"""SQL-backed local warehouse implementation for deterministic development."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from crawltech.models import (
    AnalysisResult,
    AuthorSegmentAssignment,
    DetectedAttribute,
    Image,
    Post,
    PostSegmentAssignment,
    SocialNetwork,
    TrendMetric,
    post_images,
)


class LocalWarehouse:
    """Materialize weekly trends locally; production targets Snowflake through the same port."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        analyzer_name: str = "mock-vision",
        analyzer_version: str = "1.0.0",
    ) -> None:
        self._session_factory = session_factory
        self._analyzer_name = analyzer_name
        self._analyzer_version = analyzer_version

    def build_trend_dataset(self, run_id: str) -> int:
        """Replace the local weekly aggregate with post-distinct trend metrics."""
        del run_id
        with self._session_factory() as session, session.begin():
            author_segments = self._current_author_segments(session)
            post_segments = self._current_post_segments(session)
            rows = session.execute(
                select(
                    Post.id,
                    Post.author_id,
                    Post.published_at,
                    SocialNetwork.name,
                    DetectedAttribute.category,
                    DetectedAttribute.value,
                )
                .select_from(Post)
                .join(SocialNetwork, SocialNetwork.id == Post.network_id)
                .join(post_images, post_images.c.post_id == Post.id)
                .join(Image, Image.id == post_images.c.image_id)
                .join(AnalysisResult, AnalysisResult.image_id == Image.id)
                .join(DetectedAttribute, DetectedAttribute.analysis_id == AnalysisResult.id)
                .where(
                    AnalysisResult.analyzer_name == self._analyzer_name,
                    AnalysisResult.analyzer_version == self._analyzer_version,
                    AnalysisResult.status == "succeeded",
                )
            ).all()
            grouped: dict[tuple[datetime, str, int, str, str], tuple[set[str], set[str]]] = (
                defaultdict(lambda: (set(), set()))
            )
            for post_id, author_id, published_at, network, category, value in rows:
                segment_ids = post_segments.get(post_id, author_segments.get(author_id, set()))
                for segment_id in segment_ids:
                    key = (
                        self._week_start(published_at),
                        network,
                        segment_id,
                        category,
                        value,
                    )
                    post_ids, author_ids = grouped[key]
                    post_ids.add(post_id)
                    author_ids.add(author_id)
            session.execute(delete(TrendMetric))
            session.add_all(
                [
                    TrendMetric(
                        window_start=window_start,
                        network=network,
                        segment_id=segment_id,
                        category=category,
                        value=value,
                        post_count=len(post_ids),
                        author_count=len(author_ids),
                    )
                    for (window_start, network, segment_id, category, value), (
                        post_ids,
                        author_ids,
                    ) in grouped.items()
                ]
            )
        return len(grouped)

    def validate_trend_dataset(self) -> bool:
        """Verify dimensions are unique and aggregate counts are nonnegative."""
        with self._session_factory() as session:
            metrics = session.execute(select(TrendMetric)).scalars().all()
        keys = {
            (row.window_start, row.network, row.segment_id, row.category, row.value)
            for row in metrics
        }
        return len(keys) == len(metrics) and all(
            row.post_count >= 0 and row.author_count >= 0 for row in metrics
        )

    @staticmethod
    def _current_author_segments(session: Session) -> dict[str, set[int]]:
        rows = session.execute(
            select(AuthorSegmentAssignment.author_id, AuthorSegmentAssignment.segment_id).where(
                AuthorSegmentAssignment.valid_to.is_(None)
            )
        ).all()
        segments: dict[str, set[int]] = defaultdict(set)
        for author_id, segment_id in rows:
            segments[author_id].add(segment_id)
        return segments

    @staticmethod
    def _current_post_segments(session: Session) -> dict[str, set[int]]:
        rows = session.execute(
            select(PostSegmentAssignment.post_id, PostSegmentAssignment.segment_id).where(
                PostSegmentAssignment.valid_to.is_(None)
            )
        ).all()
        segments: dict[str, set[int]] = defaultdict(set)
        for post_id, segment_id in rows:
            segments[post_id].add(segment_id)
        return segments

    @staticmethod
    def _week_start(published_at: datetime) -> datetime:
        """Normalize a publication timestamp to midnight UTC on its Monday."""
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        published_at = published_at.astimezone(UTC)
        monday = published_at.date() - timedelta(days=published_at.weekday())
        return datetime.combine(monday, time.min, tzinfo=UTC)
