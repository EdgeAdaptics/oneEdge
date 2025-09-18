"""MQTT client helper built on top of paho-mqtt."""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict

import paho.mqtt.client as mqtt

MessageHandler = Callable[[str, Dict[str, Any]], None]


class MQTTClient:
    """Threaded MQTT client with JSON helper methods."""

    def __init__(
        self,
        client_id: str,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        keepalive: int = 60,
        tls: bool = False,
        base_topic: str | None = None,
        tls_settings: Dict[str, Any] | None = None,
    ) -> None:
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            self._client.username_pw_set(username, password)
        tls_config = {k: v for k, v in (tls_settings or {}).items() if v}
        if tls or tls_config:
            settings = tls_config
            self._client.tls_set(
                ca_certs=settings.get("ca_cert"),
                certfile=settings.get("client_cert"),
                keyfile=settings.get("client_key"),
            )
            if (tls_settings or {}).get("insecure", False):
                self._client.tls_insecure_set(True)
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message
        self._host = host
        self._port = port
        self._keepalive = keepalive
        self._base_topic = base_topic.rstrip("/") if base_topic else None
        self._handlers: list[tuple[str, MessageHandler]] = []
        self._connected = threading.Event()

    def _handle_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int) -> None:
        if rc == 0:
            self._connected.set()
        else:
            self._connected.clear()

    def _handle_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        self._connected.clear()

    def _handle_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except json.JSONDecodeError:
            return
        for pattern, handler in list(self._handlers):
            if mqtt.topic_matches_sub(pattern, message.topic):
                handler(message.topic, payload)

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=self._keepalive)
        self._client.loop_start()
        if not self._connected.wait(timeout=10):
            raise ConnectionError(f"Failed to connect to MQTT broker at {self._host}:{self._port}")

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_json(self, topic: str, payload: Dict[str, Any], qos: int = 0, retain: bool = False) -> None:
        final_topic = self._qualify_topic(topic)
        self._client.publish(final_topic, json.dumps(payload), qos=qos, retain=retain)

    def subscribe_json(self, topic: str, handler: MessageHandler, qos: int = 0) -> None:
        final_topic = self._qualify_topic(topic)
        self._handlers.append((final_topic, handler))
        self._client.subscribe(final_topic, qos=qos)

    def _qualify_topic(self, topic: str) -> str:
        if self._base_topic:
            return f"{self._base_topic}/{topic.lstrip('/')}"
        return topic


__all__ = ["MQTTClient"]
