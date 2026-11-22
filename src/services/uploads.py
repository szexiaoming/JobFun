"""Validated, idempotent binary upload use cases."""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import PurePath
from typing import BinaryIO

from config import (
    ALLOWED_INTERVIEW_AUDIO_EXTENSIONS,
    ALLOWED_JD_IMAGE_EXTENSIONS,
    ALLOWED_RESUME_EXTENSIONS,
    MAX_INTERVIEW_AUDIO_SIZE_MB,
    MAX_UPLOAD_SIZE_MB,
)
from src.repositories.contracts import StoredObjectRepository
from src.services.context import RequestContext
from src.storage.contracts import ObjectStore, ObjectTooLargeError


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_CHUNK_SIZE = 1024 * 1024


class UploadServiceError(Exception):
    code = "upload_error"


class UploadValidationError(UploadServiceError):
    code = "upload_validation_error"


class UploadIdempotencyConflict(UploadServiceError):
    code = "idempotency_conflict"


class UploadNotFoundError(UploadServiceError):
    code = "resource_not_found"


_UPLOAD_RULES = {
    "resume_source": (ALLOWED_RESUME_EXTENSIONS, MAX_UPLOAD_SIZE_MB * 1024 * 1024),
    "job_source": (ALLOWED_JD_IMAGE_EXTENSIONS | {".pdf"}, 20 * 1024 * 1024),
    "interview_audio": (
        ALLOWED_INTERVIEW_AUDIO_EXTENSIONS,
        MAX_INTERVIEW_AUDIO_SIZE_MB * 1024 * 1024,
    ),
}


class UploadApplicationService:
    def __init__(
        self,
        context: RequestContext,
        store: ObjectStore,
        repository: StoredObjectRepository,
    ) -> None:
        if context.user_id is None or context.user_id <= 0:
            raise ValueError("An authenticated user context is required")
        self.context = context
        self._store = store
        self._repository = repository

    @property
    def user_id(self) -> int:
        return int(self.context.user_id)

    def upload(
        self,
        *,
        kind: str,
        filename: str,
        content_type: str,
        stream: BinaryIO,
        idempotency_key: str,
    ) -> dict:
        clean_kind = str(kind or "").strip()
        if clean_kind not in _UPLOAD_RULES:
            raise UploadValidationError("Unsupported upload kind")
        key = _validate_idempotency_key(idempotency_key)
        safe_name = _validate_filename(filename, _UPLOAD_RULES[clean_kind][0])
        max_bytes = _UPLOAD_RULES[clean_kind][1]
        media_type = str(content_type or "application/octet-stream")[:255]

        try:
            with _prepare(stream, max_bytes) as prepared:
                size, checksum = prepared.size_bytes, prepared.sha256
                if size == 0:
                    raise UploadValidationError("Upload must not be empty")
                existing = self._repository.get_by_idempotency(
                    self.user_id,
                    clean_kind,
                    key,
                )
                if existing:
                    if (
                        int(existing.get("size_bytes") or 0) == size
                        and str(existing.get("sha256") or "") == checksum
                        and str(existing.get("original_name") or "") == safe_name
                        and str(existing.get("content_type") or "") == media_type
                    ):
                        return _public_object(existing, replayed=True)
                    raise UploadIdempotencyConflict(
                        "The idempotency key was already used for another object"
                    )

                object_key = (
                    f"users/{self.user_id}/{clean_kind}/{uuid.uuid4().hex}/{safe_name}"
                )
                prepared.stream.seek(0)
                blob = self._store.put(
                    object_key,
                    prepared.stream,
                    content_type=media_type,
                    max_bytes=max_bytes,
                )
                replayed = False
                try:
                    stored = self._repository.create(
                        user_id=self.user_id,
                        object_key=blob.key,
                        kind=clean_kind,
                        original_name=safe_name,
                        content_type=media_type,
                        size_bytes=blob.size_bytes,
                        sha256=blob.sha256,
                        idempotency_key=key,
                        status="available",
                        created_at=_utc_now(),
                    )
                except Exception as exc:
                    try:
                        self._store.delete(blob.key)
                    except Exception:
                        # Preserve the metadata failure; storage cleanup can be
                        # retried by an operational orphan-object sweep.
                        pass
                    raced = self._repository.get_by_idempotency(
                        self.user_id,
                        clean_kind,
                        key,
                    )
                    if raced and _same_upload(
                        raced,
                        size=size,
                        checksum=checksum,
                        filename=safe_name,
                        content_type=media_type,
                    ):
                        stored = raced
                        replayed = True
                    elif raced:
                        raise UploadIdempotencyConflict(
                            "The idempotency key was already used for another object"
                        ) from exc
                    else:
                        raise
        except ObjectTooLargeError as exc:
            raise UploadValidationError("Upload exceeds the allowed size") from exc
        return _public_object(stored, replayed=replayed)

    def get(self, object_id: int) -> dict:
        stored = self._repository.get(self.user_id, object_id)
        if stored is None:
            raise UploadNotFoundError("Object does not exist")
        return _public_object(stored)

    def delete(self, object_id: int) -> dict:
        stored = self._repository.get(self.user_id, object_id)
        if stored is None:
            raise UploadNotFoundError("Object does not exist")
        if str(stored.get("kind") or "") != "interview_audio":
            raise UploadValidationError("Only interview audio can be deleted here")
        object_key = str(stored["object_key"])
        self._store.delete(object_key)
        self._repository.clear_audio_reference(object_key)
        self._repository.mark_deleted(self.user_id, object_id, _utc_now())
        return {"id": object_id, "status": "deleted"}


