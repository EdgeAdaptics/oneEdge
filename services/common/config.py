"""Configuration loader for oneEdge services."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(slots=True)
class Config:
    """Simple wrapper around the loaded configuration dictionary."""

    data: Dict[str, Any]

    def get(self, path: str, default: Any | None = None) -> Any:
        """Return a key from the configuration using dot-notation."""

        cursor: Any = self.data
        for token in path.split("."):
            if not isinstance(cursor, dict):
                return default
            if token not in cursor:
                return default
            cursor = cursor[token]
        return cursor


class ConfigLoader:
    """Loads YAML configuration files with simple caching."""

    _lock = threading.Lock()
    _cached: Config | None = None
    _source_path: Path | None = None
    _source_mtime: float | None = None

    @classmethod
    def load(cls, path: str | Path) -> Config:
        config_path = Path(path).expanduser().resolve()
        with cls._lock:
            if cls._should_reload(config_path):
                with config_path.open("r", encoding="utf-8") as handle:
                    raw_config = yaml.safe_load(handle) or {}
                cls._cached = Config(raw_config)
                cls._source_path = config_path
                cls._source_mtime = config_path.stat().st_mtime
        assert cls._cached is not None, "Configuration cache not initialized"
        return cls._cached

    @classmethod
    def _should_reload(cls, path: Path) -> bool:
        if cls._cached is None:
            return True
        if cls._source_path != path:
            return True
        try:
            return path.stat().st_mtime != cls._source_mtime
        except FileNotFoundError:
            return True


__all__ = ["Config", "ConfigLoader"]
