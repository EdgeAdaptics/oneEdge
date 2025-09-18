from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator
from sse_starlette.sse import EventSourceResponse

from services.common.logger import logger
from services.common.mqtt_client import MQTTClient
from services.storage.database import (
    AlertEvent,
    MetricReading,
    ProvisionedDevice,
    init_storage,
    session_scope,
)
from sqlalchemy import func


class DeviceCreate(BaseModel):
    """Request payload for provisioning or updating a device."""

    device_id: str = Field(..., description="Unique identifier used for telemetry topics")
    name: str = Field(..., description="Human-friendly device name")
    device_type: str | None = Field(None, description="Equipment category or model")
    location: str | None = Field(None, description="Physical location or cell")
    status: str | None = Field("inactive", description="Lifecycle state e.g. active/maintenance")
    metadata: Dict[str, Any] | None = Field(None, description="Additional free-form attributes")
    auth_method: str | None = Field("pre_shared_key", description="Authentication method e.g. pre_shared_key, x509")
    auth_id: str | None = Field(None, description="Identifier presented by the device during registration")
    allowed_endpoints: List[str] | None = Field(None, description="Allow-listed endpoints or services for the device")
    rotation_interval_hours: int | None = Field(168, ge=1, le=24 * 30, description="Secret rotation cadence in hours")
    initial_secret: str | None = Field(None, description="Optional bootstrap secret for PSK methods")
    policy_template: Dict[str, Any] | None = Field(None, description="Custom policy asset template for this device")
    quarantined: bool | None = Field(False, description="Whether the device should start in quarantine")

    @validator("allowed_endpoints", pre=True)
    def _normalise_endpoints(cls, value: Any) -> List[str] | None:  # noqa: D401
        """Ensure allowed endpoints are stored as a list of unique strings."""

        if value is None:
            return None
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return sorted(set(items))
        if isinstance(value, (list, tuple)):
            return sorted({str(item).strip() for item in value if str(item).strip()}) or None
        raise ValueError("allowed_endpoints must be a string or list")


class DeviceRegistration(BaseModel):
    """Payload supplied by a device attempting to register/authenticate."""

    device_id: str
    auth_id: str | None = None
    auth_secret: str | None = None
    attributes: Dict[str, Any] | None = None


class DeviceLifecycleAction(BaseModel):
    """Generic action payload supporting optional reason notes."""

    reason: str | None = Field(None, description="Context for the lifecycle action")


