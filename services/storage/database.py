"""SQLite storage using SQLAlchemy."""
from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path
from typing import Generator

from sqlalchemy import Boolean, JSON, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

Base = declarative_base()
_SessionFactory: sessionmaker[Session] | None = None


class MetricReading(Base):
    """Represents a single telemetry sample emitted by an edge device."""

    __tablename__ = "metric_readings"

    id = Column(Integer, primary_key=True)
    topic = Column(String, nullable=False, index=True)
    metric = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)


class AlertEvent(Base):
    """Captures alerts raised by analytics rules or anomaly detectors."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    topic = Column(String, nullable=False, index=True)
    rule = Column(String, nullable=False, index=True)
    severity = Column(String, default="warning")
    message = Column(String, nullable=False)
    details = Column(JSON, nullable=True)
    acknowledged = Column(Integer, default=0)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)


class HealthSnapshot(Base):
    """Stores periodic health reports for oneEdge services."""

    __tablename__ = "health_snapshots"

    id = Column(Integer, primary_key=True)
    component = Column(String, nullable=False)
    status = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)


class ProvisionedDevice(Base):
    """Represents a device that has been provisioned into the gateway."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    device_type = Column(String, nullable=True)
    location = Column(String, nullable=True)
    status = Column(String, nullable=False, default="inactive")
    auth_method = Column(String, nullable=False, default="pre_shared_key")
    auth_id = Column(String, nullable=True)
    allowed_endpoints = Column(JSON, nullable=True)
    rotation_interval_hours = Column(Integer, nullable=True)
    current_secret_hash = Column(String, nullable=True)
    device_static_secret_hash = Column(String, nullable=True)
    hardware_fingerprint_hash = Column(String, nullable=True)
    device_public_key = Column(String, nullable=True)
    policy_document = Column(JSON, nullable=True)
    quarantined = Column(Boolean, nullable=False, default=False)
    provisioned_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=True)
    last_auth_at = Column(DateTime, nullable=True)
    last_rotated_at = Column(DateTime, nullable=True)
    challenge_nonce = Column(String, nullable=True)
    challenge_expires_at = Column(DateTime, nullable=True)
    failed_auth_attempts = Column(Integer, nullable=False, default=0)
    attributes = Column(JSON, nullable=True)


def _get_engine(db_path: str) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True, connect_args={"check_same_thread": False})
    return engine


def init_storage(db_path: str) -> None:
    """Initialise the SQLite database and session factory."""

    global _SessionFactory
    engine = _get_engine(db_path)
    Base.metadata.create_all(engine)
    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


@contextlib.contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope for database operations."""

    if _SessionFactory is None:
        raise RuntimeError("Storage not initialised; call init_storage first.")
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "MetricReading",
    "AlertEvent",
    "HealthSnapshot",
    "ProvisionedDevice",
    "init_storage",
    "session_scope",
]