class _Prepared:
    def __init__(self, stream, size_bytes: int, sha256: str) -> None:
        self.stream = stream
        self.size_bytes = size_bytes
        self.sha256 = sha256

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()


def _prepare(stream: BinaryIO, max_bytes: int) -> _Prepared:
    output = tempfile.SpooledTemporaryFile(max_size=8 * _CHUNK_SIZE)
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := stream.read(_CHUNK_SIZE):
            size += len(chunk)
            if size > max_bytes:
                raise ObjectTooLargeError("Object exceeds the configured size limit")
            digest.update(chunk)
            output.write(chunk)
        output.seek(0)
        return _Prepared(output, size, digest.hexdigest())
    except Exception:
        output.close()
        raise


def _validate_filename(filename: str, allowed_extensions: set[str]) -> str:
    raw = str(filename or "").strip()
    if not raw or PurePath(raw).name != raw or "/" in raw or "\\" in raw:
        raise UploadValidationError("Invalid upload filename")
    extension = PurePath(raw).suffix.lower()
    if extension not in allowed_extensions:
        raise UploadValidationError("Unsupported file extension")
    safe = _SAFE_FILENAME.sub("_", raw).strip("._")
    if not safe or len(safe) > 180:
        raise UploadValidationError("Invalid upload filename")
    if PurePath(safe).suffix.lower() != extension:
        safe = f"{safe}{extension}"
    return safe


def _validate_idempotency_key(value: str) -> str:
    key = str(value or "").strip()
    if not _IDEMPOTENCY_KEY.fullmatch(key):
        raise UploadValidationError("Invalid Idempotency-Key")
    return key


def _public_object(value: dict, *, replayed: bool = False) -> dict:
    return {
        "id": int(value["id"]),
        "object_key": str(value["object_key"]),
        "kind": str(value["kind"]),
        "original_name": str(value["original_name"]),
        "content_type": str(value["content_type"]),
        "size_bytes": int(value["size_bytes"]),
        "sha256": str(value["sha256"]),
        "status": str(value["status"]),
        "created_at": str(value.get("created_at") or ""),
        "replayed": replayed,
    }


def _same_upload(
    value: dict,
    *,
    size: int,
    checksum: str,
    filename: str,
    content_type: str,
) -> bool:
    return (
        int(value.get("size_bytes") or 0) == size
        and str(value.get("sha256") or "") == checksum
        and str(value.get("original_name") or "") == filename
        and str(value.get("content_type") or "") == content_type
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
