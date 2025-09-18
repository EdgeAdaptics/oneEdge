"""OPC UA data ingestion publishing readings to MQTT."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from opcua import Client  # type: ignore

from services.common.logger import logger
from services.common.mqtt_client import MQTTClient


@dataclass(slots=True)
class SubscriptionConfig:
    name: str
    node_id: str
    publish_topic: str
    metric: str | None
    sampling_interval_ms: int
    deadband: float


class OPCUAIngestor:
    def __init__(self, config: Dict[str, Any], mqtt_client: MQTTClient) -> None:
        self._config = config
        self._mqtt = mqtt_client
        self._subs = self._parse_subscriptions(config.get("subscriptions", []))
        self._endpoint = config.get("endpoint")
        self._security = config.get("security", {})
        self._connected = False

    def _parse_subscriptions(self, raw: List[Dict[str, Any]]) -> List[SubscriptionConfig]:
        subs: List[SubscriptionConfig] = []
        for item in raw:
            subs.append(
                SubscriptionConfig(
                    name=item.get("name", item.get("node_id", "unknown")),
                    node_id=item["node_id"],
                    publish_topic=item.get("publish_topic", "machines/default"),
                    metric=item.get("metric"),
                    sampling_interval_ms=int(item.get("sampling_interval_ms", 1000)),
                    deadband=float(item.get("deadband", 0)),
                )
            )
        return subs

    def run(self) -> None:
        if not self._subs:
            logger.warning("No OPC UA subscriptions configured; skipping ingestion.")
            return
        while True:
            try:
                self._ingest_loop()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("OPC UA ingestion error: {}", exc)
                time.sleep(5)

    def _ingest_loop(self) -> None:
        assert self._endpoint, "OPC UA endpoint not configured"
        logger.info("Connecting to OPC UA endpoint {}", self._endpoint)
        client = Client(self._endpoint)
        policy = (self._security or {}).get("policy")
        mode = (self._security or {}).get("mode")
        if policy and policy != "None":
            client.set_security_string(f"Basic256Sha256,{mode}")
        cert = (self._security or {}).get("certificate_path")
        key = (self._security or {}).get("private_key_path")
        if cert and key:
            client.set_certificate(cert)
            client.set_private_key(key)
        client.application_uri = "urn:edgeadaptics:oneedge:ingestion"
        client.application_name = "oneEdgeOPCUAIngestor"
        client.connect()
        logger.info("OPC UA connected")
        try:
            nodes = [(sub, client.get_node(sub.node_id)) for sub in self._subs]
            last_published: dict[str, float] = {}
            while True:
                loop_start = time.monotonic()
                for sub, node in nodes:
                    try:
                        value = node.get_value()
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning("Failed to read node {}: {}", sub.node_id, exc)
                        continue
                    last_key = f"{sub.node_id}:{sub.metric}"
                    try:
                        numeric_value = float(value)
                    except (TypeError, ValueError):
                        numeric_value = None
                    last_value = last_published.get(last_key)
                    if (
                        numeric_value is not None
                        and last_value is not None
                        and abs(last_value - numeric_value) < sub.deadband
                    ):
                        continue
                    payload = {
                        "source": "opcua",
                        "metric": sub.metric or sub.name,
                        "value": value,
                        "node_id": sub.node_id,
                        "timestamp": time.time(),
                    }
                    self._mqtt.publish_json(sub.publish_topic, payload)
                    if numeric_value is not None:
                        last_published[last_key] = numeric_value
                next_tick = min(sub.sampling_interval_ms for sub in self._subs) / 1000
                elapsed = time.monotonic() - loop_start
                time.sleep(max(next_tick - elapsed, 0.05))
        finally:
            client.disconnect()
            logger.info("OPC UA disconnected")


def build_ingestor(config: Dict[str, Any], mqtt_client: MQTTClient) -> OPCUAIngestor:
    return OPCUAIngestor(config, mqtt_client)


__all__ = ["OPCUAIngestor", "build_ingestor", "SubscriptionConfig"]
