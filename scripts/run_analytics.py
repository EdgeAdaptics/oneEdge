from __future__ import annotations

import argparse
import time

from services.analytics.engine import AnalyticsEngine
from services.common.config import ConfigLoader
from services.common.logger import configure_logging, get_log_level_from_env, logger
from services.common.mqtt_client import MQTTClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Run oneEdge analytics engine")
    parser.add_argument(
        "--config",
        default="configs/oneedge.yaml",
        help="Path to oneEdge YAML configuration",
    )
    args = parser.parse_args()

    cfg = ConfigLoader.load(args.config)
    log_level = cfg.get("gateway.log_level", get_log_level_from_env("INFO"))
    configure_logging("analytics", log_level)

    mqtt_config = cfg.get("mqtt", {})
    mqtt_client = MQTTClient(
        client_id=f"oneedge-analytics-{cfg.get('gateway.id', 'dev')}",
        host=mqtt_config.get("host", "localhost"),
        port=int(mqtt_config.get("port", 1883)),
        username=mqtt_config.get("username"),
        password=mqtt_config.get("password"),
        keepalive=int(mqtt_config.get("keepalive", 60)),
        tls=bool(mqtt_config.get("tls", False)),
        base_topic=mqtt_config.get("base_topic"),
        tls_settings=mqtt_config.get("tls_settings"),
    )
    mqtt_client.connect()

    storage_path = cfg.get("storage.database_path", "./oneedge.db")
    engine = AnalyticsEngine(cfg.get("analytics", {}), mqtt_client, storage_path)

    mqtt_client.subscribe_json("machines/#", engine.on_message)

    logger.info("Analytics engine initialised; awaiting telemetry")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Analytics service stopping")
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
