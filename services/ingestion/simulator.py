"""Simulated sensor publisher for development and testing."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from services.common.logger import logger
from services.common.mqtt_client import MQTTClient


@dataclass(slots=True)
class SimulatedSensor:
    sensor_id: str
    publish_topic: str
    metric: str
    baseline: float
    variance: float
    anomaly_chance: float
    anomaly_delta: float


class SensorSimulator:
    def __init__(self, config: Dict[str, Any], mqtt: MQTTClient) -> None:
        self._config = config
        self._mqtt = mqtt
        self._interval = max(int(config.get("interval_ms", 1000)), 100)
        self._sensors = self._parse_sensors(config.get("sensors", []))
        self._running = False

    def _parse_sensors(self, raw: List[Dict[str, Any]]) -> List[SimulatedSensor]:
        sensors: List[SimulatedSensor] = []
        for item in raw:
            sensors.append(
                SimulatedSensor(
                    sensor_id=item.get("id", "sensor"),
                    publish_topic=item.get("publish_topic", "machines/sim"),
                    metric=item.get("metric", "value"),
                    baseline=float(item.get("baseline", 0.0)),
                    variance=float(item.get("variance", 1.0)),
                    anomaly_chance=float(item.get("anomaly_chance", 0.0)),
                    anomaly_delta=float(item.get("anomaly_delta", 0.0)),
                )
            )
        return sensors

    def run(self) -> None:
        if not self._sensors:
            logger.info("No simulated sensors configured.")
            return
        self._running = True
        logger.info("Starting sensor simulator for {} sensors", len(self._sensors))
        while self._running:
            tick = time.time()
            for sensor in self._sensors:
                value = random.gauss(sensor.baseline, sensor.variance)
                if random.random() < sensor.anomaly_chance:
                    value += random.choice([-sensor.anomaly_delta, sensor.anomaly_delta])
                payload = {
                    "source": "simulator",
                    "sensor_id": sensor.sensor_id,
                    "metric": sensor.metric,
                    "value": round(value, 4),
                    "timestamp": tick,
                }
                self._mqtt.publish_json(sensor.publish_topic, payload)
            time.sleep(self._interval / 1000)

    def stop(self) -> None:
        self._running = False


__all__ = ["SensorSimulator"]
