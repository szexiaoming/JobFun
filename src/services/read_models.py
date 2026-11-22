"""Ownership-scoped read use cases shared by local and HTTP adapters."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from src.repositories.contracts import OwnershipRepository
from src.services.context import RequestContext


class ReadApplicationService:
    def __init__(
        self,
        context: RequestContext,
        repository: OwnershipRepository,
    ) -> None:
        if context.user_id is None or context.user_id <= 0:
            raise ValueError("An authenticated user context is required")
        self.context = context
        self._repository = repository

    @property
    def user_id(self) -> int:
        return int(self.context.user_id)

    def get_workbench(self) -> dict[str, Any]:
        return asdict(self._repository.get_workbench_summary(self.user_id))

    def list_resumes(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        _validate_page(limit, offset)
        rows = self._repository.list_resumes(
            self.user_id,
            limit=limit,
            offset=offset,
        )
        return [_resume(row, include_content=False) for row in rows]

    def get_resume(self, resume_id: int) -> dict | None:
        row = self._repository.get_resume(self.user_id, resume_id)
        return _resume(row, include_content=True) if row else None

    def list_jobs(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        _validate_page(limit, offset)
        jobs = self._repository.list_job_descriptions(
            self.user_id,
            limit=limit,
            offset=offset,
        )
        matches = self._repository.list_matches(self.user_id, limit=1000, offset=0)
        applications = self._repository.list_applications(
            self.user_id,
            limit=1000,
            offset=0,
        )
        return [_job(row, matches, applications, include_content=False) for row in jobs]

    def get_job(self, job_id: int) -> dict | None:
        row = self._repository.get_job_description(self.user_id, job_id)
        if row is None:
            return None
        matches = self._repository.list_matches(self.user_id, limit=1000, offset=0)
        applications = self._repository.list_applications(
            self.user_id,
            limit=1000,
            offset=0,
        )
        return _job(row, matches, applications, include_content=True)

    def list_applications(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        _validate_page(limit, offset)
        rows = self._repository.list_applications(
            self.user_id,
            limit=limit,
            offset=offset,
        )
        return [self._application(row, include_content=False) for row in rows]

    def get_application(self, application_id: int) -> dict | None:
        row = self._repository.get_application(self.user_id, application_id)
        return self._application(row, include_content=True) if row else None

    def get_interview_insights(self, application_id: int) -> dict | None:
        insights = self._repository.get_interview_insights(
            self.user_id,
            application_id,
        )
        return asdict(insights) if insights is not None else None

    def list_interview_questions(self, application_id: int) -> list[dict] | None:
        if self._repository.get_application(self.user_id, application_id) is None:
            return None
        rows = self._repository.list_interview_questions(
            self.user_id,
            application_id,
        )
        result = []
        for row in rows:
            latest_attempt_id = int(row.get("latest_attempt_id") or 0)
            latest_attempt = (
                self._repository.get_interview_attempt(self.user_id, latest_attempt_id)
                if latest_attempt_id
                else None
            )
            result.append(
                {
                    "id": int(row["id"]),
                    "category": str(row.get("category") or "general"),
                    "question": str(row.get("question") or ""),
                    "difficulty": str(row.get("difficulty") or "medium"),
                    "attempt_count": int(row.get("attempt_count") or 0),
                    "latest_attempt_id": latest_attempt_id or None,
                    "latest_score": (
                        _attempt_score(latest_attempt) if latest_attempt else None
                    ),
                }
            )
        return result

    def get_interview_attempt(self, attempt_id: int) -> dict | None:
        row = self._repository.get_interview_attempt(self.user_id, attempt_id)
        if row is None:
            return None
        question = self._repository.get_interview_question(
            self.user_id,
            int(row["question_id"]),
        )
        if question is None:
            return None
        scores = {
            "completeness": float(row.get("completeness_score") or 0),
            "truthfulness": float(row.get("truthfulness_score") or 0),
            "technical": float(row.get("technical_score") or 0),
            "structure": float(row.get("structure_score") or 0),
        }
        return {
            "id": int(row["id"]),
            "question_id": int(row["question_id"]),
            "application_id": int(row["application_id"]),
            "question": str(question.get("question") or ""),
            "category": str(question.get("category") or "general"),
            "answer_text": str(row.get("answer_text") or ""),
            "scores": scores,
            "overall_score": round(sum(scores.values()) / len(scores), 2),
            "feedback": _json_object(row.get("feedback_json")),
            "answer_mode": "voice" if str(row.get("transcript") or "").strip() else "text",
            "audio_retained": bool(str(row.get("audio_path") or "").strip()),
            "created_at": str(row.get("created_at") or ""),
        }

    def _application(self, row: dict, *, include_content: bool) -> dict:
        job_row = self._repository.get_job_description(self.user_id, int(row["jd_id"]))
        resume_row = self._repository.get_resume(self.user_id, int(row["resume_id"]))
        match_id = int(row.get("match_id") or 0)
        match_row = self._repository.get_match(self.user_id, match_id) if match_id else None
        result = {
            "id": int(row["id"]),
            "status": str(row.get("status") or "saved"),
            "applied_date": str(row.get("applied_date") or ""),
            "next_step": str(row.get("next_step") or ""),
            "next_step_due": str(row.get("next_step_due") or ""),
            "interview_at": str(row.get("interview_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "job": _job_reference(job_row),
            "resume": _resume_reference(resume_row),
            "match": _match(match_row) if match_row else None,
        }
        if include_content:
            result["notes"] = str(row.get("notes") or "")
            result["resume"]["structured_json"] = _json_object(
                resume_row.get("structured_json") if resume_row else None
            )
            result["job"]["structured_json"] = _json_object(
                job_row.get("structured_json") if job_row else None
            )
        return result


def _resume(row: dict, *, include_content: bool) -> dict:
    result = {
        "id": int(row["id"]),
        "name": str(row.get("name") or "未命名简历"),
        "base_version": int(row.get("base_version") or 0),
        "parent_id": row.get("parent_id"),
        "created_at": str(row.get("created_at") or ""),
        "is_active": bool(row.get("is_active", 1)),
    }
    if include_content:
        result["structured_json"] = _json_object(row.get("structured_json"))
    return result


def _resume_reference(row: dict | None) -> dict:
    if row is None:
        return {
            "id": 0,
            "name": "不可读取",
            "base_version": 0,
            "structured_json": None,
        }
    return {
        "id": int(row["id"]),
        "name": str(row.get("name") or "未命名简历"),
        "base_version": int(row.get("base_version") or 0),
        "structured_json": None,
    }


def _job(
    row: dict,
    matches: list[dict],
    applications: list[dict],
    *,
    include_content: bool,
) -> dict:
    structured = _json_object(row.get("structured_json"))
    job_matches = [match for match in matches if match.get("jd_id") == row["id"]]
    job_applications = [
        application for application in applications if application.get("jd_id") == row["id"]
    ]
    latest = max(job_matches, key=lambda item: item.get("id", 0), default=None)
    result = {
        "id": int(row["id"]),
        "company": str(row.get("company") or structured.get("company") or "未填写公司"),
        "position": str(row.get("position") or structured.get("position") or "未填写岗位"),
        "source_type": str(row.get("source_type") or "text"),
        "source_url": str(row.get("source_url") or ""),
        "created_at": str(row.get("created_at") or ""),
        "match_count": len(job_matches),
        "application_count": len(job_applications),
        "latest_match": _match(latest) if latest else None,
    }
    if include_content:
        result["raw_text"] = str(row.get("raw_text") or "")
        result["structured_json"] = structured
    return result


def _job_reference(row: dict | None) -> dict:
    if row is None:
        return {
            "id": 0,
            "company": "不可读取",
            "position": "不可读取",
            "structured_json": None,
        }
    structured = _json_object(row.get("structured_json"))
    return {
        "id": int(row["id"]),
        "company": str(row.get("company") or structured.get("company") or "未填写公司"),
        "position": str(row.get("position") or structured.get("position") or "未填写岗位"),
        "structured_json": None,
    }


def _match(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "total_score": float(row.get("total_score") or 0),
        "skill_score": float(row.get("skill_score") or 0),
        "experience_score": float(row.get("experience_score") or 0),
        "education_score": float(row.get("education_score") or 0),
        "soft_skill_score": float(row.get("soft_skill_score") or 0),
        "culture_score": float(row.get("culture_score") or 0),
        "matched_skills": _json_list(row.get("matched_skills")),
        "missing_skills": _json_list(row.get("missing_skills")),
        "risks": _json_list(row.get("risks")),
        "created_at": str(row.get("created_at") or ""),
    }


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


def _attempt_score(row: dict) -> float:
    values = [
        float(row.get("completeness_score") or 0),
        float(row.get("truthfulness_score") or 0),
        float(row.get("technical_score") or 0),
        float(row.get("structure_score") or 0),
    ]
    return round(sum(values) / len(values), 2)


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Pagination is outside the supported range")
