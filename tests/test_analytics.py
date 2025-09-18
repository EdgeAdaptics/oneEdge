from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from services.analytics.engine import AnalyticsEngine


class DummyMQTT:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.messages.append((topic, payload))

    def subscribe_json(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - compatibility
        pass

    def connect(self) -> None:  # pragma: no cover
        pass

    def disconnect(self) -> None:  # pragma: no cover
        pass


@pytest.fixture()
def analytics_engine(tmp_path: Path) -> AnalyticsEngine:
    mqtt = DummyMQTT()
    config = {
        "window_size": 5,
        "z_score_threshold": 2.0,
        "rules": [
            {
                "name": "high_temperature",
                "metric": "temperature",
                "operator": ">",
                "threshold": 80,
                "duration_s": 0,
                "severity": "critical",
            }
        ],
    }
    storage_path = tmp_path / "analytics.db"
    engine = AnalyticsEngine(config, mqtt, str(storage_path))
    return engine


def test_rule_trigger_generates_alert(analytics_engine: AnalyticsEngine) -> None:
    topic = "machines/compressor_7"
    analytics_engine.on_message(topic, {"metric": "temperature", "value": 85, "timestamp": time.time()})
    assert analytics_engine._mqtt.messages  # type: ignore[attr-defined]
    topic_name, payload = analytics_engine._mqtt.messages[-1]  # type: ignore[attr-defined]
    assert topic_name.endswith("alerts")
    assert payload["rule"] == "high_temperature"


def test_zscore_detection(analytics_engine: AnalyticsEngine) -> None:
    topic = "machines/compressor_7"
    base = [60, 61, 62, 59, 60]
    for value in base:
        analytics_engine.on_message(topic, {"metric": "temperature", "value": value, "timestamp": time.time()})
    analytics_engine.on_message(topic, {"metric": "temperature", "value": 75, "timestamp": time.time()})
    messages = [
        payload
        for topic_name, payload in analytics_engine._mqtt.messages  # type: ignore[attr-defined]
        if payload["rule"].startswith("zscore")
    ]
    assert messages, "Expected z-score alert to be emitted"
