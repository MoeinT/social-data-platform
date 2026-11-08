"""External-system adapters and local deterministic implementations."""

from crawltech.adapters.interfaces import Analyzer, Crawler, ImageStorage
from crawltech.adapters.mock import MockAnalyzer, MockCrawler
from crawltech.adapters.storage import LocalImageStorage, StoredImage

__all__ = [
    "Analyzer",
    "Crawler",
    "ImageStorage",
    "LocalImageStorage",
    "MockAnalyzer",
    "MockCrawler",
    "StoredImage",
]
