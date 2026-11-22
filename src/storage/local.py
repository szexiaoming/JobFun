"""Atomic local-filesystem object storage adapter."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from src.storage.contracts import (
    InvalidObjectKeyError,
    ObjectStorageError,
    ObjectTooLargeError,
    StoredBlob,
)


_CHUNK_SIZE = 1024 * 1024


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        _io_path(self._root).mkdir(parents=True, exist_ok=True)

    def put(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
        max_bytes: int,
    ) -> StoredBlob:
        target = self._path(key)
        io_target = _io_path(target)
        io_target.parent.mkdir(parents=True, exist_ok=True)
        # Keep the temporary name at the root so deep keys do not exceed the
        # legacy Windows path-length limit during atomic writes.
        temporary = _io_path(self._root / f".{uuid.uuid4().hex}.part")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := stream.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ObjectTooLargeError("Object exceeds the configured size limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, io_target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return StoredBlob(key, size, digest.hexdigest(), content_type)

    def read(self, key: str, *, max_bytes: int) -> bytes:
        target = _io_path(self._path(key))
        try:
            with target.open("rb") as source:
                data = source.read(max_bytes + 1)
        except OSError as exc:
            raise ObjectStorageError("Object could not be read") from exc
        if len(data) > max_bytes:
            raise ObjectTooLargeError("Object exceeds the configured read limit")
        return data

    def exists(self, key: str) -> bool:
        return _io_path(self._path(key)).is_file()

    def delete(self, key: str) -> None:
        try:
            _io_path(self._path(key)).unlink(missing_ok=True)
        except OSError as exc:
            raise ObjectStorageError("Object could not be deleted") from exc

    def _path(self, key: str) -> Path:
        normalized = str(key or "")
        pure = PurePosixPath(normalized)
        if (
            not normalized
            or "\\" in normalized
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise InvalidObjectKeyError("Invalid object key")
        target = self._root.joinpath(*pure.parts).resolve()
        if self._root not in target.parents:
            raise InvalidObjectKeyError("Object key escapes the storage root")
        return target


def _io_path(path: Path) -> Path:
    """Use Win32's extended path form when a sandbox/temp root is very long."""
    value = str(path)
    if os.name == "nt" and len(value) >= 240 and not value.startswith("\\\\?\\"):
        return Path(f"\\\\?\\{value}")
    return path
