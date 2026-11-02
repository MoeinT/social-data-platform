"""End-to-end behavior tests for ingestion, retries, quality, and trend output."""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crawltech.adapters import MockAnalyzer
from crawltech.models import (
    AnalysisResult,
    Author,
    BoundingBox,
    DetectedAttribute,
    Image,
    Post,
    TrendMetric,
    post_images,
)
from crawltech.models.schemas import AnalysisOutput, DetectedAttributeInput
from crawltech.services import DataQualityError, run_local_pipeline


def test_end_to_end_pipeline_is_idempotent_and_stores_files(components) -> None:
    """Repeated full runs retain unique posts/images/analyses and materialize trends."""
    first = run_local_pipeline(
        components.ingestion, components.quality, components.warehouse, components.repository, 2
    )
    second = run_local_pipeline(
        components.ingestion, components.quality, components.warehouse, components.repository, 2
    )
    with Session(components.engine) as session:
        counts = {
            "authors": session.execute(select(func.count(Author.id))).scalar_one(),
            "posts": session.execute(select(func.count(Post.id))).scalar_one(),
            "images": session.execute(select(func.count(Image.id))).scalar_one(),
            "analyses": session.execute(select(func.count(AnalysisResult.id))).scalar_one(),
            "attributes": session.execute(select(func.count(DetectedAttribute.id))).scalar_one(),
            "boxes": session.execute(select(func.count(BoundingBox.id))).scalar_one(),
            "links": session.execute(select(func.count()).select_from(post_images)).scalar_one(),
        }
        image_uris = session.execute(select(Image.storage_uri)).scalars().all()
        no_image_posts = session.execute(
            select(Post.id)
            .select_from(Post.__table__.outerjoin(post_images, Post.id == post_images.c.post_id))
            .where(post_images.c.post_id.is_(None))
        ).all()

    assert first.batches == 3
    assert first.authors_seen == 6
    assert first.posts_seen == 12
    assert first.images_seen == 14
    assert first.trend_rows > 0
    assert second.trend_rows == first.trend_rows
    assert counts == {
        "authors": 6,
        "posts": 12,
        "images": 7,
        "analyses": 7,
        "attributes": 14,
        "boxes": 7,
        "links": 14,
    }
    assert len(no_image_posts) == 1
    assert all(Path(uri).is_file() for uri in image_uris)
    assert all(Path(uri).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for uri in image_uris)


def test_quality_fails_for_missing_local_image_files(components) -> None:
    """Image-less posts are acceptable, but persisted files disappearing is blocking."""
    run_local_pipeline(
        components.ingestion, components.quality, components.warehouse, components.repository, 2
    )
    with Session(components.engine) as session:
        uri = session.execute(select(Image.storage_uri).limit(1)).scalar_one()
    Path(uri).unlink()
    run_id = components.repository.start_run()
    with pytest.raises(DataQualityError, match="quality check"):
        components.quality.run(run_id)


def test_failed_batch_can_be_retried_without_duplicate_data(components) -> None:
    """A transient analyzer failure marks the batch failed, then safely resumes."""

    class FlakyAnalyzer(MockAnalyzer):
        def __init__(self) -> None:
            self.attempts = 0

        def analyze(self, storage_uri: str) -> AnalysisOutput:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient analyzer outage")
            return super().analyze(storage_uri)

    from crawltech.services import IngestionService

    flaky = FlakyAnalyzer()
    service = IngestionService(components.crawler, components.storage, flaky, components.repository)
    run_id = components.repository.start_run()
    authors = [components.crawler.discover_authors()[0]]
    with pytest.raises(RuntimeError, match="transient analyzer outage"):
        service.process_batch(run_id, 0, authors)
    result = service.process_batch(run_id, 0, authors)

    assert result.posts_seen == 2
    assert result.images_seen == 3
    assert flaky.attempts == 3
    with Session(components.engine) as session:
        assert session.execute(select(func.count(Post.id))).scalar_one() == 2
        assert session.execute(select(func.count(Image.id))).scalar_one() == 2
        assert session.execute(select(func.count(AnalysisResult.id))).scalar_one() == 2


def test_trend_counts_a_post_once_when_multiple_images_match(components) -> None:
    """Two matching images from one carousel contribute one post to the trend."""

    class UniformAnalyzer:
        name = "uniform-test"
        version = "1"

        def analyze(self, storage_uri: str) -> AnalysisOutput:
            return AnalysisOutput(
                analyzer_name=self.name,
                analyzer_version=self.version,
                attributes=[
                    DetectedAttributeInput(category="product_type", value="bag", confidence=0.9)
                ],
            )

    from crawltech.database import create_session_factory
    from crawltech.services import IngestionService
    from crawltech.warehouses import LocalWarehouse

    service = IngestionService(
        components.crawler, components.storage, UniformAnalyzer(), components.repository
    )
    run_id = components.repository.start_run()
    service.process_batch(run_id, 0, [components.crawler.discover_authors()[0]])
    session_factory = create_session_factory(components.engine)
    warehouse = LocalWarehouse(session_factory, "uniform-test", "1")
    warehouse.build_trend_dataset(run_id)
    with Session(components.engine) as session:
        metrics = (
            session.execute(select(TrendMetric).where(TrendMetric.category == "product_type"))
            .scalars()
            .all()
        )

    assert len(metrics) == 2
    assert sum(metric.post_count for metric in metrics) == 2
    assert all(metric.post_count == 1 and metric.author_count == 1 for metric in metrics)
