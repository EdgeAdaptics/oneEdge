"""SQLite storage using SQLAlchemy."""
from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path
from typing import Generator

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

Base = declarative_base()
_SessionFactory: sessionmaker[Session] | None = None


class MetricReading(Base):
    __tablename__ = "metric_readings"

    id = Column(Integer, primary_key=True)
    topic = Column(String, nullable=False, index=True)
    metric = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)


class AlertEvent(Base):
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
    __tablename__ = "health_snapshots"

    id = Column(Integer, primary_key=True)
    component = Column(String, nullable=False)
    status = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)


def _get_engine(db_path: str) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True, connect_args={"check_same_thread": False})
    return engine


def init_storage(db_path: str) -> None:
    global _SessionFactory
    engine = _get_engine(db_path)
    Base.metadata.create_all(engine)
    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


@contextlib.contextmanager
def session_scope() -> Generator[Session, None, None]:
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
    "init_storage",
    "session_scope",
]
