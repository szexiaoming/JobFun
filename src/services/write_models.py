"""Idempotent, ownership-scoped write use cases and AI job submission."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from config import get_active_model, get_transcription_runtime_label
from src.core.progress_manager import STATUS_FLOW
from src.db.models import Application, ApplicationEvent, JobDescription, Resume
from src.db.sqlite_client import Database
from src.services.gap_explanations import json_object, requirement_options
from src.repositories.contracts import (
    OperationRepository,
    OwnershipRepository,
    StoredObjectRepository,
)
from src.services.context import RequestContext
from src.services.read_models import ReadApplicationService


MAX_ACTIVE_OPERATIONS = 5
MAX_OPERATIONS_PER_MINUTE = 20
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


class WriteServiceError(Exception):
    code = "write_error"


class IdempotencyConflictError(WriteServiceError):
    code = "idempotency_conflict"


class ResourceNotFoundError(WriteServiceError):
    code = "resource_not_found"


class WriteValidationError(WriteServiceError):
    code = "write_validation_error"


class RateLimitError(WriteServiceError):
    code = "rate_limit_exceeded"


class WriteApplicationService:
    def __init__(
        self,
        context: RequestContext,
        database: Database,
        ownership: OwnershipRepository,
        operations: OperationRepository,
        stored_objects: StoredObjectRepository,
    ) -> None:
        if context.user_id is None or context.user_id <= 0:
            raise ValueError("An authenticated user context is required")
        self.context = context
        self._database = database
        self._ownership = ownership
        self._operations = operations
        self._stored_objects = stored_objects
        self._reads = ReadApplicationService(context, ownership)

    @property
    def user_id(self) -> int:
        return int(self.context.user_id)

    def get_operation(self, operation_id: int) -> dict | None:
        operation = self._operations.get(self.user_id, operation_id)
        return _public_operation(operation) if operation else None

    def queue_resume_parse(
        self,
        *,
        name: str,
        text: str,
        idempotency_key: str,
    ) -> dict:
        clean_name = str(name or "").strip()
        clean_text = str(text or "").strip()
        if not clean_name or len(clean_name) > 200:
            raise WriteValidationError("Resume name must be between 1 and 200 characters")
        if not clean_text or len(clean_text) > 200_000:
            raise WriteValidationError("Resume text must be between 1 and 200,000 characters")
        request = {"name": clean_name, "text": clean_text}
        request_hash = _request_hash(request)
        existing = self._existing("resume_parse", idempotency_key, request_hash)
        if existing:
            return _public_operation(existing, replayed=True)
        self._check_limits()
        now = _utc_now()
        with self._database.transaction():
            resume_id = self._database.insert(
                "resumes",
                Resume(
                    user_id=self.user_id,
                    name=clean_name,
                    latex_path="",
                    structured_json={"status": "pending_parse"},
                    created_at=now,
                ),
            )
            operation = self._operations.create(
                user_id=self.user_id,
                operation_type="resume_parse",
                idempotency_key=_validate_idempotency_key(idempotency_key),
                request_hash=request_hash,
                status="queued",
                progress=0,
                input_refs_json={"resume_id": resume_id},
                result_refs_json={"resume_id": resume_id},
                model=_model("structured"),
                input_units=len(clean_text),
                created_at=now,
                updated_at=now,
            )
            self._operations.store_payload(
                operation["id"],
                self.user_id,
                {"name": clean_name, "text": clean_text},
            )
        return _public_operation(operation)

    def queue_job_parse(
        self,
        *,
        text: str,
        source_url: str,
        idempotency_key: str,
    ) -> dict:
        clean_text = str(text or "").strip()
        clean_url = str(source_url or "").strip()
        if not clean_text or len(clean_text) > 100_000:
            raise WriteValidationError("JD text must be between 1 and 100,000 characters")
        if len(clean_url) > 2_000:
            raise WriteValidationError("Source URL is too long")
        request = {"text": clean_text, "source_url": clean_url}
        request_hash = _request_hash(request)
        existing = self._existing("jd_parse", idempotency_key, request_hash)
        if existing:
            return _public_operation(existing, replayed=True)
        self._check_limits()
        now = _utc_now()
        with self._database.transaction():
            job_id = self._database.insert(
                "job_descriptions",
                JobDescription(
                    user_id=self.user_id,
                    raw_text=clean_text,
                    source_type="text",
                    source_url=clean_url,
                    structured_json={"status": "pending_parse"},
                    created_at=now,
                ),
            )
            operation = self._operations.create(
                user_id=self.user_id,
                operation_type="jd_parse",
                idempotency_key=_validate_idempotency_key(idempotency_key),
                request_hash=request_hash,
                status="queued",
                progress=0,
                input_refs_json={"job_id": job_id},
                result_refs_json={"job_id": job_id},
                model=_model("structured"),
                input_units=len(clean_text),
                created_at=now,
                updated_at=now,
            )
            self._operations.store_payload(
                operation["id"],
                self.user_id,
                {"text": clean_text},
            )
        return _public_operation(operation)

    def queue_match(
        self,
        *,
        resume_id: int,
        job_id: int,
        idempotency_key: str,
    ) -> dict:
        request = {"resume_id": resume_id, "job_id": job_id}
        request_hash = _request_hash(request)
        existing = self._existing("match", idempotency_key, request_hash)
        if existing:
            return _public_operation(existing, replayed=True)
        resume = self._ownership.get_resume(self.user_id, resume_id)
        job = self._ownership.get_job_description(self.user_id, job_id)
        if resume is None or job is None:
            raise ResourceNotFoundError("Resume or job does not exist")
        self._check_limits()
        operation = self._create_queued_operation(
            operation_type="match",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            input_refs=request,
            payload={},
            model=_model("reasoning"),
            input_units=len(str(resume.get("structured_json", ""))) + len(str(job.get("structured_json", ""))),
        )
        return _public_operation(operation)

    def queue_gap_explanation(
        self,
        *,
        application_id: int,
        requirement_key: str,
        idempotency_key: str,
    ) -> dict:
        key = str(requirement_key or "").strip()
        if not key or len(key) > 2_000:
            raise WriteValidationError("A valid requirement key is required")
        request_hash = _request_hash({"application_id": application_id, "requirement_key": key})
        existing = self._existing("gap_explanation", idempotency_key, request_hash)
        if existing:
            return _public_operation(existing, replayed=True)
        application = self._ownership.get_application(self.user_id, application_id)
        if application is None or not int(application.get("match_id") or 0):
            raise ResourceNotFoundError("Application or match does not exist")
        job_id = int(application["jd_id"])
        resume_id = int(application["resume_id"])
        match = self._ownership.get_match(self.user_id, int(application["match_id"]))
        job = self._ownership.get_job_description(self.user_id, job_id)
        resume = self._ownership.get_resume(self.user_id, resume_id)
        if (
            match is None or job is None or resume is None
            or int(match["jd_id"]) != job_id or int(match["resume_id"]) != resume_id
        ):
            raise ResourceNotFoundError("Application or match does not exist")
        options = requirement_options(job_id, json_object(job.get("structured_json")))
        if not any(item["key"] == key for item in options):
            raise WriteValidationError("Requirement is not part of this application")
        self._check_limits()
        operation = self._create_queued_operation(
            operation_type="gap_explanation",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            input_refs={"application_id": application_id},
            payload={"requirement_key": key},
            model=_model("agent"),
            input_units=len(key) + len(str(resume.get("structured_json") or "")),
        )
        return _public_operation(operation)

    def get_gap_explanation(self, operation_id: int) -> dict | None:
        operation = self._operations.get(self.user_id, operation_id)
        if (
            operation is None
            or operation.get("operation_type") != "gap_explanation"
            or operation.get("status") != "succeeded"
        ):
            return None
        application_id = int((operation.get("input_refs_json") or {}).get("application_id") or 0)
        if self._ownership.get_application(self.user_id, application_id) is None:
            return None
        payload = self._operations.get_payload(operation_id, self.user_id)
        result = payload.get("result") if isinstance(payload, dict) else None
        return result if isinstance(result, dict) else None

    def queue_interview_answer(
        self,
        *,
        application_id: int,
        question_id: int,
        answer_text: str,
        idempotency_key: str,
        transcription_operation_id: int | None = None,
        retain_audio: bool = False,
    ) -> dict:
        answer = str(answer_text or "").strip()
        if not answer or len(answer) > 12_000:
            raise WriteValidationError("Answer must be between 1 and 12,000 characters")
        request = {
            "application_id": application_id,
            "question_id": question_id,
            "answer_text": answer,
            "transcription_operation_id": transcription_operation_id or 0,
            "retain_audio": bool(retain_audio),
        }
        request_hash = _request_hash(request)
        existing = self._existing("interview_answer", idempotency_key, request_hash)
        if existing:
            return _public_operation(existing, replayed=True)
        application = self._ownership.get_application(self.user_id, application_id)
        question = self._ownership.get_interview_question(self.user_id, question_id)
        if application is None or question is None:
            raise ResourceNotFoundError("Application or question does not exist")
        if int(application.get("match_id") or 0) != int(question.get("match_id") or 0):
            raise ResourceNotFoundError("Application or question does not exist")
        audio_object_id = 0
        confirmed_transcript = ""
        if transcription_operation_id is not None:
            transcription = self._validated_transcription(
                transcription_operation_id,
                application_id=application_id,
                question_id=question_id,
            )
            audio_object_id = int(transcription["object_id"])
            if retain_audio and not bool(transcription["audio_retained"]):
                raise WriteValidationError("The original audio was not retained")
            confirmed_transcript = answer
        elif retain_audio:
            raise WriteValidationError("Audio can only be retained for a voice transcript")
        self._check_limits()
        operation = self._create_queued_operation(
            operation_type="interview_answer",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            input_refs={"application_id": application_id, "question_id": question_id},
            payload={
                "answer_text": answer,
                "transcription_operation_id": transcription_operation_id or 0,
                "audio_object_id": audio_object_id,
                "retain_audio": bool(retain_audio),
                "transcript": confirmed_transcript,
            },
            model=_model("evaluation"),
            input_units=len(answer),
        )
        return _public_operation(operation)

    def queue_interview_transcription(
        self,
        *,
        application_id: int,
        question_id: int,
        object_id: int,
        retain_audio: bool = False,
        idempotency_key: str,
    ) -> dict:
        request = {
            "application_id": application_id,
            "question_id": question_id,
            "object_id": object_id,
            "retain_audio": int(bool(retain_audio)),
        }
        request_hash = _request_hash(request)
        existing = self._existing(
            "interview_transcription", idempotency_key, request_hash
        )
        if existing:
            return _public_operation(existing, replayed=True)
        application = self._ownership.get_application(self.user_id, application_id)
        question = self._ownership.get_interview_question(self.user_id, question_id)
        stored = self._stored_objects.get(self.user_id, object_id)
        if application is None or question is None or stored is None:
            raise ResourceNotFoundError("Interview audio inputs do not exist")
        if int(application.get("match_id") or 0) != int(question.get("match_id") or 0):
            raise ResourceNotFoundError("Interview audio inputs do not exist")
        if str(stored.get("kind") or "") != "interview_audio":
            raise ResourceNotFoundError("Interview audio inputs do not exist")
        self._check_limits()
        operation = self._create_queued_operation(
            operation_type="interview_transcription",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            input_refs=request,
            payload={"object_id": object_id},
            model=get_transcription_runtime_label(),
            input_units=int(stored.get("size_bytes") or 0),
        )
        return _public_operation(operation)

    def get_interview_transcription(self, operation_id: int) -> dict | None:
        operation = self._operations.get(self.user_id, operation_id)
        if (
            operation is None
            or operation.get("operation_type") != "interview_transcription"
            or operation.get("status") != "succeeded"
        ):
            return None
        payload = self._operations.get_payload(operation_id, self.user_id)
        if payload is None or _expired(payload.get("expires_at")):
            return None
        refs = operation.get("input_refs_json") or {}
        return {
            "operation_id": int(operation_id),
            "application_id": int(refs["application_id"]),
            "question_id": int(refs["question_id"]),
            "object_id": int(refs["object_id"]),
            "transcript": str(payload.get("transcript") or ""),
            "original_name": str(payload.get("original_name") or ""),
            "content_type": str(payload.get("content_type") or ""),
            "size_bytes": int(payload.get("size_bytes") or 0),
            "audio_retained": bool(payload.get("audio_retained")),
            "expires_at": str(payload.get("expires_at") or ""),
        }

    def _validated_transcription(
        self,
        operation_id: int,
        *,
        application_id: int,
        question_id: int,
    ) -> dict:
        operation = self._operations.get(self.user_id, operation_id)
        if (
            operation is None
            or operation.get("operation_type") != "interview_transcription"
            or operation.get("status") != "succeeded"
        ):
            raise ResourceNotFoundError("Transcription draft does not exist")
        refs = operation.get("input_refs_json") or {}
        if (
            int(refs.get("application_id") or 0) != application_id
            or int(refs.get("question_id") or 0) != question_id
        ):
            raise ResourceNotFoundError("Transcription draft does not exist")
        payload = self._operations.get_payload(operation_id, self.user_id)
        if payload is None or _expired(payload.get("expires_at")):
            raise ResourceNotFoundError("Transcription draft does not exist")
        if not str(payload.get("transcript") or "").strip():
            raise WriteValidationError("Transcription draft is empty")
        return {
            "object_id": int(refs.get("object_id") or 0),
            "audio_retained": bool(payload.get("audio_retained")),
        }

    def create_application(
        self,
        *,
        job_id: int,
        resume_id: int,
        match_id: int = 0,
        notes: str = "",
        idempotency_key: str,
    ) -> dict:
        clean_notes = str(notes or "").strip()
        if len(clean_notes) > 5_000:
            raise WriteValidationError("Notes exceed 5,000 characters")
        request = {
            "job_id": job_id,
            "resume_id": resume_id,
            "match_id": match_id,
            "notes": clean_notes,
        }
        request_hash = _request_hash(request)
        existing = self._existing("application_create", idempotency_key, request_hash)
        if existing:
            application_id = int(existing.get("result_refs_json", {}).get("application_id", 0))
            result = self._reads.get_application(application_id)
            if result is None:
                raise ResourceNotFoundError("Application does not exist")
            return {"operation": _public_operation(existing, replayed=True), "application": result}
        self._check_recent_limit()
        job = self._ownership.get_job_description(self.user_id, job_id)
        resume = self._ownership.get_resume(self.user_id, resume_id)
        match = self._ownership.get_match(self.user_id, match_id) if match_id else None
        if job is None or resume is None or (match_id and match is None):
            raise ResourceNotFoundError("Linked resource does not exist")
        if match and (int(match["jd_id"]) != job_id or int(match["resume_id"]) != resume_id):
            raise WriteValidationError("Match does not belong to the selected resume and job")
        now = _utc_now()
        with self._database.transaction():
            operation = self._operations.create(
                user_id=self.user_id,
                operation_type="application_create",
                idempotency_key=_validate_idempotency_key(idempotency_key),
                request_hash=request_hash,
                status="running",
                progress=50,
                input_refs_json={"job_id": job_id, "resume_id": resume_id, "match_id": match_id},
                created_at=now,
                started_at=now,
                updated_at=now,
            )
            application_id = self._database.insert(
                "applications",
                Application(
                    user_id=self.user_id,
                    jd_id=job_id,
                    resume_id=resume_id,
                    match_id=match_id,
                    status="saved",
                    notes=clean_notes,
                    updated_at=now,
                ),
            )
            self._database.insert(
                "application_events",
                ApplicationEvent(
                    application_id=application_id,
                    event_type="created",
                    to_status="saved",
                    title="创建申请记录",
                    details=clean_notes,
                    occurred_at=now,
                    created_at=now,
                ),
            )
            self._operations.update(
                operation["id"],
                {
                    "status": "succeeded",
                    "progress": 100,
                    "result_refs_json": {"application_id": application_id},
                    "completed_at": now,
                    "updated_at": now,
                },
            )
        return {
            "operation": _public_operation(
                self._operations.get(self.user_id, operation["id"])
            ),
            "application": self._reads.get_application(application_id),
        }

    def update_application(
        self,
        application_id: int,
        *,
        changes: dict[str, Any],
        idempotency_key: str,
    ) -> dict:
        current = self._ownership.get_application(self.user_id, application_id)
        if current is None:
            raise ResourceNotFoundError("Application does not exist")
        supplied = {key: value for key, value in changes.items() if value is not None}
        request_hash = _request_hash({"application_id": application_id, **supplied})
        existing = self._existing("application_update", idempotency_key, request_hash)
        if existing:
            result = self._reads.get_application(application_id)
            return {"operation": _public_operation(existing, replayed=True), "application": result}
        self._check_recent_limit()
        normalized = _validate_application_changes(current, changes)
        now = _utc_now()
        with self._database.transaction():
            operation = self._operations.create(
                user_id=self.user_id,
                operation_type="application_update",
                idempotency_key=_validate_idempotency_key(idempotency_key),
                request_hash=request_hash,
                status="running",
                progress=50,
                input_refs_json={"application_id": application_id},
                created_at=now,
                started_at=now,
                updated_at=now,
            )
            updates = dict(normalized["updates"])
            updates["updated_at"] = now
            self._database.update("applications", application_id, updates)
            self._database.insert(
                "application_events",
                ApplicationEvent(
                    application_id=application_id,
                    event_type="api_updated",
                    from_status=str(current.get("status") or ""),
                    to_status=str(updates.get("status") or current.get("status") or ""),
                    title="通过 API 更新申请",
                    details=normalized["event_details"],
                    occurred_at=now,
                    created_at=now,
                ),
            )
            self._operations.update(
                operation["id"],
                {
                    "status": "succeeded",
                    "progress": 100,
                    "result_refs_json": {"application_id": application_id},
                    "completed_at": now,
                    "updated_at": now,
                },
            )
        return {
            "operation": _public_operation(
                self._operations.get(self.user_id, operation["id"])
            ),
            "application": self._reads.get_application(application_id),
        }

    def _create_queued_operation(
        self,
        *,
        operation_type: str,
        idempotency_key: str,
        request_hash: str,
        input_refs: dict,
        payload: dict,
        model: str,
        input_units: int,
    ) -> dict:
        now = _utc_now()
        with self._database.transaction():
            operation = self._operations.create(
                user_id=self.user_id,
                operation_type=operation_type,
                idempotency_key=_validate_idempotency_key(idempotency_key),
                request_hash=request_hash,
                status="queued",
                progress=0,
                input_refs_json=input_refs,
                model=model,
                input_units=input_units,
                created_at=now,
                updated_at=now,
            )
            self._operations.store_payload(operation["id"], self.user_id, payload)
        return operation

    def _existing(
        self,
        operation_type: str,
        idempotency_key: str,
        request_hash: str,
    ) -> dict | None:
        key = _validate_idempotency_key(idempotency_key)
        existing = self._operations.get_by_key(self.user_id, operation_type, key)
        if existing and existing.get("request_hash") != request_hash:
            raise IdempotencyConflictError(
                "The idempotency key was already used for a different request"
            )
        return existing

    def _check_limits(self) -> None:
        if self._operations.count_active(self.user_id) >= MAX_ACTIVE_OPERATIONS:
            raise RateLimitError("Too many active operations")
        self._check_recent_limit()

    def _check_recent_limit(self) -> None:
        since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        if self._operations.count_recent(self.user_id, since) >= MAX_OPERATIONS_PER_MINUTE:
            raise RateLimitError("Too many operations in the current minute")


def _public_operation(operation: dict, *, replayed: bool = False) -> dict:
    return {
        "id": int(operation["id"]),
        "operation_type": str(operation["operation_type"]),
        "status": str(operation["status"]),
        "progress": int(operation.get("progress") or 0),
        "input_refs": dict(operation.get("input_refs_json") or {}),
        "result_refs": dict(operation.get("result_refs_json") or {}),
        "error_code": str(operation.get("error_code") or ""),
        "error_message": str(operation.get("error_message") or ""),
        "model": str(operation.get("model") or ""),
        "input_units": int(operation.get("input_units") or 0),
        "output_units": int(operation.get("output_units") or 0),
        "estimated_cost": float(operation.get("estimated_cost") or 0),
        "retry_count": int(operation.get("retry_count") or 0),
        "created_at": str(operation.get("created_at") or ""),
        "started_at": str(operation.get("started_at") or ""),
        "completed_at": str(operation.get("completed_at") or ""),
        "replayed": replayed,
    }


def _validate_idempotency_key(value: str) -> str:
    key = str(value or "").strip()
    if not _IDEMPOTENCY_KEY.fullmatch(key):
        raise WriteValidationError("Invalid Idempotency-Key")
    return key


def _request_hash(value: dict) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _model(capability: str) -> str:
    try:
        return get_active_model(capability)
    except ValueError:
        return "unconfigured"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expired(value: Any) -> bool:
    try:
        expires_at = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _validate_datetime(value: str, field: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    try:
        datetime.strptime(clean, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise WriteValidationError(f"{field} must use YYYY-MM-DD HH:MM") from exc
    return clean


def _validate_application_changes(current: dict, changes: dict[str, Any]) -> dict:
    supplied = {key: value for key, value in changes.items() if value is not None}
    if not supplied:
        raise WriteValidationError("At least one application field is required")
    updates: dict[str, Any] = {}
    details = []
    if "status" in supplied:
        new_status = str(supplied["status"]).strip()
        old_status = str(current.get("status") or "saved")
        if new_status not in STATUS_FLOW.get(old_status, []):
            raise WriteValidationError("Invalid application status transition")
        updates["status"] = new_status
        details.append(f"status:{old_status}->{new_status}")
        if new_status == "applied" and not current.get("applied_date"):
            updates["applied_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "note" in supplied:
        note = str(supplied["note"] or "").strip()
        if not note or len(note) > 5_000:
            raise WriteValidationError("Note must be between 1 and 5,000 characters")
        existing = str(current.get("notes") or "")
        updates["notes"] = f"{existing}\n{note}".strip()
        details.append("note:added")
    if "next_step" in supplied:
        step = str(supplied["next_step"] or "").strip()
        if len(step) > 500:
            raise WriteValidationError("Next step exceeds 500 characters")
        updates["next_step"] = step
        details.append("next_step:updated")
    if "next_step_due" in supplied:
        updates["next_step_due"] = _validate_datetime(
            supplied["next_step_due"],
            "Next step deadline",
        )
        details.append("next_step_due:updated")
    if "interview_at" in supplied:
        updates["interview_at"] = _validate_datetime(
            supplied["interview_at"],
            "Interview time",
        )
        details.append("interview_at:updated")
    return {"updates": updates, "event_details": ", ".join(details)}
