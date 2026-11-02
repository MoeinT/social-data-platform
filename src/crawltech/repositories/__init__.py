"""Operational repository interfaces and local SQLAlchemy implementation."""

from crawltech.repositories.interfaces import OperationalRepository
from crawltech.repositories.sqlalchemy import SqlAlchemyOperationalRepository

__all__ = ["OperationalRepository", "SqlAlchemyOperationalRepository"]
