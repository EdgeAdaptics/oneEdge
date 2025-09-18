from __future__ import annotations

import argparse
import threading
import time

from services.common.config import ConfigLoader
from services.common.logger import configure_logging, get_log_level_from_env, logger
from services.common.mqtt_client import MQTTClient
from services.ingestion.opcua_ingestor import build_ingestor
from services.ingestion.simulator import SensorSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run oneEdge ingestion service")
    parser.add_argument(
        "--config",
        default="configs/oneedge.yaml",
        help="Path to oneEdge YAML configuration",
    )
    parser.add_argument(
        "--no-opcua",
        action="store_true",
        help="Disable OPC UA ingestion",
    )
    parser.add_argument(
        "--no-sim",
        action="store_true",
        help="Disable sensor simulator",
    )
    args = parser.parse_args()

    cfg = ConfigLoader.load(args.config)
    log_level = cfg.get("gateway.log_level", get_log_level_from_env("INFO"))
    configure_logging("ingestion", log_level)

    mqtt_config = cfg.get("mqtt", {})
    mqtt_client = MQTTClient(
        client_id=f"oneedge-ingestion-{cfg.get('gateway.id', 'dev')}",
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

    threads: list[threading.Thread] = []

    if not args.no_sim and cfg.get("simulated_sensors.enabled", False):
        simulator = SensorSimulator(cfg.get("simulated_sensors", {}), mqtt_client)
        sim_thread = threading.Thread(target=simulator.run, name="sensor-simulator", daemon=True)
        sim_thread.start()
        threads.append(sim_thread)

    if not args.no_opcua and cfg.get("opcua.enabled", False):
        opcua_ingestor = build_ingestor(cfg.get("opcua", {}), mqtt_client)
        opc_thread = threading.Thread(target=opcua_ingestor.run, name="opcua-ingestor", daemon=True)
        opc_thread.start()
        threads.append(opc_thread)

    if not threads:
        logger.warning("Ingestion service started with no active publishers.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping ingestion service")
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