class DashboardServer:
    """HTTP API and dashboard runtime for the oneEdge gateway."""

    def __init__(
        self,
        config: Dict[str, Any],
        mqtt_config: Dict[str, Any],
        storage_path: str,
        gateway_config: Dict[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._mqtt_config = mqtt_config
        self._storage_path = storage_path
        self._gateway_config = gateway_config or {}
        self._mqtt: MQTTClient | None = None
        self._alert_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._basic_auth_config = config.get("basic_auth", {})
        self._basic_auth = (
            HTTPBasic(auto_error=False)
            if self._basic_auth_config.get("enabled")
            else None
        )
        self._max_failed_attempts = int(
            config.get("max_failed_auth_attempts")
            or self._gateway_config.get("max_failed_auth_attempts")
            or 5
        )
        self._challenge_window_minutes = int(
            config.get("challenge_window_minutes")
            or self._gateway_config.get("challenge_window_minutes")
            or 5
        )
        init_storage(storage_path)
        self.app = FastAPI(title="oneEdge Dashboard")
        self._setup_routes()

    # FastAPI wiring ------------------------------------------------------------

    def _setup_routes(self) -> None:
        """Register FastAPI routes and lifecycle hooks."""

        app = self.app

        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(exist_ok=True)
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        if self._basic_auth:

            async def require_auth(
                credentials: HTTPBasicCredentials | None = Depends(self._basic_auth),
            ) -> None:
                if not self._verify_credentials(credentials):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Basic realm=oneEdge"},
                    )

            route_dependencies = [Depends(require_auth)]
        else:
            route_dependencies: List[Any] = []

        @app.on_event("startup")
        async def on_startup() -> None:
            """Initialise resources when the application boots."""

            self._loop = asyncio.get_running_loop()
            await self._start_mqtt()

        @app.on_event("shutdown")
        async def on_shutdown() -> None:
            """Gracefully release resources on shutdown."""

            await self._stop_mqtt()

        @app.get("/", response_class=HTMLResponse, dependencies=route_dependencies)
        async def index() -> Any:  # pragma: no cover
            index_html = static_dir / "index.html"
            if not index_html.exists():
                raise HTTPException(status_code=404, detail="Dashboard assets missing")
            return FileResponse(index_html)

        @app.get("/api/metrics/latest", dependencies=route_dependencies)
        async def latest_metrics(limit: int = 10) -> List[Dict[str, Any]]:
            with session_scope() as session:
                subquery = (
                    session.query(
                        MetricReading.metric,
                        MetricReading.topic,
                        func.max(MetricReading.timestamp).label("latest_ts"),
                    )
                    .group_by(MetricReading.metric, MetricReading.topic)
                    .subquery()
                )
                rows = (
                    session.query(MetricReading)
                    .join(
                        subquery,
                        (MetricReading.metric == subquery.c.metric)
                        & (MetricReading.topic == subquery.c.topic)
                        & (MetricReading.timestamp == subquery.c.latest_ts),
                    )
                    .order_by(MetricReading.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "metric": row.metric,
                        "topic": row.topic,
                        "value": row.value,
                        "timestamp": row.timestamp,
                        "source": row.raw_payload.get("source") if row.raw_payload else None,
                    }
                    for row in rows
                ]

        @app.get("/api/metrics/history", dependencies=route_dependencies)
        async def metric_history(metric: str, topic: str, limit: int = 100) -> List[Dict[str, Any]]:
            with session_scope() as session:
                rows = (
                    session.query(MetricReading)
                    .filter(MetricReading.metric == metric)
                    .filter(MetricReading.topic == topic)
                    .order_by(MetricReading.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "metric": row.metric,
                        "topic": row.topic,
                        "value": row.value,
                        "timestamp": row.timestamp,
                    }
                    for row in reversed(rows)
                ]

        @app.get("/api/alerts", dependencies=route_dependencies)
        async def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
            with session_scope() as session:
                rows = (
                    session.query(AlertEvent)
                    .order_by(AlertEvent.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "id": row.id,
                        "topic": row.topic,
                        "rule": row.rule,
                        "message": row.message,
                        "severity": row.severity,
                        "timestamp": row.timestamp,
                        "details": row.details,
                        "acknowledged": bool(row.acknowledged),
                    }
                    for row in rows
                ]

        @app.post("/api/alerts/{alert_id}/ack", dependencies=route_dependencies)
        async def ack_alert(alert_id: int) -> Dict[str, Any]:
            with session_scope() as session:
                alert = session.get(AlertEvent, alert_id)
                if not alert:
                    raise HTTPException(status_code=404, detail="Alert not found")
                alert.acknowledged = 1
                return {"status": "ok"}

        @app.get("/api/alerts/stream", dependencies=route_dependencies)
        async def alerts_stream() -> EventSourceResponse:
            async def event_generator():
                while True:
                    try:
                        payload = await self._alert_queue.get()
                    except asyncio.CancelledError:  # pragma: no cover - client disconnect
                        break
                    yield {
                        "event": "alert",
                        "data": json.dumps(payload),
                    }

            return EventSourceResponse(event_generator())

        @app.get("/api/devices", dependencies=route_dependencies)
        async def list_devices() -> List[Dict[str, Any]]:
            with session_scope() as session:
                rows = session.query(ProvisionedDevice).order_by(ProvisionedDevice.name.asc()).all()
                return [self._serialise_device(row) for row in rows]

        @app.post("/api/devices", dependencies=route_dependencies)
        async def create_device(payload: DeviceCreate) -> Dict[str, Any]:
            data = payload.dict()
            device_id = data["device_id"].strip()
            if not device_id:
                raise HTTPException(status_code=400, detail="device_id must not be empty")

            bootstrap_secret: str | None = None
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == device_id)
                    .one_or_none()
                )
                if device:
                    self._update_device_from_payload(device, data)
                else:
                    device = ProvisionedDevice(
                        device_id=device_id,
                        name=data.get("name") or device_id,
                        device_type=data.get("device_type"),
                        location=data.get("location"),
                        status=data.get("status") or "inactive",
                    )
                    session.add(device)
                    self._update_device_from_payload(device, data)
                if device.auth_method == "pre_shared_key" and not device.current_secret_hash:
                    if data.get("initial_secret"):
                        bootstrap_secret = data.get("initial_secret")
                        device.current_secret_hash = self._hash_secret(bootstrap_secret)
                        device.last_rotated_at = dt.datetime.utcnow()
                    elif device.device_static_secret_hash:
                        device.current_secret_hash = device.device_static_secret_hash
                        device.last_rotated_at = dt.datetime.utcnow()
                    else:
                        bootstrap_secret = secrets.token_urlsafe(32)
                        device.current_secret_hash = self._hash_secret(bootstrap_secret)
                        device.last_rotated_at = dt.datetime.utcnow()

                if data.get("initial_secret") and bootstrap_secret is None:
                    bootstrap_secret = data.get("initial_secret")

            response = {"status": "ok", "device": self._serialise_device(device)}
            if bootstrap_secret:
                response["bootstrap_secret"] = bootstrap_secret
            return response

        @app.post("/api/devices/register")
        async def register_device(payload: DeviceRegistration) -> Dict[str, Any]:
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == payload.device_id)
                    .one_or_none()
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not provisioned")
                if device.quarantined:
                    raise HTTPException(status_code=423, detail="Device is quarantined")

                now = dt.datetime.utcnow()

                if device.auth_id and payload.auth_id and device.auth_id != payload.auth_id:
                    self._record_failed_attempt(device)
                    raise HTTPException(status_code=401, detail="Authentication identifier mismatch")
                if not device.auth_id and payload.auth_id:
                    device.auth_id = payload.auth_id

                if payload.hardware_fingerprint:
                    fingerprint_hash = self._hash_secret(payload.hardware_fingerprint)
                    if device.hardware_fingerprint_hash and device.hardware_fingerprint_hash != fingerprint_hash:
                        self._record_failed_attempt(device)
                        raise HTTPException(status_code=401, detail="Hardware fingerprint mismatch")
                    if not device.hardware_fingerprint_hash:
                        device.hardware_fingerprint_hash = fingerprint_hash

                if device.device_static_secret_hash is None:
                    if payload.auth_secret:
                        device.device_static_secret_hash = self._hash_secret(payload.auth_secret)
                    else:
                        raise HTTPException(status_code=400, detail="Device static key required for initial handshake")
                elif payload.auth_secret and not self._verify_secret(device.device_static_secret_hash, payload.auth_secret):
                    self._record_failed_attempt(device)
                    raise HTTPException(status_code=401, detail="Invalid device static key")

                if payload.auth_secret and device.auth_method == "pre_shared_key":
                    device.current_secret_hash = self._hash_secret(payload.auth_secret)
                    device.last_rotated_at = now

                if payload.request_challenge or not payload.challenge_response:
                    return self._issue_challenge(device, now)

                if not device.challenge_nonce or not device.challenge_expires_at:
                    self._record_failed_attempt(device)
                    raise HTTPException(status_code=400, detail="Challenge not requested")
                if device.challenge_expires_at < now:
                    self._record_failed_attempt(device)
                    raise HTTPException(status_code=400, detail="Challenge expired")

                expected = hmac.new(
                    (device.device_static_secret_hash or "").encode("utf-8"),
                    device.challenge_nonce.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                if not payload.challenge_response or not secrets.compare_digest(expected, payload.challenge_response):
                    self._record_failed_attempt(device)
                    raise HTTPException(status_code=401, detail="Challenge verification failed")

                device.challenge_nonce = None
                device.challenge_expires_at = None
                device.failed_auth_attempts = 0
                device.last_seen_at = now
                device.last_auth_at = now
                if device.status != "quarantined":
                    device.status = "active"

                new_secret: str | None = None
                if self._rotation_due(device, now) and device.auth_method == "pre_shared_key":
                    new_secret = secrets.token_urlsafe(32)
                    device.current_secret_hash = self._hash_secret(new_secret)
                    device.last_rotated_at = now

                if payload.attributes:
                    attributes = device.attributes or {}
                    attributes.update(payload.attributes)
                    device.attributes = attributes

                policy = self._build_policy(device)
                response = {
                    "status": "ok",
                    "device": self._serialise_device(device),
                    "policy": policy,
                    "next_rotation_hours": device.rotation_interval_hours,
                }
                if new_secret:
                    response["session_secret"] = new_secret
                return response

        @app.post("/api/devices/{device_id}/rotate", dependencies=route_dependencies)
        async def rotate_device(device_id: str) -> Dict[str, Any]:
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == device_id)
                    .one_or_none()
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                if device.auth_method != "pre_shared_key":
                    raise HTTPException(status_code=400, detail="Rotation supported for pre_shared_key devices only")
                new_secret = secrets.token_urlsafe(32)
                device.current_secret_hash = self._hash_secret(new_secret)
                device.last_rotated_at = dt.datetime.utcnow()
                response = {
                    "status": "ok",
                    "device": self._serialise_device(device),
                    "session_secret": new_secret,
                }
                return response

        @app.post("/api/devices/{device_id}/quarantine", dependencies=route_dependencies)
        async def quarantine_device(device_id: str, payload: DeviceLifecycleAction | None = None) -> Dict[str, Any]:
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == device_id)
                    .one_or_none()
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                device.quarantined = True
                device.status = "quarantined"
                attributes = device.attributes or {}
                if payload and payload.reason:
                    attributes["quarantine_reason"] = payload.reason
                device.attributes = attributes
                return {"status": "ok", "device": self._serialise_device(device)}

        @app.post("/api/devices/{device_id}/authorize", dependencies=route_dependencies)
        async def authorize_device(device_id: str, payload: DeviceLifecycleAction | None = None) -> Dict[str, Any]:
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == device_id)
                    .one_or_none()
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                device.quarantined = False
                attributes = device.attributes or {}
                attributes.pop("quarantine_reason", None)
                if payload and payload.reason:
                    attributes["authorization_note"] = payload.reason
                device.attributes = attributes if attributes else None
                device.status = "inactive" if device.status in (None, "quarantined") else device.status
                device.failed_auth_attempts = 0
                device.challenge_nonce = None
                device.challenge_expires_at = None
                return {"status": "ok", "device": self._serialise_device(device)}

        @app.delete("/api/devices/{device_id}", dependencies=route_dependencies)
        async def delete_device(device_id: str) -> Dict[str, Any]:
            with session_scope() as session:
                device = (
                    session.query(ProvisionedDevice)
                    .filter(ProvisionedDevice.device_id == device_id)
                    .one_or_none()
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                session.delete(device)
                return {"status": "ok"}

    # MQTT bridge ----------------------------------------------------------------

    async def _start_mqtt(self) -> None:
        """Create the MQTT client used to bridge alerts to the UI."""

        mqtt_client = MQTTClient(
            client_id="oneedge-dashboard",
            host=self._mqtt_config.get("host", "localhost"),
            port=int(self._mqtt_config.get("port", 1883)),
            username=self._mqtt_config.get("username"),
            password=self._mqtt_config.get("password"),
            keepalive=int(self._mqtt_config.get("keepalive", 60)),
            tls=bool(self._mqtt_config.get("tls", False)),
            base_topic=self._mqtt_config.get("base_topic"),
            tls_settings=self._mqtt_config.get("tls_settings"),
        )
        mqtt_client.connect()
        mqtt_client.subscribe_json("alerts", self._handle_alert)
        self._mqtt = mqtt_client
        logger.info("Dashboard connected to MQTT broker")

    async def _stop_mqtt(self) -> None:
        """Tear down the MQTT bridge when the server stops."""

        if self._mqtt:
            self._mqtt.disconnect()
            logger.info("Dashboard disconnected from MQTT broker")
            self._mqtt = None

    def _handle_alert(self, topic: str, payload: Dict[str, Any]) -> None:
        """Push MQTT alert payloads into the SSE queue."""

        if not self._loop:
            return

        def _enqueue() -> None:
            try:
                self._alert_queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    self._alert_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                self._alert_queue.put_nowait(payload)

        self._loop.call_soon_threadsafe(_enqueue)

    def _verify_credentials(self, credentials: HTTPBasicCredentials | None) -> bool:
        """Validate dashboard credentials when basic auth is enabled."""

        if self._basic_auth is None:
            return True
        if credentials is None:
            return False
        username = self._basic_auth_config.get("username")
        password = self._basic_auth_config.get("password")
        if not username or not password:
            logger.warning("Basic auth configured without credentials; denying access")
            return False
        return secrets.compare_digest(credentials.username, username) and secrets.compare_digest(
            credentials.password, password
        )

    # Helpers --------------------------------------------------------------------

    def _update_device_from_payload(self, device: ProvisionedDevice, data: Dict[str, Any]) -> None:
        """Update ORM entity with values from the provisioning payload."""

        device.name = data.get("name") or device.name
        device.device_type = data.get("device_type")
        device.location = data.get("location")
        device.status = data.get("status") or device.status
        device.auth_method = (data.get("auth_method") or device.auth_method or "pre_shared_key").lower()
        device.auth_id = data.get("auth_id") or device.auth_id
        device.allowed_endpoints = data.get("allowed_endpoints")
        device.rotation_interval_hours = data.get("rotation_interval_hours") or device.rotation_interval_hours
        device.policy_document = data.get("policy_template") or device.policy_document
        if data.get("device_static_key"):
            device.device_static_secret_hash = self._hash_secret(data["device_static_key"])
            if device.auth_method == "pre_shared_key" and not device.current_secret_hash:
                device.current_secret_hash = device.device_static_secret_hash
                device.last_rotated_at = dt.datetime.utcnow()
        if data.get("hardware_fingerprint"):
            device.hardware_fingerprint_hash = self._hash_secret(data["hardware_fingerprint"])
        if data.get("device_public_key"):
            device.device_public_key = data.get("device_public_key")
        if data.get("quarantined") is not None:
            device.quarantined = bool(data.get("quarantined"))
            if device.quarantined:
                device.status = "quarantined"
        device.attributes = data.get("metadata")
        if data.get("initial_secret") and device.auth_method == "pre_shared_key":
            device.current_secret_hash = self._hash_secret(data["initial_secret"])
            device.last_rotated_at = dt.datetime.utcnow()

    def _serialise_device(self, device: ProvisionedDevice) -> Dict[str, Any]:
        """Convert a device ORM entity into a JSON-serialisable payload."""

        now = dt.datetime.utcnow()
        rotation_interval = device.rotation_interval_hours or 0
        needs_rotation = bool(
            rotation_interval
            and (
                device.last_rotated_at is None
                or now - device.last_rotated_at > dt.timedelta(hours=rotation_interval)
            )
        )
        stale_threshold_hours = rotation_interval * 2 if rotation_interval else 48
        stale = bool(device.last_seen_at and now - device.last_seen_at > dt.timedelta(hours=stale_threshold_hours))
        attention_required = device.quarantined or needs_rotation or stale

        return {
            "id": device.id,
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type,
            "location": device.location,
            "status": device.status,
            "auth_method": device.auth_method,
            "auth_id": device.auth_id,
            "allowed_endpoints": device.allowed_endpoints or [],
            "rotation_interval_hours": device.rotation_interval_hours,
            "quarantined": bool(device.quarantined),
            "last_seen_at": self._isoformat(device.last_seen_at),
            "last_auth_at": self._isoformat(device.last_auth_at),
            "last_rotated_at": self._isoformat(device.last_rotated_at),
            "policy": device.policy_document,
            "metadata": device.attributes or {},
            "needs_rotation": needs_rotation,
            "stale": stale,
            "attention_required": attention_required,
            "failed_auth_attempts": device.failed_auth_attempts,
            "challenge_pending": bool(device.challenge_nonce),
            "challenge_expires_at": self._isoformat(device.challenge_expires_at),
        }

    def _build_policy(self, device: ProvisionedDevice) -> Dict[str, Any]:
        """Construct the policy asset delivered to devices post-authentication."""

        if device.policy_document:
            return device.policy_document
        base_topic = self._mqtt_config.get("base_topic") or "oneEdge"
        return {
            "device_id": device.device_id,
            "allowed_endpoints": device.allowed_endpoints or [],
            "topics": {
                "telemetry": f"{base_topic}/devices/{device.device_id}/telemetry",
                "alerts": f"{base_topic}/devices/{device.device_id}/alerts",
            },
            "rotation_interval_hours": device.rotation_interval_hours,
        }

    def _issue_challenge(self, device: ProvisionedDevice, now: dt.datetime) -> Dict[str, Any]:
        """Generate and persist a challenge nonce for the device."""

        nonce = secrets.token_urlsafe(32)
        device.challenge_nonce = nonce
        device.challenge_expires_at = now + dt.timedelta(minutes=self._challenge_window_minutes)
        device.last_seen_at = now
        return {
            "status": "challenge",
            "challenge": nonce,
            "expires_at": self._isoformat(device.challenge_expires_at),
            "device": self._serialise_device(device),
        }

    def _record_failed_attempt(self, device: ProvisionedDevice) -> None:
        """Increment failure counters and quarantine if threshold exceeded."""

        device.failed_auth_attempts = (device.failed_auth_attempts or 0) + 1
        if device.failed_auth_attempts >= self._max_failed_attempts:
            device.quarantined = True
            device.status = "quarantined"

    @staticmethod
    def _hash_secret(secret: str) -> str:
        """Return a SHA-256 hash for the provided secret."""

        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    @staticmethod
    def _verify_secret(stored_hash: str | None, candidate: str) -> bool:
        """Validate a candidate secret against the stored hash."""

        if not stored_hash:
            return False
        return secrets.compare_digest(stored_hash, hashlib.sha256(candidate.encode("utf-8")).hexdigest())

    @staticmethod
    def _rotation_due(device: ProvisionedDevice, now: dt.datetime) -> bool:
        """Determine whether key rotation should occur for a device."""

        if device.rotation_interval_hours is None or device.rotation_interval_hours <= 0:
            return False
        if device.last_rotated_at is None:
            return True
        return now - device.last_rotated_at > dt.timedelta(hours=device.rotation_interval_hours)

    @staticmethod
    def _isoformat(value: dt.datetime | None) -> str | None:
        """Return an ISO 8601 string for datetime values."""

        if value is None:
            return None
        return value.replace(tzinfo=dt.timezone.utc).isoformat()


__all__ = ["DashboardServer"]
