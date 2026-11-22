"""Canonical checksums and strict offline validation for maintenance exports."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


EXPORT_SCHEMA_VERSION = 3
INTEGRITY_ALGORITHM = "sha256"
AUTHENTICATION_ALGORITHM = "hmac-sha256"
CANONICALIZATION = "json-sort-keys-v1"
MAX_EXPORT_BYTES = 10 * 1024 * 1024
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CODE_PATTERN = re.compile(r"^[a-z0-9_]{0,100}$")
_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FORBIDDEN_KEYS = {
    "answer_text",
    "audio_path",
    "object_key",
    "original_name",
    "sha256",
    "transcript",
    "user_id",
}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    valid: bool
    errors: tuple[str, ...]
    run_count: int = 0


def attach_integrity(payload: dict) -> dict:
    """Return a new export document with a checksum over canonical JSON."""
    document = {
        key: value
        for key, value in payload.items()
        if key not in {"integrity", "authentication"}
    }
    document["schema_version"] = EXPORT_SCHEMA_VERSION
    document["authentication"] = None
    document["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "canonicalization": CANONICALIZATION,
        "digest": _digest(_integrity_content(document)),
    }
    return document


def attach_authentication(document: dict, *, key_id: str, key: bytes) -> dict:
    """Authenticate an integrity-protected export with one HMAC key."""
    _validate_key_id_and_material(key_id, key)
    authenticated = dict(document)
    authenticated["authentication"] = None
    if not verify_document(authenticated).valid:
        raise ValueError("Only a valid maintenance export can be authenticated.")
    authenticated["authentication"] = {
        "algorithm": AUTHENTICATION_ALGORITHM,
        "key_id": key_id,
        "digest": _hmac_digest(_authenticated_content(authenticated), key),
    }
    return authenticated


def parse_hmac_keyring(value: str) -> dict[str, bytes]:
    """Parse a bounded JSON mapping of key IDs to Base64-encoded HMAC keys."""
    if not value.strip():
        return {}
    try:
        raw = json.loads(value, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("HMAC keyring must be a JSON object.") from exc
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 20:
        raise ValueError("HMAC keyring must contain 1 to 20 keys.")
    result: dict[str, bytes] = {}
    for key_id, encoded in raw.items():
        if not isinstance(key_id, str) or not isinstance(encoded, str):
            raise ValueError("HMAC keyring entries must use string IDs and values.")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("HMAC keyring contains invalid Base64 key material.") from exc
        _validate_key_id_and_material(key_id, key)
        result[key_id] = key
    return result


def verify_document(
    document: Any,
    *,
    authentication_keys: dict[str, bytes] | None = None,
    require_authentication: bool = False,
) -> VerificationReport:
    errors: list[str] = []
    if not isinstance(document, dict):
        return VerificationReport(False, ("Export root must be a JSON object.",))
    _validate_top_level(document, errors)
    integrity = document.get("integrity")
    if isinstance(integrity, dict):
        _validate_integrity(document, integrity, errors)
    authentication = document.get("authentication")
    if authentication is None:
        if require_authentication:
            errors.append("Authenticated export is required.")
    elif isinstance(authentication, dict):
        _validate_authentication(
            document,
            authentication,
            authentication_keys or {},
            errors,
        )
    else:
        errors.append("Authentication metadata must be null or an object.")
    _find_forbidden_keys(document, errors)
    history = document.get("run_history")
    run_count = len(history) if isinstance(history, list) else 0
    return VerificationReport(not errors, tuple(dict.fromkeys(errors)), run_count)


def load_document(path: str | Path) -> dict:
    target = Path(path)
    with target.open("rb") as export_file:
        raw = export_file.read(MAX_EXPORT_BYTES + 1)
    if len(raw) > MAX_EXPORT_BYTES:
        raise ValueError(f"Export exceeds the {MAX_EXPORT_BYTES} byte limit.")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Export is not valid UTF-8 JSON.") from exc
    if not isinstance(document, dict):
        raise ValueError("Export root must be a JSON object.")
    return document


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _digest(document: dict) -> str:
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def _hmac_digest(document: dict, key: bytes) -> str:
    return hmac.new(key, _canonical_bytes(document), hashlib.sha256).hexdigest()


def _canonical_bytes(document: dict) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _integrity_content(document: dict) -> dict:
    return {
        key: value
        for key, value in document.items()
        if key not in {"integrity", "authentication"}
    }


def _authenticated_content(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "authentication"}


def _validate_top_level(document: dict, errors: list[str]) -> None:
    expected = {
        "schema_version",
        "exported_at",
        "task_name",
        "history_limit",
        "current_run",
        "run_history",
        "retention_policy",
        "integrity",
        "authentication",
    }
    if set(document) != expected:
        errors.append("Export has missing or unsupported top-level fields.")
    if document.get("schema_version") != EXPORT_SCHEMA_VERSION:
        errors.append("Unsupported export schema version.")
    if document.get("task_name") != "audio_retention_cleanup":
        errors.append("Unsupported maintenance task.")
    _timestamp(document.get("exported_at"), "exported_at", errors)
    limit = _bounded_int(document.get("history_limit"), 12, 1000)
    if limit is None:
        errors.append("history_limit must be an integer from 12 to 1000.")
    _validate_current_run(document.get("current_run"), errors)
    history = document.get("run_history")
    if not isinstance(history, list):
        errors.append("run_history must be a list.")
    else:
        if limit is not None and len(history) > limit:
            errors.append("run_history exceeds history_limit.")
        for item in history:
            _validate_history_item(item, errors)
    _validate_policy(document.get("retention_policy"), limit, errors)


def _validate_integrity(document: dict, integrity: dict, errors: list[str]) -> None:
    if set(integrity) != {"algorithm", "canonicalization", "digest"}:
        errors.append("Integrity metadata has unsupported fields.")
        return
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        errors.append("Unsupported integrity algorithm.")
    if integrity.get("canonicalization") != CANONICALIZATION:
        errors.append("Unsupported canonicalization method.")
    supplied = integrity.get("digest")
    if not isinstance(supplied, str) or not _DIGEST_PATTERN.fullmatch(supplied):
        errors.append("Integrity digest must be a lowercase SHA-256 value.")
        return
    try:
        expected = _digest(_integrity_content(document))
    except (TypeError, ValueError):
        errors.append("Export contains values that cannot be canonicalized.")
        return
    if not hmac.compare_digest(supplied, expected):
        errors.append("Integrity checksum does not match the export content.")


def _validate_authentication(
    document: dict,
    authentication: dict,
    keys: dict[str, bytes],
    errors: list[str],
) -> None:
    if set(authentication) != {"algorithm", "key_id", "digest"}:
        errors.append("Authentication metadata has unsupported fields.")
        return
    if authentication.get("algorithm") != AUTHENTICATION_ALGORITHM:
        errors.append("Unsupported authentication algorithm.")
    key_id = authentication.get("key_id")
    if not isinstance(key_id, str) or not _KEY_ID_PATTERN.fullmatch(key_id):
        errors.append("Authentication key ID is invalid.")
        return
    supplied = authentication.get("digest")
    if not isinstance(supplied, str) or not _DIGEST_PATTERN.fullmatch(supplied):
        errors.append("Authentication digest must be a lowercase HMAC-SHA256 value.")
        return
    key = keys.get(key_id)
    if key is None:
        errors.append("Authentication key is unavailable.")
        return
    try:
        _validate_key_id_and_material(key_id, key)
        expected = _hmac_digest(_authenticated_content(document), key)
    except (TypeError, ValueError):
        errors.append("Authentication key or export content is invalid.")
        return
    if not hmac.compare_digest(supplied, expected):
        errors.append("Authentication digest does not match the export content.")


def _validate_key_id_and_material(key_id: str, key: bytes) -> None:
    if not isinstance(key_id, str) or not _KEY_ID_PATTERN.fullmatch(key_id):
        raise ValueError("HMAC key ID is invalid.")
    if not isinstance(key, bytes) or not 32 <= len(key) <= 64:
        raise ValueError("HMAC keys must decode to 32-64 bytes.")


def _validate_current_run(value: Any, errors: list[str]) -> None:
    if value is None:
        return
    expected = {
        "status",
        "last_started_at",
        "last_completed_at",
        "last_checked",
        "last_deleted",
        "last_failed",
        "consecutive_failures",
        "run_total",
        "deleted_total",
        "failed_total",
        "last_error_code",
    }
    if not isinstance(value, dict) or set(value) != expected:
        errors.append("current_run has an invalid structure.")
        return
    if value.get("status") not in {"idle", "running", "succeeded", "failed"}:
        errors.append("current_run has an invalid status.")
    for name in ("last_started_at", "last_completed_at"):
        _timestamp(value.get(name), f"current_run.{name}", errors, allow_empty=True)
    for name in (
        "last_checked",
        "last_deleted",
        "last_failed",
        "consecutive_failures",
        "run_total",
        "deleted_total",
        "failed_total",
    ):
        if _bounded_int(value.get(name), 0, 2**63 - 1) is None:
            errors.append(f"current_run.{name} must be a non-negative integer.")
    _error_code(value.get("last_error_code"), "current_run.last_error_code", errors)


def _validate_history_item(value: Any, errors: list[str]) -> None:
    expected = {
        "status",
        "started_at",
        "completed_at",
        "checked_count",
        "deleted_count",
        "failed_count",
        "error_code",
    }
    if not isinstance(value, dict) or set(value) != expected:
        errors.append("run_history contains an invalid record.")
        return
    if value.get("status") not in {"succeeded", "failed"}:
        errors.append("run_history contains an invalid status.")
    _timestamp(value.get("started_at"), "run_history.started_at", errors)
    _timestamp(value.get("completed_at"), "run_history.completed_at", errors)
    for name in ("checked_count", "deleted_count", "failed_count"):
        if _bounded_int(value.get(name), 0, 2**63 - 1) is None:
            errors.append(f"run_history.{name} must be a non-negative integer.")
    _error_code(value.get("error_code"), "run_history.error_code", errors)


def _validate_policy(value: Any, limit: int | None, errors: list[str]) -> None:
    expected = {"configured_days", "observed_days", "last_observed_at", "changes"}
    if not isinstance(value, dict) or set(value) != expected:
        errors.append("retention_policy has an invalid structure.")
        return
    if _bounded_int(value.get("configured_days"), 1, 365) is None:
        errors.append("retention_policy.configured_days must be between 1 and 365.")
    observed = value.get("observed_days")
    if observed is not None and _bounded_int(observed, 1, 365) is None:
        errors.append("retention_policy.observed_days must be null or between 1 and 365.")
    _timestamp(
        value.get("last_observed_at"),
        "retention_policy.last_observed_at",
        errors,
        allow_empty=True,
    )
    changes = value.get("changes")
    if not isinstance(changes, list):
        errors.append("retention_policy.changes must be a list.")
        return
    if limit is not None and len(changes) > limit:
        errors.append("retention_policy.changes exceeds history_limit.")
    expected_change = {"previous_days", "new_days", "changed_at", "source"}
    for change in changes:
        if not isinstance(change, dict) or set(change) != expected_change:
            errors.append("retention_policy.changes contains an invalid record.")
            continue
        if _bounded_int(change.get("previous_days"), 1, 365) is None:
            errors.append("A policy previous_days value is invalid.")
        if _bounded_int(change.get("new_days"), 1, 365) is None:
            errors.append("A policy new_days value is invalid.")
        _timestamp(change.get("changed_at"), "policy change changed_at", errors)
        if change.get("source") != "configuration":
            errors.append("A policy change source is invalid.")


def _find_forbidden_keys(value: Any, errors: list[str]) -> None:
    if isinstance(value, dict):
        forbidden = set(value) & _FORBIDDEN_KEYS
        if forbidden:
            errors.append("Export contains a forbidden sensitive field.")
        for child in value.values():
            _find_forbidden_keys(child, errors)
    elif isinstance(value, list):
        for child in value:
            _find_forbidden_keys(child, errors)


def _timestamp(value: Any, name: str, errors: list[str], *, allow_empty: bool = False) -> None:
    if allow_empty and value == "":
        return
    if not isinstance(value, str) or len(value) > 100:
        errors.append(f"{name} must be an ISO timestamp.")
        return
    try:
        datetime.fromisoformat(value)
    except ValueError:
        errors.append(f"{name} must be an ISO timestamp.")


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if minimum <= value <= maximum else None


def _error_code(value: Any, name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _CODE_PATTERN.fullmatch(value):
        errors.append(f"{name} has an invalid value.")
