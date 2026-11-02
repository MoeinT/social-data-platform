"""Ports used by business services to isolate external integrations."""

from collections.abc import Sequence
from typing import Protocol

from crawltech.adapters.storage import StoredImage
from crawltech.models.schemas import AnalysisOutput, CrawledAuthor, CrawledPost, ImageReference


class Crawler(Protocol):
    """Discover eligible authors and retrieve an author's post metadata."""

    def discover_authors(self) -> Sequence[CrawledAuthor]: ...

    def crawl_posts(self, author: CrawledAuthor) -> Sequence[CrawledPost]: ...


class ImageStorage(Protocol):
    """Persist a remote image reference and return its stable local reference."""

    def download(self, image: ImageReference) -> StoredImage: ...

    def exists(self, storage_uri: str) -> bool: ...


class Analyzer(Protocol):
    """Analyze a stored image reference and return versioned structured output."""

    name: str
    version: str

    def analyze(self, storage_uri: str) -> AnalysisOutput: ...
