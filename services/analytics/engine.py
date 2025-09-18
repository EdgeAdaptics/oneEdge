from __future__ import annotations

import datetime as dt
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List

from services.common.logger import logger
from services.common.mqtt_client import MQTTClient
from services.storage.database import AlertEvent, MetricReading, init_storage, session_scope


@dataclass(slots=True)
class RuleDefinition:
    name: str
    metric: str
    operator: str
    threshold: float
    duration_s: float
    severity: str = "warning"


class AnalyticsEngine:
    """Streaming analytics engine that processes telemetry and emits alerts."""

    def __init__(self, config: Dict[str, Any], mqtt: MQTTClient, storage_path: str) -> None:
        """Initialise analytics engine with configuration, MQTT client, and storage."""

        self._config = config
        self._mqtt = mqtt
        self._window_size = int(config.get("window_size", 25))
        self._z_threshold = float(config.get("z_score_threshold", 3.0))
        self._rules = self._parse_rules(config.get("rules", []))
        self._history: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self._window_size))
        self._rule_state: dict[str, float] = {}
        self._last_alert: dict[str, float] = {}
        init_storage(storage_path)

    def _parse_rules(self, raw_rules: List[Dict[str, Any]]) -> List[RuleDefinition]:
        rules: List[RuleDefinition] = []
        for rule in raw_rules:
            try:
                rules.append(
                    RuleDefinition(
                        name=rule["name"],
                        metric=rule["metric"],
                        operator=rule.get("operator", ">"),
                        threshold=float(rule.get("threshold")),
                        duration_s=float(rule.get("duration_s", 0)),
                        severity=rule.get("severity", "warning"),
                    )
                )
            except KeyError as exc:
                logger.warning("Skipping invalid rule definition: missing {}", exc)
        return rules

    # Public API -----------------------------------------------------------------

    def on_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle an incoming telemetry message from the MQTT bus."""

        metric = payload.get("metric")
        value = payload.get("value")
        timestamp = payload.get("timestamp", time.time())
        if metric is None or value is None:
            logger.debug("Ignoring payload without metric/value: {}", payload)
            return
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            logger.debug("Skipping non-numeric value for metric {}", metric)
            numeric_value = None

        self._persist_reading(topic, metric, numeric_value, payload)
        if numeric_value is None:
            return
        key = f"{topic}/{metric}"
        history = self._history[key]
        history.append(numeric_value)
        if len(history) >= 5:
            self._detect_zscore(topic, metric, numeric_value, history, timestamp)
        self._evaluate_rules(topic, metric, numeric_value, timestamp)

    # Persistence ----------------------------------------------------------------

    def _persist_reading(
        self, topic: str, metric: str, value: float | None, payload: Dict[str, Any]
    ) -> None:
        """Persist the raw payload and derived value for later analysis."""

        timestamp_value = payload.get("timestamp", time.time())
        if isinstance(timestamp_value, (int, float)):
            timestamp_dt = dt.datetime.utcfromtimestamp(timestamp_value)
        elif isinstance(timestamp_value, str):
            try:
                timestamp_dt = dt.datetime.fromisoformat(timestamp_value)
            except ValueError:
                timestamp_dt = dt.datetime.utcnow()
        elif isinstance(timestamp_value, dt.datetime):
            timestamp_dt = timestamp_value
        else:
            timestamp_dt = dt.datetime.utcnow()

        with session_scope() as session:
            session.add(
                MetricReading(
                    topic=topic,
                    metric=metric,
                    value=value,
                    raw_payload=payload,
                    timestamp=timestamp_dt,
                )
            )

    # Detection ------------------------------------------------------------------

    def _detect_zscore(
        self,
        topic: str,
        metric: str,
        value: float,
        history: Deque[float],
        timestamp: float,
    ) -> None:
        """Detect statistical outliers using a rolling z-score."""

        if len(history) < 2:
            return
        mean = statistics.fmean(history)
        stdev = statistics.pstdev(history)
        if stdev == 0:
            return
        z_score = (value - mean) / stdev
        if abs(z_score) >= self._z_threshold:
            self._emit_alert(
                topic=topic,
                rule=f"zscore_{metric}",
                severity="critical" if abs(z_score) > self._z_threshold * 1.5 else "warning",
                message=f"Z-score anomaly detected for {metric}: {z_score:.2f}",
                details={
                    "metric": metric,
                    "value": value,
                    "mean": mean,
                    "stdev": stdev,
                    "z_score": z_score,
                    "timestamp": timestamp,
                },
            )

    def _evaluate_rules(self, topic: str, metric: str, value: float, timestamp: float) -> None:
        """Evaluate configured threshold rules for the given metric sample."""

        for rule in self._rules:
            if rule.metric != metric:
                continue
            triggered = self._apply_operator(value, rule.operator, rule.threshold)
            state_key = f"{topic}:{rule.name}"
            if triggered:
                if state_key not in self._rule_state:
                    self._rule_state[state_key] = timestamp
                elif timestamp - self._rule_state[state_key] >= rule.duration_s:
                    self._emit_alert(
                        topic=topic,
                        rule=rule.name,
                        severity=rule.severity,
                        message=f"Rule {rule.name} triggered for {metric}",
                        details={
                            "metric": metric,
                            "value": value,
                            "threshold": rule.threshold,
                            "operator": rule.operator,
                            "duration_s": rule.duration_s,
                            "timestamp": timestamp,
                        },
                    )
                    self._rule_state[state_key] = timestamp + 60  # cooldown
            else:
                self._rule_state.pop(state_key, None)

    def _apply_operator(self, value: float, operator: str, threshold: float) -> bool:
        """Evaluate a rule comparison operator against a threshold."""

        if operator == ">":
            return value > threshold
        if operator == ">=":
            return value >= threshold
        if operator == "<":
            return value < threshold
        if operator == "<=":
            return value <= threshold
        if operator == "==":
            return value == threshold
        if operator == "!=":
            return value != threshold
        logger.warning("Unsupported operator {}, defaulting to >", operator)
        return value > threshold

    # Alerting -------------------------------------------------------------------

    def _emit_alert(
        self,
        topic: str,
        rule: str,
        severity: str,
        message: str,
        details: Dict[str, Any],
    ) -> None:
        """Publish an alert to MQTT and persist it in the database."""

        alert_key = f"{topic}:{rule}:{message}"
        now = time.time()
        if now - self._last_alert.get(alert_key, 0) < 30:
            return
        self._last_alert[alert_key] = now
        alert_payload = {
            "topic": topic,
            "rule": rule,
            "severity": severity,
            "message": message,
            "details": details,
            "timestamp": now,
        }
        logger.warning("Alert emitted: {}", alert_payload)
        self._mqtt.publish_json("alerts", alert_payload)
        with session_scope() as session:
            session.add(
                AlertEvent(
                    topic=topic,
                    rule=rule,
                    severity=severity,
                    message=message,
                    details=details,
                )
            )


__all__ = ["AnalyticsEngine"]
