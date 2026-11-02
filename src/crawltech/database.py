"""Database engine and session factory for the local operational store."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from crawltech.config import Settings, get_settings


def create_database_engine(settings: Settings | None = None) -> Engine:
    """Create a pre-ping SQLAlchemy engine from validated application settings."""
    active_settings = settings or get_settings()
    return create_engine(active_settings.database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create non-autocommit sessions; services own explicit transaction boundaries."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
