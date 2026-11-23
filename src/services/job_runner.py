"""Durable local worker for queued AI operations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import config
from src.ai.client import get_ai_client
from src.core.audio_transcription import transcribe_interview_audio
from src.core.evidence_matcher import prepare_job_requirements, run_evidence_match
from src.core.interview_practice import evaluate_text_answer
from src.core.latex_parser import parse_resume_text
from src.core.match_engine import run_match
from src.db.models import Resume
from src.db.sqlite_client import Database, row_to_model
from src.repositories.operations import SQLiteOperationRepository
from src.repositories.sqlite_ownership import SQLiteOwnershipRepository
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.repositories.worker_health import WorkerHeartbeatRepository
from src.services.gap_explanations import (
    build_explanation, json_object, requirement_options, resume_candidates,
    verified_evidence,
)
from src.services.alerts import configured_alert_sink
from src.storage.local import LocalObjectStore
from src.storage.s3 import S3ObjectStore
from src.utils.logger import logger


class OperationRunner:
    def __init__(
        self,
        database: Database,
        *,
        client=None,
        transcription_client=None,
        object_store=None,
        alert_sink=None,
        worker_name: str | None = None,
    ):
        self._database = database
        self._operations = SQLiteOperationRepository(database)
        self._ownership = SQLiteOwnershipRepository(database)
        self._stored_objects = StoredObjectDatabaseRepository(database)
        self._client = client
        self._transcription_client = transcription_client
        self._object_store = object_store or _configured_object_store()
        self._heartbeats = WorkerHeartbeatRepository(database)
        self._alert_sink = alert_sink or configured_alert_sink()
        self._worker_name = str(worker_name or config.WORKER_NAME)

    def run_next(self, limit: int = 1) -> list[int]:
        self._record_heartbeat(status="idle")
        completed = []
        for operation in self._operations.list_queued(limit=limit):
            if self.run_one(int(operation["id"])):
                completed.append(int(operation["id"]))
        return completed

    def run_one(self, operation_id: int) -> bool:
        operation = self._operations.get_any(operation_id)
        if operation is None:
            return False
        started_at = _utc_now()
        if not self._operations.claim(operation_id, started_at):
            return False
        self._record_heartbeat(
            status="running",
            operation_id=operation_id,
            started_at=started_at,
            error_code="",
        )
        operation = self._operations.get_any(operation_id)
        payload = self._operations.get_payload(operation_id, int(operation["user_id"]))
        if payload is None:
            self._fail(operation, "operation_payload_missing", retryable=False)
            return True
        try:
            result_refs, output_units, estimated_cost, retained_payload = self._dispatch(
                operation, payload
            )
        except Exception as exc:
            logger.error(
                "operation_failed",
                extra={
                    "event": "operation_failed",
                    "operation_id": operation_id,
                    "operation_type": str(operation.get("operation_type") or ""),
                    "error_type": type(exc).__name__,
                    "retry_count": int(operation.get("retry_count") or 0) + 1,
                    "status": "retrying",
                },
            )
            self._fail(operation, "operation_execution_failed", retryable=True)
            return True

        completed_at = _utc_now()
        with self._database.transaction():
            self._operations.update(
                operation_id,
                {
                    "status": "succeeded",
                    "progress": 100,
                    "result_refs_json": result_refs,
                    "output_units": output_units,
                    "estimated_cost": estimated_cost,
                    "error_code": "",
                    "error_message": "",
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                },
            )
            self._operations.delete_payload(operation_id, int(operation["user_id"]))
            if retained_payload is not None:
                self._operations.store_payload(
                    operation_id,
                    int(operation["user_id"]),
                    retained_payload,
                )
        self._record_heartbeat(
            status="idle",
            operation_id=operation_id,
            completed_at=completed_at,
            error_code="",
            processed_delta=1,
        )
        return True

    def _dispatch(
        self,
        operation: dict,
        payload: dict,
    ) -> tuple[dict, int, float, dict | None]:
        operation_type = operation["operation_type"]
        user_id = int(operation["user_id"])
        refs = operation.get("input_refs_json") or {}
        client = self._client
        if operation_type not in {"interview_transcription", "gap_explanation"}:
            client = client or get_ai_client()

        if operation_type == "resume_parse":
            resume_id = int(refs["resume_id"])
            if self._ownership.get_resume(user_id, resume_id) is None:
                raise ValueError("Resume not owned")
            structured = parse_resume_text(payload["text"], client=client)
            self._database.update(
                "resumes",
                resume_id,
                {"structured_json": json.dumps(structured, ensure_ascii=False)},
            )
            return {"resume_id": resume_id}, len(json.dumps(structured)), 0.0, None

        if operation_type == "jd_parse":
            job_id = int(refs["job_id"])
            if self._ownership.get_job_description(user_id, job_id) is None:
                raise ValueError("Job not owned")
            structured = client.extract_jd_from_text(payload["text"])
            self._database.update(
                "job_descriptions",
                job_id,
                {
                    "company": str(structured.get("company") or ""),
                    "position": str(structured.get("position") or ""),
                    "structured_json": json.dumps(structured, ensure_ascii=False),
                },
            )
            if structured:
                prepare_job_requirements(job_id, structured, db=self._database)
            return {"job_id": job_id}, len(json.dumps(structured)), 0.0, None

        if operation_type == "match":
            resume_id = int(refs["resume_id"])
            job_id = int(refs["job_id"])
            resume_row = self._ownership.get_resume(user_id, resume_id)
            job_row = self._ownership.get_job_description(user_id, job_id)
            if resume_row is None or job_row is None:
                raise ValueError("Match inputs not owned")
            resume = row_to_model(resume_row, Resume)
            resume_json = _json_object(resume_row.get("structured_json"))
            job_json = _json_object(job_row.get("structured_json"))
            report = run_match(
                resume,
                job_json,
                resume_json,
                jd_id=job_id,
                db=self._database,
                client=client,
            )
            match_id = int(report["match_result"].id)
            if job_json:
                prepare_job_requirements(job_id, job_json, db=self._database)
            return {"match_id": match_id}, len(json.dumps(job_json)) + len(json.dumps(resume_json)), 0.0, None

        if operation_type == "gap_explanation":
            application_id = int(refs["application_id"])
            application = self._ownership.get_application(user_id, application_id)
            if application is None or not int(application.get("match_id") or 0):
                raise ValueError("Gap explanation application not owned")
            match_id = int(application["match_id"])
            resume_id = int(application["resume_id"])
            job_id = int(application["jd_id"])
            match = self._ownership.get_match(user_id, match_id)
            resume = self._ownership.get_resume(user_id, resume_id)
            job = self._ownership.get_job_description(user_id, job_id)
            if (
                match is None or resume is None or job is None
                or int(match["resume_id"]) != resume_id or int(match["jd_id"]) != job_id
            ):
                raise ValueError("Gap explanation inputs not owned")
            resume_json = json_object(resume.get("structured_json"))
            job_json = json_object(job.get("structured_json"))
            key = str(payload.get("requirement_key") or "")
            requirement = next(
                (item for item in requirement_options(job_id, job_json) if item["key"] == key),
                None,
            )
            if requirement is None:
                raise ValueError("Requirement is not part of the pinned job")
            active_requirements = prepare_job_requirements(job_id, job_json, db=self._database)
            selected = next((item for item in active_requirements if item.normalized_key == key), None)
            if selected is None:
                raise ValueError("Requirement is not persisted")
            evidence_rows = self._ownership.list_match_evidence(user_id, match_id)
            evidence_row = next((item for item in evidence_rows if item["requirement_id"] == selected.id), None)
            if evidence_row is None:
                try:
                    run_evidence_match(
                        match_id, job_id, resume_json,
                        requirements=active_requirements,
                        db=self._database,
                        client=client,
                    )
                    evidence_rows = self._ownership.list_match_evidence(user_id, match_id)
                    evidence_row = next((item for item in evidence_rows if item["requirement_id"] == selected.id), None)
                except Exception as exc:
                    logger.warning("gap_evidence_unavailable: %s", type(exc).__name__)
            from src.ai.langchain_gap import propose_gap_action

            _, verified = verified_evidence(evidence_row, resume_json)
            candidates = resume_candidates(resume_json)
            draft = propose_gap_action(
                requirement, verified, candidates,
                user_id=user_id, resume_id=resume_id,
            )
            result = build_explanation(
                application_id=application_id,
                requirement=requirement,
                evidence_row=evidence_row,
                resume_json=resume_json,
                agent_draft=draft,
            )
            return (
                {"application_id": application_id, "requirement_id": int(selected.id)},
                len(json.dumps(result, ensure_ascii=False)),
                0.0,
                {"result": result},
            )

        if operation_type == "interview_transcription":
            object_id = int(refs["object_id"])
            stored = self._stored_objects.get(user_id, object_id)
            if stored is None or str(stored.get("kind") or "") != "interview_audio":
                raise ValueError("Interview audio not owned")
            audio_bytes = self._object_store.read(
                str(stored["object_key"]),
                max_bytes=config.MAX_INTERVIEW_AUDIO_SIZE_MB * 1024 * 1024,
            )
            transcription = transcribe_interview_audio(
                audio_bytes,
                str(stored.get("original_name") or "audio.webm"),
                str(stored.get("content_type") or "application/octet-stream"),
                client=self._transcription_client,
            )
            retain_audio = bool(int(refs.get("retain_audio") or 0))
            if not retain_audio:
                self._object_store.delete(str(stored["object_key"]))
                self._stored_objects.mark_deleted(user_id, object_id, _utc_now())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            retained = {
                "object_id": object_id,
                "transcript": transcription.text,
                "original_name": str(stored.get("original_name") or ""),
                "content_type": str(stored.get("content_type") or ""),
                "size_bytes": int(stored.get("size_bytes") or 0),
                "audio_retained": retain_audio,
                "expires_at": expires_at,
            }
            return {"object_id": object_id, "draft_ready": 1}, len(transcription.text), 0.0, retained

        if operation_type == "interview_answer":
            application_id = int(refs["application_id"])
            question_id = int(refs["question_id"])
            application = self._ownership.get_application(user_id, application_id)
            question = self._ownership.get_interview_question(user_id, question_id)
            if application is None or question is None:
                raise ValueError("Interview inputs not owned")
            transcription_operation_id = int(
                payload.get("transcription_operation_id") or 0
            )
            audio_object_id = int(payload.get("audio_object_id") or 0)
            retain_audio = bool(payload.get("retain_audio"))
            audio_path = ""
            transcript = str(payload.get("transcript") or "")
            if transcription_operation_id:
                stored = self._stored_objects.get(user_id, audio_object_id)
                if stored is None:
                    if retain_audio:
                        raise ValueError("Interview audio not owned")
                elif str(stored.get("kind") or "") != "interview_audio":
                    raise ValueError("Interview audio not owned")
                elif retain_audio:
                    audio_path = str(stored["object_key"])
                else:
                    self._object_store.delete(str(stored["object_key"]))
                    self._stored_objects.mark_deleted(user_id, audio_object_id, _utc_now())
            evaluation = evaluate_text_answer(
                question_id,
                payload["answer_text"],
                application_id=application_id,
                db=self._database,
                client=client,
                audio_path=audio_path,
                transcript=transcript,
            )
            if transcription_operation_id:
                self._operations.delete_payload(
                    transcription_operation_id,
                    user_id,
                )
            return {"attempt_id": evaluation.attempt_id}, len(json.dumps(evaluation.feedback)), 0.0, None

        raise ValueError("Unsupported operation type")

    def _fail(self, operation: dict, error_code: str, *, retryable: bool) -> None:
        updated_at = _utc_now()
        retry_count = int(operation.get("retry_count") or 0) + 1
        retry_scheduled = retryable and retry_count <= int(operation.get("max_retries") or 0)
        self._operations.update(
            int(operation["id"]),
            {
                "status": "queued" if retry_scheduled else "failed",
                "progress": 0 if retry_scheduled else 100,
                "error_code": "operation_retry_scheduled" if retry_scheduled else error_code,
                "error_message": (
                    "操作暂未完成，已安排自动重试"
                    if retry_scheduled
                    else "操作未完成，请稍后重试"
                ),
                "retry_count": retry_count,
                "started_at": "" if retry_scheduled else operation.get("started_at", ""),
                "completed_at": "" if retry_scheduled else updated_at,
                "updated_at": updated_at,
            },
        )
        operation_id = int(operation["id"])
        self._record_heartbeat(
            status="idle" if retry_scheduled else "error",
            operation_id=operation_id,
            completed_at="" if retry_scheduled else updated_at,
            error_code=("operation_retry_scheduled" if retry_scheduled else error_code),
            processed_delta=0 if retry_scheduled else 1,
            failed_delta=0 if retry_scheduled else 1,
        )
        if not retry_scheduled:
            event = {
                "event_type": "operation_failed",
                "severity": "error",
                "operation_id": operation_id,
                "operation_type": str(operation.get("operation_type") or ""),
                "error_code": error_code,
                "retry_count": retry_count,
                "occurred_at": updated_at,
            }
            try:
                self._alert_sink.send(event)
            except Exception as exc:
                logger.warning(
                    "alert_delivery_failed",
                    extra={
                        "event": "alert_delivery_failed",
                        "operation_id": operation_id,
                        "operation_type": str(operation.get("operation_type") or ""),
                        "error_type": type(exc).__name__,
                        "status": "failed",
                    },
                )

    def _record_heartbeat(
        self,
        *,
        status: str,
        operation_id: int | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_code: str | None = None,
        processed_delta: int = 0,
        failed_delta: int = 0,
    ) -> None:
        self._heartbeats.record(
            worker_name=self._worker_name,
            status=status,
            last_seen_at=_utc_now(),
            last_started_at=started_at,
            last_completed_at=completed_at,
            last_operation_id=operation_id,
            last_error_code=error_code,
            processed_delta=processed_delta,
            failed_delta=failed_delta,
        )


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured_object_store():
    if config.OBJECT_STORAGE_BACKEND == "local":
        return LocalObjectStore(config.OBJECT_STORAGE_DIR)
    if config.OBJECT_STORAGE_BACKEND == "s3":
        return S3ObjectStore(
            config.S3_BUCKET,
            region=config.S3_REGION,
            endpoint_url=config.S3_ENDPOINT_URL,
            kms_key_id=config.S3_KMS_KEY_ID,
        )
    raise RuntimeError(f"Unsupported object storage backend: {config.OBJECT_STORAGE_BACKEND}")
