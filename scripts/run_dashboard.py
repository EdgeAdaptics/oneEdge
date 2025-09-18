"""Entry point for the oneEdge dashboard service."""

from __future__ import annotations

import argparse

import uvicorn

from services.common.config import ConfigLoader
from services.common.logger import configure_logging, get_log_level_from_env
from services.dashboard.server import DashboardServer


def main() -> None:
    """Initialise the dashboard server and run uvicorn."""

    parser = argparse.ArgumentParser(description="Run oneEdge dashboard server")
    parser.add_argument(
        "--config",
        default="configs/oneedge.yaml",
        help="Path to oneEdge YAML configuration",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    cfg = ConfigLoader.load(args.config)
    log_level = cfg.get("gateway.log_level", get_log_level_from_env("INFO"))
    configure_logging("dashboard", log_level)

    host = cfg.get("dashboard.host", args.host)
    port = int(cfg.get("dashboard.port", args.port))
    tls_cfg = cfg.get("dashboard.tls", {}) or {}
    tls_enabled = bool(tls_cfg.get("enabled"))
    ssl_certfile = tls_cfg.get("certfile") if tls_enabled else None
    ssl_keyfile = tls_cfg.get("keyfile") if tls_enabled else None
    server = DashboardServer(
        cfg.get("dashboard", {}),
        cfg.get("mqtt", {}),
        cfg.get("storage.database_path", "./oneedge.db"),
        cfg.get("gateway", {}),
    )

    uvicorn.run(
        server.app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
