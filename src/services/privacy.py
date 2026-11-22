"""Authenticated data export and two-step account deletion use cases."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from typing import BinaryIO, Iterator

from config import MAX_DATA_EXPORT_SIZE_MB
from src.repositories.contracts import PrivacyRepository
from src.services.context import RequestContext
from src.storage.contracts import ObjectStore


DELETION_CONFIRMATION = "DELETE MY DATA"
DELETION_CHALLENGE_MINUTES = 15
_EXPORT_LIMIT = MAX_DATA_EXPORT_SIZE_MB * 1024 * 1024
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class PrivacyServiceError(Exception):
    code = "privacy_error"


class PrivacyValidationError(PrivacyServiceError):
    code = "privacy_validation_error"


class PrivacyChallengeError(PrivacyServiceError):
    code = "deletion_challenge_invalid"


class PrivacyResourceNotFound(PrivacyServiceError):
    code = "resource_not_found"


@dataclass(slots=True)
class ExportPackage:
    stream: BinaryIO
    filename: str
    size_bytes: int

    def chunks(self, size: int = 1024 * 1024) -> Iterator[bytes]:
        self.stream.seek(0)
        while chunk := self.stream.read(size):
            yield chunk

    def close(self) -> None:
        self.stream.close()


class PrivacyApplicationService:
    def __init__(
        self,
        context: RequestContext,
        repository: PrivacyRepository,
        store: ObjectStore,
    ) -> None:
        if context.user_id is None or context.user_id <= 0:
            raise ValueError("An authenticated user context is required")
        self.context = context
        self._repository = repository
        self._store = store

    @property
    def user_id(self) -> int:
        return int(self.context.user_id)

    def create_deletion_challenge(self) -> dict:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=DELETION_CHALLENGE_MINUTES)
        self._repository.create_deletion_challenge(
            user_id=self.user_id,
            token_hash=_hash(token),
            expires_at=expires.isoformat(),
            created_at=now.isoformat(),
        )
        return {
            "deletion_token": token,
            "expires_at": expires.isoformat(),
            "required_confirmation": DELETION_CONFIRMATION,
        }

    def export(self) -> ExportPackage:
        snapshot = self._repository.export_snapshot(self.user_id)
        if snapshot is None:
            raise PrivacyResourceNotFound("User does not exist")
        exported = _exportable_snapshot(snapshot)
        warnings: list[dict[str, str | int]] = _legacy_asset_warnings(snapshot)
        output = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
        exported_binary_bytes = 0
        try:
            with zipfile.ZipFile(
                output,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.writestr(
                    "data.json",
                    json.dumps(exported, ensure_ascii=False, indent=2),
                )
                for stored in snapshot.get("stored_objects", []):
                    size = int(stored.get("size_bytes") or 0)
                    object_id = int(stored.get("id") or 0)
                    if exported_binary_bytes + size > _EXPORT_LIMIT:
                        warnings.append({
                            "object_id": object_id,
                            "code": "export_size_limit",
                        })
                        continue
                    try:
                        content = self._store.read(
                            str(stored["object_key"]),
                            max_bytes=max(size, 1),
                        )
                    except Exception:
                        warnings.append({
                            "object_id": object_id,
                            "code": "object_unavailable",
                        })
                        continue
                    if len(content) != size or hashlib.sha256(content).hexdigest() != str(
                        stored.get("sha256") or ""
                    ):
                        warnings.append({
                            "object_id": object_id,
                            "code": "object_integrity_mismatch",
                        })
                        continue
                    exported_binary_bytes += len(content)
                    archive.writestr(
                        f"objects/{object_id}/{_safe_filename(stored.get('original_name'))}",
                        content,
                    )
                counts = {
                    key: (1 if key == "user" else len(value))
                    for key, value in exported.items()
                }
                exported_at = _utc_now()
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "exported_at": exported_at,
                            "counts": counts,
                            "binary_bytes": exported_binary_bytes,
                            "warnings": warnings,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            size_bytes = output.tell()
            self._repository.record_audit(
                correlation_id=uuid.uuid4().hex,
                subject_hash=_anonymous_subject(self.user_id),
                event_type="data_exported",
                status="completed_with_warnings" if warnings else "completed",
                request_id=self.context.request_id,
                details_json={"counts": counts, "warning_count": len(warnings)},
                created_at=exported_at,
            )
            output.seek(0)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            return ExportPackage(output, f"jobfun-export-{stamp}.zip", size_bytes)
        except Exception:
            output.close()
            raise

    def delete_account(
        self,
        *,
        deletion_token: str,
        username: str,
        confirmation: str,
    ) -> dict:
        if confirmation != DELETION_CONFIRMATION:
            raise PrivacyValidationError("Deletion confirmation phrase does not match")
        if username != self.context.username:
            raise PrivacyValidationError("Username confirmation does not match")
        clean_token = str(deletion_token or "").strip()
        if len(clean_token) < 32 or len(clean_token) > 256 or not clean_token.isascii():
            raise PrivacyChallengeError("Deletion challenge is invalid or expired")
        snapshot = self._repository.export_snapshot(self.user_id)
        if snapshot is None:
            raise PrivacyResourceNotFound("User does not exist")
        if _legacy_asset_warnings(snapshot):
            raise PrivacyValidationError(
                "Legacy local files must be migrated before account deletion"
            )
        token_hash = _hash(clean_token)
        correlation_id = uuid.uuid4().hex
        result = self._repository.delete_user_data(
            user_id=self.user_id,
            token_hash=token_hash,
            now=_utc_now(),
            correlation_id=correlation_id,
            subject_hash=_hash(f"{self.user_id}:{token_hash}"),
            request_id=self.context.request_id,
        )
        if result is None:
            raise PrivacyChallengeError("Deletion challenge is invalid or expired")
        pending = self._cleanup(result["cleanup_jobs"])
        self._repository.update_deletion_audit(int(result["audit_id"]), pending)
        return {
            "status": "deleted",
            "correlation_id": result["correlation_id"],
            "deleted_records": sum(result["counts"].values()),
            "object_cleanup_pending": pending,
        }

    def retry_pending_cleanups(self, limit: int = 100) -> dict:
        return ObjectCleanupRunner(self._repository, self._store).run(limit)

    def _cleanup(self, jobs: list[dict]) -> int:
        pending = 0
        for job in jobs:
            try:
                self._store.delete(str(job["object_key"]))
                self._repository.complete_cleanup(int(job["id"]))
            except Exception:
                pending += 1
                self._repository.fail_cleanup(int(job["id"]), _utc_now())
        return pending


class ObjectCleanupRunner:
    def __init__(self, repository: PrivacyRepository, store: ObjectStore) -> None:
        self._repository = repository
        self._store = store

    def run(self, limit: int = 100) -> dict:
        jobs = self._repository.list_cleanup_jobs(max(1, min(limit, 1000)))
        pending = 0
        for job in jobs:
            try:
                self._store.delete(str(job["object_key"]))
                self._repository.complete_cleanup(int(job["id"]))
            except Exception:
                pending += 1
                self._repository.fail_cleanup(int(job["id"]), _utc_now())
        return {"processed": len(jobs), "pending": pending}


def _exportable_snapshot(snapshot: dict) -> dict:
    excluded = {
        "resumes": {"latex_path", "pdf_path"},
        "job_descriptions": {"source_file"},
        "interview_attempts": {"audio_path"},
        "latex_changes": {"file_path", "commit_hash"},
        "operation_jobs": {"idempotency_key", "request_hash"},
        "stored_objects": {"idempotency_key"},
    }
    result = {"user": _decode_row(snapshot["user"], {"settings_json"})}
    for table, rows in snapshot.items():
        if table == "user":
            continue
        result[table] = [
            _decode_row(row, excluded.get(table, set())) for row in rows
        ]
    return result


def _decode_row(row: dict, excluded: set[str]) -> dict:
    decoded = {}
    json_fields = {
        "settings_json",
        "input_refs_json",
        "result_refs_json",
        "payload_json",
        "structured_json",
        "matched_skills",
        "missing_skills",
        "risks",
        "evidence_json",
        "previous_evidence_json",
        "corrected_evidence_json",
        "snapshot_json",
        "feedback_json",
    }
    for key, value in row.items():
        if key in excluded:
            continue
        public_key = {
            "settings_json": "settings",
            "payload_json": "payload",
        }.get(key, key)
        if key in json_fields and isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                pass
        decoded[public_key] = value
    return decoded


def _safe_filename(value) -> str:
    name = PurePath(str(value or "object.bin")).name
    safe = _SAFE_FILENAME.sub("_", name).strip("._")
    return (safe or "object.bin")[:180]


def _legacy_asset_warnings(snapshot: dict) -> list[dict[str, str | int]]:
    fields = {
        "resumes": ("latex_path", "pdf_path"),
        "job_descriptions": ("source_file",),
        "interview_attempts": ("audio_path",),
    }
    warnings = []
    for table, names in fields.items():
        for row in snapshot.get(table, []):
            for name in names:
                value = str(row.get(name) or "").strip()
                if value:
                    warnings.append({
                        "record_id": int(row.get("id") or 0),
                        "code": "legacy_local_file_not_exported",
                    })
    return warnings


def _anonymous_subject(user_id: int) -> str:
    return _hash(f"{user_id}:{secrets.token_hex(16)}")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
