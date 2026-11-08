"""Domain payload validation and persistence behavior tests."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crawltech.models import (
    AnalysisResult,
    AuthorSegmentAssignment,
    BoundingBox,
    DetectedAttribute,
    Image,
    Segment,
)
from crawltech.models.schemas import (
    AnalysisOutput,
    BoundingBoxInput,
    CrawledPost,
    DetectedAttributeInput,
)


def test_bounding_box_rejects_coordinates_outside_image() -> None:
    """Coordinates are normalized and must not extend past the image boundary."""
    with pytest.raises(ValidationError):
        BoundingBoxInput(label="bag", x=0.8, y=0.1, width=0.3, height=0.4, confidence=0.9)


def test_post_allows_zero_or_multiple_images() -> None:
    """Posts without images and carousel posts are both valid crawler outputs."""
    base = {
        "network": "mockgram",
        "author_external_id": "studio-arc",
        "external_id": "post-1",
        "published_at": datetime.now(UTC),
    }
    no_images = CrawledPost(**base)
    multiple_images = CrawledPost(
        **base,
        images=[
            {"source_url": "https://images.example.test/1.png"},
            {"source_url": "https://images.example.test/2.png"},
        ],
    )
    assert no_images.images == []
    assert len(multiple_images.images) == 2


def test_analyzer_output_validates_confidence_and_bounding_boxes() -> None:
    """Analyzer payloads reject invalid confidence before they reach SQL."""
    with pytest.raises(ValidationError):
        DetectedAttributeInput(category="color", value="ivory", confidence=1.1)


def test_assignment_changes_keep_history_and_allow_multiple_segments(components) -> None:
    """Manual updates close old rows while unrelated segment memberships remain active."""
    author = components.crawler.discover_authors()[0]
    author_id = components.repository.upsert_author(author)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    components.repository.assign_author_segment(
        author_id, "luxury-fashion", "automated", "crawler", "profile", start
    )
    components.repository.assign_author_segment(
        author_id, "design", "manual", "analyst", "curated", start
    )
    components.repository.assign_author_segment(
        author_id,
        "luxury-fashion",
        "manual",
        "analyst",
        "reviewed",
        start + timedelta(days=1),
    )
    components.repository.remove_author_segment(
        author_id, "luxury-fashion", start + timedelta(days=2)
    )

    with Session(components.engine) as session:
        history = session.execute(
            select(AuthorSegmentAssignment, Segment.name)
            .join(Segment)
            .where(AuthorSegmentAssignment.author_id == author_id)
        ).all()
    luxury_history = [row for row, name in history if name == "luxury-fashion"]
    design_history = [row for row, name in history if name == "design"]
    assert len(luxury_history) == 2
    assert all(row.valid_to is not None for row in luxury_history)
    assert len(design_history) == 1
    assert design_history[0].valid_to is None
    assert components.repository.current_author_segment_ids(author_id) == {
        design_history[0].segment_id
    }


def test_multiple_analyzer_versions_are_preserved(components) -> None:
    """A new model version creates a distinct immutable result for the same image."""
    components.ingestion.process_batch(
        components.repository.start_run(), 0, [components.crawler.discover_authors()[0]]
    )
    with Session(components.engine) as session:
        image_id = session.execute(select(Image.id).limit(1)).scalar_one()
    output = AnalysisOutput(
        analyzer_name="mock-vision",
        analyzer_version="2.0.0",
        attributes=[DetectedAttributeInput(category="product_type", value="bag", confidence=0.8)],
        bounding_boxes=[
            BoundingBoxInput(label="bag", x=0.1, y=0.1, width=0.5, height=0.6, confidence=0.8)
        ],
    )
    assert components.repository.save_analysis(image_id, output)
    assert not components.repository.save_analysis(image_id, output)
    with Session(components.engine) as session:
        versions = session.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.image_id == image_id)
        ).scalar_one()
        boxes = session.execute(select(func.count(BoundingBox.id))).scalar_one()
        attributes = session.execute(select(func.count(DetectedAttribute.id))).scalar_one()
    assert versions == 2
    assert boxes >= 2
    assert attributes >= 4
