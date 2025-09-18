"""Entry point for the retention maintenance utility."""

from __future__ import annotations

import argparse

from services.common.config import ConfigLoader
from services.common.logger import configure_logging, get_log_level_from_env, logger
from services.storage.database import init_storage
from services.storage.retention import purge_expired


def main() -> None:
    """Purge expired metrics and alerts based on retention policy."""

    parser = argparse.ArgumentParser(description="Run oneEdge retention maintenance")
    parser.add_argument(
        "--config",
        default="configs/oneedge.yaml",
        help="Path to oneEdge YAML configuration",
    )
    args = parser.parse_args()

    cfg = ConfigLoader.load(args.config)
    log_level = cfg.get("gateway.log_level", get_log_level_from_env("INFO"))
    configure_logging("retention", log_level)
    db_path = cfg.get("storage.database_path", "./oneedge.db")

    init_storage(db_path)
    deleted = purge_expired(cfg.get("storage.retention", {}))
    logger.info("Retention run removed records: {}", deleted)


if __name__ == "__main__":
    main()
