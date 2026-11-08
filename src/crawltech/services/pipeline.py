"""Ingestion business logic and local orchestration entry point."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from crawltech.adapters.interfaces import Analyzer, Crawler, ImageStorage
from crawltech.models.schemas import CrawledAuthor
from crawltech.repositories.interfaces import OperationalRepository
from crawltech.services.quality import DataQualityService
from crawltech.warehouses.interfaces import Warehouse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchReport:
    """Small counters returned from a bounded author batch."""

    batch_number: int
    authors_seen: int
    posts_seen: int
    images_seen: int


@dataclass(frozen=True)
class PipelineReport:
    """Summary of one complete local ingestion and analytics run."""

    run_id: str
    batches: int
    authors_seen: int
    posts_seen: int
    images_seen: int
    trend_rows: int


class IngestionService:
    """Coordinate adapters and repository operations for bounded author batches."""

    def __init__(
        self,
        crawler: Crawler,
        image_storage: ImageStorage,
        analyzer: Analyzer,
        repository: OperationalRepository,
    ) -> None:
        self._crawler = crawler
        self._image_storage = image_storage
        self._analyzer = analyzer
        self._repository = repository

    def discover_batches(self, batch_size: int) -> list[list[CrawledAuthor]]:
        """Discover eligible authors and return stable, bounded task payloads."""
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")
        authors = list(self._crawler.discover_authors())
        return [
            authors[offset : offset + batch_size] for offset in range(0, len(authors), batch_size)
        ]

    def process_batch(
        self, run_id: str, batch_number: int, authors: Sequence[CrawledAuthor]
    ) -> BatchReport:
        """Persist one retryable batch; repeated execution does not duplicate facts."""
        external_ids = [author.external_id for author in authors]
        self._repository.record_batch(run_id, batch_number, external_ids, "running")
        posts_seen = 0
        images_seen = 0
        try:
            for author in authors:
                author_id = self._repository.upsert_author(author)
                segments = author.metadata.get("segments", [])
                if isinstance(segments, list):
                    for segment in segments:
                        if isinstance(segment, str) and segment:
                            self._repository.assign_author_segment(
                                author_id,
                                segment,
                                source="automated",
                                assigned_by="mock-crawler",
                                reason="crawler profile metadata",
                            )
                for post in self._crawler.crawl_posts(author):
                    if post.author_external_id != author.external_id:
                        raise ValueError("crawler returned a post for a different author")
                    post_id, _ = self._repository.upsert_post(author_id, post)
                    posts_seen += 1
                    for ordinal, image_reference in enumerate(post.images):
                        stored_image = self._image_storage.download(image_reference)
                        image_id = self._repository.upsert_image(stored_image)
                        self._repository.link_image(
                            post_id,
                            image_id,
                            ordinal,
                            str(image_reference.source_url),
                        )
                        images_seen += 1
                        if not self._repository.has_analysis(
                            image_id, self._analyzer.name, self._analyzer.version
                        ):
                            output = self._analyzer.analyze(stored_image.storage_uri)
                            self._repository.save_analysis(image_id, output)
            self._repository.record_batch(run_id, batch_number, external_ids, "succeeded")
        except Exception:
            self._repository.record_batch(run_id, batch_number, external_ids, "failed")
            logger.exception(
                "Author batch failed",
                extra={"run_id": run_id, "batch_number": batch_number},
            )
            raise
        logger.info(
            "Author batch completed",
            extra={
                "run_id": run_id,
                "batch_number": batch_number,
                "authors_seen": len(authors),
                "posts_seen": posts_seen,
                "images_seen": images_seen,
            },
        )
        return BatchReport(batch_number, len(authors), posts_seen, images_seen)


def run_local_pipeline(
    ingestion: IngestionService,
    quality: DataQualityService,
    warehouse: Warehouse,
    repository: OperationalRepository,
    batch_size: int,
) -> PipelineReport:
    """Execute the complete mock pipeline without Airflow or external credentials."""
    run_id = repository.start_run()
    reports: list[BatchReport] = []
    try:
        batches = ingestion.discover_batches(batch_size)
        for batch_number, authors in enumerate(batches):
            reports.append(ingestion.process_batch(run_id, batch_number, authors))
        quality.run(run_id)
        trend_rows = warehouse.build_trend_dataset(run_id)
        if not warehouse.validate_trend_dataset():
            raise ValueError("trend-ready dataset failed final validation")
        posts_seen = sum(report.posts_seen for report in reports)
        images_seen = sum(report.images_seen for report in reports)
        repository.finish_run(run_id, "succeeded", posts_seen, images_seen)
        return PipelineReport(
            run_id=run_id,
            batches=len(reports),
            authors_seen=sum(report.authors_seen for report in reports),
            posts_seen=posts_seen,
            images_seen=images_seen,
            trend_rows=trend_rows,
        )
    except Exception:
        posts_seen = sum(report.posts_seen for report in reports)
        images_seen = sum(report.images_seen for report in reports)
        repository.finish_run(run_id, "failed", posts_seen, images_seen)
        logger.exception("Pipeline run failed", extra={"run_id": run_id})
        raise
