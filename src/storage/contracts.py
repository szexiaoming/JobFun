"""Storage-neutral binary object contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


class ObjectStorageError(Exception):
    """Base error for object storage adapters."""


class ObjectTooLargeError(ObjectStorageError):
    """The streamed object exceeded its configured maximum size."""


class InvalidObjectKeyError(ObjectStorageError):
    """The object key could escape or ambiguously address the storage root."""


@dataclass(frozen=True, slots=True)
class StoredBlob:
    key: str
    size_bytes: int
    sha256: str
    content_type: str
    etag: str = ""


class ObjectStore(Protocol):
    def put(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
        max_bytes: int,
    ) -> StoredBlob: ...

    def read(self, key: str, *, max_bytes: int) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...
