"""Application runtime assembly and local command-line entry point."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from crawltech.adapters import LocalImageStorage, MockAnalyzer, MockCrawler
from crawltech.config import Settings, get_settings
from crawltech.database import create_database_engine, create_session_factory
from crawltech.repositories import SqlAlchemyOperationalRepository
from crawltech.services import DataQualityService, IngestionService, PipelineReport
from crawltech.services.pipeline import run_local_pipeline
from crawltech.warehouses import LocalWarehouse


@dataclass
class Runtime:
    """Per-process application services and their owned SQLAlchemy engine."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    crawler: MockCrawler
    repository: SqlAlchemyOperationalRepository
    ingestion: IngestionService
    quality: DataQualityService
    warehouse: LocalWarehouse

    def close(self) -> None:
        """Release the database connection pool owned by this runtime."""
        self.engine.dispose()

    def __enter__(self) -> Runtime:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def create_runtime(settings: Settings | None = None) -> Runtime:
    """Construct the local adapters and services using validated configuration."""
    active_settings = settings or get_settings()
    engine = create_database_engine(active_settings)
    session_factory = create_session_factory(engine)
    crawler = MockCrawler()
    storage = LocalImageStorage(active_settings.image_storage_path)
    analyzer = MockAnalyzer()
    repository = SqlAlchemyOperationalRepository(session_factory)
    return Runtime(
        settings=active_settings,
        engine=engine,
        session_factory=session_factory,
        crawler=crawler,
        repository=repository,
        ingestion=IngestionService(crawler, storage, analyzer, repository),
        quality=DataQualityService(session_factory, repository, storage),
        warehouse=LocalWarehouse(session_factory, analyzer.name, analyzer.version),
    )


def run_pipeline() -> PipelineReport:
    """Run the complete local pipeline and close its connection pool afterward."""
    with create_runtime() as runtime:
        return run_local_pipeline(
            runtime.ingestion,
            runtime.quality,
            runtime.warehouse,
            runtime.repository,
            runtime.settings.crawl_batch_size,
        )


def main() -> None:
    """Run one local pipeline and emit a machine-readable run summary."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    report = run_pipeline()
    print(json.dumps(report.__dict__, sort_keys=True))


if __name__ == "__main__":
    main()
