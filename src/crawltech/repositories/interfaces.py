"""Persistence contract consumed by domain services."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from crawltech.adapters.storage import StoredImage
from crawltech.models.schemas import AnalysisOutput, CrawledAuthor, CrawledPost


class OperationalRepository(Protocol):
    """Operations required by ingestion, assignment, and quality services."""

    def start_run(self) -> str: ...

    def finish_run(self, run_id: str, status: str, posts_seen: int, images_seen: int) -> None: ...

    def record_batch(
        self, run_id: str, batch_number: int, author_ids: Sequence[str], status: str
    ) -> None: ...

    def upsert_author(self, author: CrawledAuthor) -> str: ...

    def upsert_post(self, author_id: str, post: CrawledPost) -> tuple[str, bool]: ...

    def upsert_image(self, image: StoredImage) -> str: ...

    def link_image(self, post_id: str, image_id: str, ordinal: int, source_url: str) -> None: ...

    def save_analysis(self, image_id: str, result: AnalysisOutput) -> bool: ...

    def has_analysis(self, image_id: str, analyzer_name: str, analyzer_version: str) -> bool: ...

    def assign_author_segment(
        self,
        author_id: str,
        segment_name: str,
        source: str,
        assigned_by: str,
        reason: str,
        assigned_at: datetime | None = None,
    ) -> None: ...

    def assign_post_segment(
        self,
        post_id: str,
        segment_name: str,
        source: str,
        assigned_by: str,
        reason: str,
        assigned_at: datetime | None = None,
    ) -> None: ...

    def remove_author_segment(
        self, author_id: str, segment_name: str, effective_at: datetime | None = None
    ) -> None: ...

    def remove_post_segment(
        self, post_id: str, segment_name: str, effective_at: datetime | None = None
    ) -> None: ...

    def current_author_segment_ids(self, author_id: str) -> set[int]: ...

    def persist_quality_result(
        self, run_id: str, check_name: str, status: str, details: dict[str, object]
    ) -> None: ...

    def quality_counts(self, run_id: str) -> tuple[int, int]: ...
