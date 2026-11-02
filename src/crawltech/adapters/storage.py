"""Local content-addressed image storage used by development and tests."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from struct import pack
from zlib import compress, crc32

from crawltech.models.schemas import ImageReference


def _chunk(kind: bytes, data: bytes) -> bytes:
    """Encode one PNG chunk with its length and checksum."""
    return pack(">I", len(data)) + kind + data + pack(">I", crc32(kind + data) & 0xFFFFFFFF)


def _sample_png(seed: bytes) -> bytes:
    """Build a valid deterministic 1x1 RGBA PNG from a stable content seed."""
    header = pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixel = b"\x00" + seed[:3] + b"\xff"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", compress(pixel))
        + _chunk(b"IEND", b"")
    )


@dataclass(frozen=True)
class StoredImage:
    """File-backed image metadata; the payload itself is never persisted in SQL."""

    sha256: str
    storage_uri: str
    media_type: str


class LocalImageStorage:
    """Write deterministic image files under a local directory by content hash."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def download(self, image: ImageReference) -> StoredImage:
        """Materialize one deterministic sample file for a crawled image reference."""
        self.root.mkdir(parents=True, exist_ok=True)
        source = str(image.source_url).encode("utf-8")
        payload = _sample_png(sha256(source).digest())
        digest = sha256(payload).hexdigest()
        target = self.root / f"{digest}.png"
        if not target.exists():
            target.write_bytes(payload)
        return StoredImage(digest, str(target.resolve()), image.media_type)

    def exists(self, storage_uri: str) -> bool:
        """Return whether the stored local image file is present."""
        return Path(storage_uri).is_file()
