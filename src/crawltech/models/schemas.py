"""Validated inputs and outputs exchanged by crawler and analyzer adapters."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ImageReference(BaseModel):
    """An image reference returned with a crawled post."""

    source_url: HttpUrl
    media_type: str = "image/png"


class CrawledAuthor(BaseModel):
    """Stable crawler representation of a social author."""

    network: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    profile_url: HttpUrl
    metadata: dict[str, object] = Field(default_factory=dict)


class CrawledPost(BaseModel):
    """Post metadata and image references supplied by a crawler."""

    network: str = Field(min_length=1, max_length=50)
    author_external_id: str = Field(min_length=1, max_length=200)
    external_id: str = Field(min_length=1, max_length=200)
    published_at: datetime
    caption: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    images: list[ImageReference] = Field(default_factory=list)


class DetectedAttributeInput(BaseModel):
    """A semantic attribute emitted by an analyzer."""

    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)


class BoundingBoxInput(BaseModel):
    """Normalized image coordinates for one detected object."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1, max_length=100)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def fit_within_image(self) -> "BoundingBoxInput":
        """Reject boxes extending beyond the normalized image boundary."""
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("bounding box must fit within normalized image bounds")
        return self


class AnalysisOutput(BaseModel):
    """Versioned analyzer response for one persisted image."""

    analyzer_name: str = Field(min_length=1, max_length=100)
    analyzer_version: str = Field(min_length=1, max_length=100)
    attributes: list[DetectedAttributeInput] = Field(default_factory=list)
    bounding_boxes: list[BoundingBoxInput] = Field(default_factory=list)
