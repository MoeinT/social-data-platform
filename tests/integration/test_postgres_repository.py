"""Opt-in PostgreSQL-backed repository integration test."""

import os

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from crawltech.adapters import MockCrawler
from crawltech.database import create_session_factory
from crawltech.models import Author, Base
from crawltech.repositories import SqlAlchemyOperationalRepository


@pytest.mark.integration
def test_postgres_author_upsert_is_idempotent() -> None:
    """The local Postgres adapter enforces the same natural-key behavior as SQLite tests."""
    database_url = os.getenv("CRAWLTECH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set CRAWLTECH_TEST_DATABASE_URL to run PostgreSQL integration tests")
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    Base.metadata.create_all(engine)
    repository = SqlAlchemyOperationalRepository(create_session_factory(engine))
    try:
        author = MockCrawler().discover_authors()[0]
        first_id = repository.upsert_author(author)
        second_id = repository.upsert_author(author)
        with Session(engine) as session:
            count = session.execute(select(func.count(Author.id))).scalar_one()
        assert first_id == second_id
        assert count == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
