"""Logging utilities centralised for oneEdge services."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from loguru import logger


def configure_logging(service_name: str, level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure loguru logging for a service."""

    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=level.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        f"{service_name} | {{message}}",
        colorize=False,
        backtrace=False,
        diagnose=False,
    )

    if log_dir:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        logger.add(
            path / f"{service_name}.log",
            level=level.upper(),
            rotation="7 days",
            retention="30 days",
            compression="zip",
            enqueue=True,
        )


def get_log_level_from_env(default: str = "INFO") -> str:
    return os.getenv("ONEEDGE_LOG_LEVEL", default)


__all__ = ["logger", "configure_logging", "get_log_level_from_env"]
