from __future__ import annotations

import datetime as dt

from services.common.logger import logger
from services.storage.database import AlertEvent, MetricReading, session_scope


def purge_expired(retention_config: dict[str, int | float | None]) -> dict[str, int]:
    """Remove historical records beyond configured retention windows."""

    metrics_days = int(retention_config.get("metrics_days", 30) or 0)
    alerts_days = int(retention_config.get("alerts_days", 90) or 0)
    deleted = {"metric_readings": 0, "alerts": 0}
    now = dt.datetime.utcnow()
    with session_scope() as session:
        if metrics_days > 0:
            cutoff = now - dt.timedelta(days=metrics_days)
            result = (
                session.query(MetricReading)
                .filter(MetricReading.timestamp < cutoff)
                .delete(synchronize_session=False)
            )
            deleted["metric_readings"] = result or 0
        if alerts_days > 0:
            cutoff = now - dt.timedelta(days=alerts_days)
            result = (
                session.query(AlertEvent)
                .filter(AlertEvent.timestamp < cutoff)
                .delete(synchronize_session=False)
            )
            deleted["alerts"] = result or 0
    if deleted["metric_readings"] or deleted["alerts"]:
        logger.info("Retention purge complete: {}", deleted)
    return deleted


__all__ = ["purge_expired"]
