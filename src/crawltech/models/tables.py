"""SQLAlchemy operational entities and constraints."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class AssignmentSource(StrEnum):
    """Provenance of a segment assignment."""

    MANUAL = "manual"
    AUTOMATED = "automated"


post_images = Table(
    "post_images",
    Base.metadata,
    Column("post_id", String(36), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("image_id", String(36), ForeignKey("images.id", ondelete="CASCADE"), primary_key=True),
    Column("ordinal", Integer, nullable=False),
    Column("source_url", Text, nullable=False),
    UniqueConstraint("post_id", "ordinal", name="uq_post_image_ordinal"),
)


class SocialNetwork(Base):
    """A source social network such as the mock photo-sharing network."""

    __tablename__ = "social_networks"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)

    authors = relationship("Author", back_populates="network")
    posts = relationship("Post", back_populates="network")


class Author(Base):
    """A social account, keyed by its network-scoped external identifier."""

    __tablename__ = "authors"
    __table_args__ = (
        UniqueConstraint("network_id", "external_id", name="uq_author_network_external"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    network_id = Column(Integer, ForeignKey("social_networks.id"), nullable=False, index=True)
    external_id = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    profile_url = Column(Text, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)

    network = relationship("SocialNetwork", back_populates="authors")
    posts = relationship("Post", back_populates="author")
    segment_assignments = relationship("AuthorSegmentAssignment", back_populates="author")


class Post(Base):
    """A network post; uniqueness prevents repeat crawls from duplicating it."""

    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("network_id", "external_id", name="uq_post_network_external"),
        Index("ix_posts_published_at", "published_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    network_id = Column(Integer, ForeignKey("social_networks.id"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("authors.id"), nullable=False, index=True)
    external_id = Column(String(200), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    caption = Column(Text, nullable=False, default="")
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)

    network = relationship("SocialNetwork", back_populates="posts")
    author = relationship("Author", back_populates="posts")
    images = relationship("Image", secondary=post_images, back_populates="posts")
    segment_assignments = relationship("PostSegmentAssignment", back_populates="post")


class Image(Base):
    """A content-addressed image; binary data remains in the storage adapter."""

    __tablename__ = "images"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sha256 = Column(String(64), nullable=False, unique=True)
    storage_uri = Column(Text, nullable=False)
    media_type = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    posts = relationship("Post", secondary=post_images, back_populates="images")
    analyses = relationship("AnalysisResult", back_populates="image")


class AnalysisResult(Base):
    """An immutable result per image and analyzer version."""

    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint(
            "image_id", "analyzer_name", "analyzer_version", name="uq_image_analyzer_version"
        ),
        CheckConstraint("status IN ('succeeded', 'failed')", name="ck_analysis_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    image_id = Column(
        String(36), ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analyzer_name = Column(String(100), nullable=False)
    analyzer_version = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="succeeded")
    analyzed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    image = relationship("Image", back_populates="analyses")
    attributes = relationship(
        "DetectedAttribute", back_populates="analysis", cascade="all, delete-orphan"
    )
    bounding_boxes = relationship(
        "BoundingBox", back_populates="analysis", cascade="all, delete-orphan"
    )


class DetectedAttribute(Base):
    """A classifier label with confidence for a specific analysis result."""

    __tablename__ = "detected_attributes"
    __table_args__ = (
        UniqueConstraint("analysis_id", "category", "value", name="uq_analysis_attribute"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_attribute_confidence"),
    )

    id = Column(Integer, primary_key=True)
    analysis_id = Column(
        String(36),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(100), nullable=False)
    value = Column(String(200), nullable=False)
    confidence = Column(Float, nullable=False)

    analysis = relationship("AnalysisResult", back_populates="attributes")


class BoundingBox(Base):
    """A normalized detected-object rectangle for an analysis result."""

    __tablename__ = "bounding_boxes"
    __table_args__ = (
        CheckConstraint("x >= 0 AND y >= 0", name="ck_bbox_origin_nonnegative"),
        CheckConstraint("width > 0 AND height > 0", name="ck_bbox_size_positive"),
        CheckConstraint("x + width <= 1 AND y + height <= 1", name="ck_bbox_inside_image"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_bbox_confidence"),
    )

    id = Column(Integer, primary_key=True)
    analysis_id = Column(
        String(36),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(100), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)

    analysis = relationship("AnalysisResult", back_populates="bounding_boxes")


class Segment(Base):
    """A business-defined author or post segment."""

    __tablename__ = "segments"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=False, default="")


class AuthorSegmentAssignment(Base):
    """One version of an author's segment membership; closed rows are history."""

    __tablename__ = "author_segment_assignments"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'automated')", name="ck_author_assignment_source"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from", name="ck_author_assignment_period"
        ),
        Index("ix_author_assignment_current", "author_id", "valid_to"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    author_id = Column(String(36), ForeignKey("authors.id", ondelete="CASCADE"), nullable=False)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False)
    source = Column(String(20), nullable=False)
    assigned_by = Column(String(200), nullable=False)
    reason = Column(Text, nullable=False, default="")
    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    valid_to = Column(DateTime(timezone=True), nullable=True)

    author = relationship("Author", back_populates="segment_assignments")
    segment = relationship("Segment")


