"""Persisted data quality checks for local ingestion output."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from crawltech.adapters.interfaces import ImageStorage
from crawltech.models import Author, Image, Post, post_images
from crawltech.repositories.interfaces import OperationalRepository

logger = logging.getLogger(__name__)


class DataQualityError(RuntimeError):
    """Raised when one or more blocking data quality checks fail."""


@dataclass(frozen=True)
class QualityReport:
    """Summary of persisted check outcomes."""

    passed: int
    failed: int
    posts_without_images: int
    posts_with_multiple_images: int
    missing_image_files: int
    orphan_references: int


class DataQualityService:
    """Check local file references and relational integrity after ingestion."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        repository: OperationalRepository,
        image_storage: ImageStorage,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository
        self._image_storage = image_storage

    def run(self, run_id: str) -> QualityReport:
        """Persist named quality results and raise on broken image or FK references."""
        with self._session_factory() as session:
            posts_without_images, posts_with_multiple_images = self._post_image_counts(session)
            missing_image_files = self._missing_files(session)
            orphan_references = self._orphan_reference_count(session)

        checks: list[tuple[str, bool, dict[str, object]]] = [
            (
                "image_files_exist",
                missing_image_files == 0,
                {"missing_image_files": missing_image_files},
            ),
            (
                "references_are_valid",
                orphan_references == 0,
                {"orphan_references": orphan_references},
            ),
            (
                "post_image_cardinality",
                True,
                {
                    "posts_without_images": posts_without_images,
                    "posts_with_multiple_images": posts_with_multiple_images,
                    "image_less_posts_are_allowed": True,
                },
            ),
        ]
        for name, passed, details in checks:
            self._repository.persist_quality_result(
                run_id, name, "passed" if passed else "failed", details
            )
        passed_count, failed_count = self._repository.quality_counts(run_id)
        report = QualityReport(
            passed=passed_count,
            failed=failed_count,
            posts_without_images=posts_without_images,
            posts_with_multiple_images=posts_with_multiple_images,
            missing_image_files=missing_image_files,
            orphan_references=orphan_references,
        )
        if failed_count:
            logger.error(
                "Data quality checks failed", extra={"run_id": run_id, "failed": failed_count}
            )
            raise DataQualityError(f"{failed_count} data quality check(s) failed")
        logger.info("Data quality checks passed", extra={"run_id": run_id, "passed": passed_count})
        return report

    @staticmethod
    def _post_image_counts(session: Session) -> tuple[int, int]:
        posts = session.execute(select(Post.id)).scalars().all()
        links = session.execute(select(post_images.c.post_id, post_images.c.image_id)).all()
        image_counts: dict[str, set[str]] = {}
        for post_id, image_id in links:
            image_counts.setdefault(post_id, set()).add(image_id)
        without_images = sum(post_id not in image_counts for post_id in posts)
        with_multiple = sum(len(image_counts.get(post_id, set())) > 1 for post_id in posts)
        return without_images, with_multiple

    def _missing_files(self, session: Session) -> int:
        image_uris = session.execute(select(Image.storage_uri)).scalars().all()
        missing = 0
        for uri in image_uris:
            try:
                missing += not self._image_storage.exists(uri)
            except OSError:
                logger.exception("Unable to verify image file", extra={"storage_uri": uri})
                missing += 1
        return missing

    @staticmethod
    def _orphan_reference_count(session: Session) -> int:
        missing_image = session.execute(
            select(post_images.c.image_id)
            .select_from(post_images.outerjoin(Image, Image.id == post_images.c.image_id))
            .where(Image.id.is_(None))
        ).all()
        missing_post = session.execute(
            select(post_images.c.post_id)
            .select_from(post_images.outerjoin(Post, Post.id == post_images.c.post_id))
            .where(Post.id.is_(None))
        ).all()
        missing_author = session.execute(
            select(Post.id)
            .select_from(Post.__table__.outerjoin(Author, Author.id == Post.author_id))
            .where(Author.id.is_(None))
        ).all()
        return len(missing_image) + len(missing_post) + len(missing_author)
