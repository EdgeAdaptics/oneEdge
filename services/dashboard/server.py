from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sse_starlette.sse import EventSourceResponse

from services.common.logger import logger
from services.common.mqtt_client import MQTTClient
from services.storage.database import AlertEvent, MetricReading, init_storage, session_scope
from sqlalchemy import func


class DashboardServer:
    def __init__(
        self,
        config: Dict[str, Any],
        mqtt_config: Dict[str, Any],
        storage_path: str,
    ) -> None:
        self._config = config
        self._mqtt_config = mqtt_config
        self._storage_path = storage_path
        self._mqtt: MQTTClient | None = None
        self._alert_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._basic_auth_config = config.get("basic_auth", {})
        self._basic_auth = (
            HTTPBasic(auto_error=False)
            if self._basic_auth_config.get("enabled")
            else None
        )
        init_storage(storage_path)
        self.app = FastAPI(title="oneEdge Dashboard")
        self._setup_routes()

    # FastAPI wiring ------------------------------------------------------------

    def _setup_routes(self) -> None:
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
            route_dependencies: list[Any] = []

        @app.on_event("startup")
        async def on_startup() -> None:
            self._loop = asyncio.get_running_loop()
            await self._start_mqtt()

        @app.on_event("shutdown")
        async def on_shutdown() -> None:
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

    # MQTT bridge ----------------------------------------------------------------

    async def _start_mqtt(self) -> None:
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
        if self._mqtt:
            self._mqtt.disconnect()
            logger.info("Dashboard disconnected from MQTT broker")
            self._mqtt = None

    def _handle_alert(self, topic: str, payload: Dict[str, Any]) -> None:
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


__all__ = ["DashboardServer"]
