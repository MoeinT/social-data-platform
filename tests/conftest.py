"""Shared deterministic local database and adapter fixtures."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from crawltech.adapters import LocalImageStorage, MockAnalyzer, MockCrawler
from crawltech.database import create_session_factory
from crawltech.models import Base
from crawltech.repositories import SqlAlchemyOperationalRepository
from crawltech.services import DataQualityService, IngestionService
from crawltech.warehouses import LocalWarehouse


@dataclass
class Components:
    """All services sharing one isolated test database and temporary image store."""

    engine: Engine
    repository: SqlAlchemyOperationalRepository
    crawler: MockCrawler
    storage: LocalImageStorage
    analyzer: MockAnalyzer
    ingestion: IngestionService
    quality: DataQualityService
    warehouse: LocalWarehouse


@pytest.fixture
def components(tmp_path: Path) -> Iterator[Components]:
    """Provide a clean SQLite schema and real local-file mock adapters."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    repository = SqlAlchemyOperationalRepository(session_factory)
    crawler = MockCrawler()
    storage = LocalImageStorage(tmp_path / "images")
    analyzer = MockAnalyzer()
    yield Components(
        engine=engine,
        repository=repository,
        crawler=crawler,
        storage=storage,
        analyzer=analyzer,
        ingestion=IngestionService(crawler, storage, analyzer, repository),
        quality=DataQualityService(session_factory, repository, storage),
        warehouse=LocalWarehouse(session_factory),
    )
    Base.metadata.drop_all(engine)
    engine.dispose()