class PostSegmentAssignment(Base):
    """One version of an explicit post-level segment override."""

    __tablename__ = "post_segment_assignments"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'automated')", name="ck_post_assignment_source"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from", name="ck_post_assignment_period"
        ),
        Index("ix_post_assignment_current", "post_id", "valid_to"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    post_id = Column(String(36), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False)
    source = Column(String(20), nullable=False)
    assigned_by = Column(String(200), nullable=False)
    reason = Column(Text, nullable=False, default="")
    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    valid_to = Column(DateTime(timezone=True), nullable=True)

    post = relationship("Post", back_populates="segment_assignments")
    segment = relationship("Segment")


class CrawlRun(Base):
    """One logical ingestion run, including terminal status and counters."""

    __tablename__ = "crawl_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="running")
    posts_seen = Column(Integer, nullable=False, default=0)
    images_seen = Column(Integer, nullable=False, default=0)

    batches = relationship("CrawlBatch", back_populates="run", cascade="all, delete-orphan")
    quality_results = relationship("DataQualityResult", back_populates="run")


class CrawlBatch(Base):
    """A bounded group of authors processed as one orchestration unit."""

    __tablename__ = "crawl_batches"
    __table_args__ = (UniqueConstraint("run_id", "batch_number", name="uq_run_batch_number"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False)
    batch_number = Column(Integer, nullable=False)
    author_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    run = relationship("CrawlRun", back_populates="batches")


class DataQualityResult(Base):
    """Persisted outcome and diagnostic details for one named quality check."""

    __tablename__ = "data_quality_results"
    __table_args__ = (
        CheckConstraint("status IN ('passed', 'failed')", name="ck_quality_status"),
        UniqueConstraint("run_id", "check_name", name="uq_run_quality_check"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(
        String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    details = Column(JSON, nullable=False, default=dict)

    run = relationship("CrawlRun", back_populates="quality_results")


class TrendMetric(Base):
    """Locally materialized trend output; production equivalent lives in Snowflake."""

    __tablename__ = "trend_metrics"
    __table_args__ = (
        UniqueConstraint(
            "window_start", "network", "segment_id", "category", "value", name="uq_trend_dimension"
        ),
        CheckConstraint(
            "post_count >= 0 AND author_count >= 0", name="ck_trend_counts_nonnegative"
        ),
        Index("ix_trend_window_segment", "window_start", "segment_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    window_start = Column(DateTime(timezone=True), nullable=False)
    network = Column(String(50), nullable=False)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False)
    category = Column(String(100), nullable=False)
    value = Column(String(200), nullable=False)
    post_count = Column(Integer, nullable=False)
    author_count = Column(Integer, nullable=False)
    generated_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
