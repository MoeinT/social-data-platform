"""SQLAlchemy repository for local PostgreSQL and SQLite-backed tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from crawltech.adapters.storage import StoredImage
from crawltech.models import (
    AnalysisResult,
    Author,
    AuthorSegmentAssignment,
    BoundingBox,
    CrawlBatch,
    CrawlRun,
    DataQualityResult,
    DetectedAttribute,
    Image,
    Post,
    PostSegmentAssignment,
    Segment,
    SocialNetwork,
    post_images,
)
from crawltech.models.schemas import AnalysisOutput, CrawledAuthor, CrawledPost


def _as_utc(value: datetime) -> datetime:
    """Normalize timezone-naive SQLite timestamps and aware DB values to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqlAlchemyOperationalRepository:
    """Persist operational records with content keys and transaction-scoped writes."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def start_run(self) -> str:
        """Create a crawl-run record and return its stable identifier."""
        run = CrawlRun()
        with self._session_factory() as session, session.begin():
            session.add(run)
            session.flush()
            run_id = str(run.id)
        return run_id

    def finish_run(self, run_id: str, status: str, posts_seen: int, images_seen: int) -> None:
        """Set terminal run state and observed input counts."""
        with self._session_factory() as session, session.begin():
            run = session.get(CrawlRun, run_id)
            if run is None:
                raise LookupError(f"crawl run {run_id} does not exist")
            run.status = status
            run.finished_at = datetime.now(UTC)
            run.posts_seen = posts_seen
            run.images_seen = images_seen

    def record_batch(
        self, run_id: str, batch_number: int, author_ids: Sequence[str], status: str
    ) -> None:
        """Create or update a bounded batch state so a task retry is idempotent."""
        with self._session_factory() as session, session.begin():
            batch = session.execute(
                select(CrawlBatch).where(
                    CrawlBatch.run_id == run_id, CrawlBatch.batch_number == batch_number
                )
            ).scalar_one_or_none()
            if batch is None:
                batch = CrawlBatch(
                    id=str(uuid4()),
                    run_id=run_id,
                    batch_number=batch_number,
                    author_ids=list(author_ids),
                )
                session.add(batch)
            batch.author_ids = list(author_ids)
            batch.status = status

    def upsert_author(self, author: CrawledAuthor) -> str:
        """Insert or refresh network-scoped author metadata."""
        with self._session_factory() as session, session.begin():
            network = session.execute(
                select(SocialNetwork).where(SocialNetwork.name == author.network)
            ).scalar_one_or_none()
            if network is None:
                network = SocialNetwork(name=author.network)
                session.add(network)
                session.flush()
            record = session.execute(
                select(Author).where(
                    Author.network_id == network.id, Author.external_id == author.external_id
                )
            ).scalar_one_or_none()
            if record is None:
                record = Author(
                    id=str(uuid4()),
                    network_id=network.id,
                    external_id=author.external_id,
                    display_name=author.display_name,
                    profile_url=str(author.profile_url),
                    metadata_json=author.metadata,
                )
                session.add(record)
            else:
                record.display_name = author.display_name
                record.profile_url = str(author.profile_url)
                record.metadata_json = author.metadata
            session.flush()
            author_id = str(record.id)
        return author_id

    def upsert_post(self, author_id: str, post: CrawledPost) -> tuple[str, bool]:
        """Insert or refresh network-scoped post metadata, returning whether new."""
        with self._session_factory() as session, session.begin():
            author = session.get(Author, author_id)
            if author is None:
                raise LookupError(f"author {author_id} does not exist")
            network = session.get(SocialNetwork, author.network_id)
            if network is None or network.name != post.network:
                raise ValueError("post network does not match persisted author network")
            record = session.execute(
                select(Post).where(
                    Post.network_id == author.network_id, Post.external_id == post.external_id
                )
            ).scalar_one_or_none()
            created = record is None
            if record is None:
                record = Post(
                    id=str(uuid4()),
                    network_id=author.network_id,
                    author_id=author_id,
                    external_id=post.external_id,
                    published_at=post.published_at,
                    caption=post.caption,
                    metadata_json=post.metadata,
                )
                session.add(record)
            else:
                if record.author_id != author_id:
                    raise ValueError("post external identifier is already linked to another author")
                record.published_at = post.published_at
                record.caption = post.caption
                record.metadata_json = post.metadata
            session.flush()
            post_id = record.id
        return post_id, created

    def upsert_image(self, image: StoredImage) -> str:
        """Deduplicate an image by its SHA-256 content hash."""
        with self._session_factory() as session, session.begin():
            record = session.execute(
                select(Image).where(Image.sha256 == image.sha256)
            ).scalar_one_or_none()
            if record is None:
                record = Image(
                    id=str(uuid4()),
                    sha256=image.sha256,
                    storage_uri=image.storage_uri,
                    media_type=image.media_type,
                )
                session.add(record)
            else:
                record.storage_uri = image.storage_uri
                record.media_type = image.media_type
            session.flush()
            image_id = str(record.id)
        return image_id

    def link_image(self, post_id: str, image_id: str, ordinal: int, source_url: str) -> None:
        """Create a post-image edge once; repeated links remain harmless on retries."""
        with self._session_factory() as session, session.begin():
            existing = session.execute(
                select(post_images.c.post_id).where(
                    and_(post_images.c.post_id == post_id, post_images.c.image_id == image_id)
                )
            ).first()
            if existing is None:
                session.execute(
                    post_images.insert().values(
                        post_id=post_id,
                        image_id=image_id,
                        ordinal=ordinal,
                        source_url=source_url,
                    )
                )

    def save_analysis(self, image_id: str, result: AnalysisOutput) -> bool:
        """Persist a single immutable image/analyzer-version result if not present."""
        with self._session_factory() as session, session.begin():
            existing = session.execute(
                select(AnalysisResult).where(
                    AnalysisResult.image_id == image_id,
                    AnalysisResult.analyzer_name == result.analyzer_name,
                    AnalysisResult.analyzer_version == result.analyzer_version,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False
            analysis = AnalysisResult(
                id=str(uuid4()),
                image_id=image_id,
                analyzer_name=result.analyzer_name,
                analyzer_version=result.analyzer_version,
            )
            analysis.attributes = [
                DetectedAttribute(
                    category=attribute.category,
                    value=attribute.value,
                    confidence=attribute.confidence,
                )
                for attribute in result.attributes
            ]
            analysis.bounding_boxes = [
                BoundingBox(
                    label=box.label,
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                    confidence=box.confidence,
                )
                for box in result.bounding_boxes
            ]
            session.add(analysis)
        return True

    def has_analysis(self, image_id: str, analyzer_name: str, analyzer_version: str) -> bool:
        """Check the immutable image/analyzer key before spending analyzer work."""
        with self._session_factory() as session:
            result = session.execute(
                select(AnalysisResult.id).where(
                    AnalysisResult.image_id == image_id,
                    AnalysisResult.analyzer_name == analyzer_name,
                    AnalysisResult.analyzer_version == analyzer_version,
                )
            ).first()
            return result is not None

    def assign_author_segment(
        self,
        author_id: str,
        segment_name: str,
        source: str,
        assigned_by: str,
        reason: str,
        assigned_at: datetime | None = None,
    ) -> None:
        """Idempotently version one author/segment membership without deleting history."""
        self._assign_segment(
            AuthorSegmentAssignment,
            "author_id",
            author_id,
            segment_name,
            source,
            assigned_by,
            reason,
            assigned_at,
        )

    def assign_post_segment(
        self,
        post_id: str,
        segment_name: str,
        source: str,
        assigned_by: str,
        reason: str,
        assigned_at: datetime | None = None,
    ) -> None:
        """Idempotently version one explicit post-level segment override."""
        self._assign_segment(
            PostSegmentAssignment,
            "post_id",
            post_id,
            segment_name,
            source,
            assigned_by,
            reason,
            assigned_at,
        )

    def remove_author_segment(
        self, author_id: str, segment_name: str, effective_at: datetime | None = None
    ) -> None:
        """Close an active author membership while retaining its historical row."""
        self._remove_segment(
            AuthorSegmentAssignment, "author_id", author_id, segment_name, effective_at
        )

    def remove_post_segment(
        self, post_id: str, segment_name: str, effective_at: datetime | None = None
    ) -> None:
        """Close an active post override while retaining its historical row."""
        self._remove_segment(PostSegmentAssignment, "post_id", post_id, segment_name, effective_at)

    def _remove_segment(
        self,
        assignment_model: type[AuthorSegmentAssignment] | type[PostSegmentAssignment],
        entity_column: str,
        entity_id: str,
        segment_name: str,
        effective_at: datetime | None,
    ) -> None:
        """Close the matching active assignment with a non-overlapping timestamp."""
        with self._session_factory() as session, session.begin():
            entity_filter = getattr(assignment_model, entity_column) == entity_id
            current = session.execute(
                select(assignment_model)
                .join(Segment)
                .where(
                    entity_filter,
                    Segment.name == segment_name,
                    assignment_model.valid_to.is_(None),
                )
            ).scalar_one_or_none()
            if current is None:
                return
            end_at = _as_utc(effective_at or datetime.now(UTC))
            current_start = _as_utc(current.valid_from)
            if end_at <= current_start:
                end_at = current_start + timedelta(microseconds=1)
            current.valid_to = end_at

    def _assign_segment(
        self,
        assignment_model: type[AuthorSegmentAssignment] | type[PostSegmentAssignment],
        entity_column: str,
        entity_id: str,
        segment_name: str,
        source: str,
        assigned_by: str,
        reason: str,
        assigned_at: datetime | None,
    ) -> None:
        if source not in {"manual", "automated"}:
            raise ValueError("assignment source must be 'manual' or 'automated'")
        effective_at = assigned_at or datetime.now(UTC)
        with self._session_factory() as session, session.begin():
            segment = session.execute(
                select(Segment).where(Segment.name == segment_name)
            ).scalar_one_or_none()
            if segment is None:
                segment = Segment(name=segment_name)
                session.add(segment)
                session.flush()
            entity_filter = getattr(assignment_model, entity_column) == entity_id
            current = session.execute(
                select(assignment_model).where(
                    entity_filter,
                    assignment_model.segment_id == segment.id,
                    assignment_model.valid_to.is_(None),
                )
            ).scalar_one_or_none()
            if current is not None and (
                current.source,
                current.assigned_by,
                current.reason,
            ) == (source, assigned_by, reason):
                return
            if current is not None:
                effective_at = _as_utc(effective_at)
                current_start = _as_utc(current.valid_from)
                if effective_at <= current_start:
                    effective_at = current_start + timedelta(microseconds=1)
                current.valid_to = effective_at
            assignment = assignment_model(
                id=str(uuid4()),
                **{entity_column: entity_id},
                segment_id=segment.id,
                source=source,
                assigned_by=assigned_by,
                reason=reason,
                valid_from=effective_at,
            )
            session.add(assignment)

    def current_author_segment_ids(self, author_id: str) -> set[int]:
        """Return the author's currently active segment identifiers."""
        with self._session_factory() as session:
            segment_ids = session.execute(
                select(AuthorSegmentAssignment.segment_id).where(
                    AuthorSegmentAssignment.author_id == author_id,
                    AuthorSegmentAssignment.valid_to.is_(None),
                )
            ).scalars()
            return set(segment_ids)

    def persist_quality_result(
        self, run_id: str, check_name: str, status: str, details: dict[str, object]
    ) -> None:
        """Create or refresh one run/check result so task retries remain idempotent."""
        with self._session_factory() as session, session.begin():
            result = session.execute(
                select(DataQualityResult).where(
                    DataQualityResult.run_id == run_id,
                    DataQualityResult.check_name == check_name,
                )
            ).scalar_one_or_none()
            if result is None:
                result = DataQualityResult(
                    id=str(uuid4()), run_id=run_id, check_name=check_name, status=status
                )
                session.add(result)
            result.status = status
            result.details = details

    def quality_counts(self, run_id: str) -> tuple[int, int]:
        """Return passed and failed quality-check counts for a run."""
        with self._session_factory() as session:
            results = session.execute(
                select(DataQualityResult.status).where(DataQualityResult.run_id == run_id)
            ).scalars()
            statuses = list(results)
        return statuses.count("passed"), statuses.count("failed")
