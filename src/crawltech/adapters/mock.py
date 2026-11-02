"""Deterministic crawler and analyzer implementations for local execution."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crawltech.models.schemas import (
    AnalysisOutput,
    BoundingBoxInput,
    CrawledAuthor,
    CrawledPost,
    DetectedAttributeInput,
    ImageReference,
)


class MockCrawler:
    """Return a small realistic catalog with varied image cardinality."""

    _AUTHOR_PROFILES = (
        ("nina-style", "Nina Laurent", ["luxury-fashion"]),
        ("studio-arc", "Studio Arc", ["luxury-fashion", "design"]),
        ("maison-rose", "Maison Rose", ["luxury-fashion", "beauty"]),
        ("field-notes", "Field Notes", ["design"]),
        ("atelier-north", "Atelier North", ["luxury-fashion"]),
        ("object-study", "Object Study", ["design", "beauty"]),
    )

    def __init__(self) -> None:
        self._authors = [
            CrawledAuthor(
                network="mockgram",
                external_id=external_id,
                display_name=display_name,
                profile_url=f"https://social.example.test/{external_id}",
                metadata={"segments": segments, "followers": 18400 + (index * 3917)},
            )
            for index, (external_id, display_name, segments) in enumerate(self._AUTHOR_PROFILES)
        ]

    def discover_authors(self) -> Sequence[CrawledAuthor]:
        """Return the bounded mock catalog; production crawlers can paginate here."""
        return self._authors

    def crawl_posts(self, author: CrawledAuthor) -> Sequence[CrawledPost]:
        """Return two recent posts, including a no-image post for quality coverage."""
        now = datetime.now(UTC)
        author_index = next(
            index
            for index, profile in enumerate(self._AUTHOR_PROFILES)
            if profile[0] == author.external_id
        )
        first_url = "https://images.example.test/products/leather-tote.png"
        second_url = f"https://images.example.test/products/editorial-{author_index}.png"
        image_references = [
            ImageReference(source_url=first_url),
            ImageReference(source_url=second_url),
        ]
        first_images = image_references if author_index % 2 == 0 else image_references[:1]
        second_images = [] if author_index == 2 else image_references[1:]
        return [
            CrawledPost(
                network=author.network,
                author_external_id=author.external_id,
                external_id=f"{author.external_id}-post-01",
                published_at=now - timedelta(days=1 + author_index),
                caption="A considered study in material, silhouette and everyday objects.",
                metadata={"likes": 1200 + author_index * 217, "comments": 34 + author_index},
                images=first_images,
            ),
            CrawledPost(
                network=author.network,
                author_external_id=author.external_id,
                external_id=f"{author.external_id}-post-02",
                published_at=now - timedelta(days=8 + author_index),
                caption="Notes from the latest collection preview.",
                metadata={"likes": 800 + author_index * 113, "comments": 18 + author_index},
                images=second_images,
            ),
        ]


class MockAnalyzer:
    """Produce realistic-looking but synthetic labels and normalized detections."""

    name = "mock-vision"
    version = "1.0.0"

    def analyze(self, storage_uri: str) -> AnalysisOutput:
        """Generate repeatable output from a local file reference without CV services."""
        file_path = Path(storage_uri)
        image_digest = file_path.stem
        category = "handbag" if int(image_digest[-1], 16) % 2 == 0 else "outerwear"
        color = "black" if int(image_digest[-2], 16) % 2 == 0 else "ivory"
        return AnalysisOutput(
            analyzer_name=self.name,
            analyzer_version=self.version,
            attributes=[
                DetectedAttributeInput(category="product_type", value=category, confidence=0.94),
                DetectedAttributeInput(category="color", value=color, confidence=0.88),
            ],
            bounding_boxes=[
                BoundingBoxInput(
                    label=category,
                    x=0.16,
                    y=0.12,
                    width=0.62,
                    height=0.73,
                    confidence=0.91,
                )
            ],
        )
