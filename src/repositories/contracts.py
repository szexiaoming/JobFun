"""Persistence ports used by application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    user_id: int
    username: str
    roles: tuple[str, ...] = ()


class AuthRepository(Protocol):
    def find_principal_by_token_hash(
        self,
        token_hash: str,
        now: str,
    ) -> AuthPrincipal | None: ...

    def touch_token(self, token_hash: str, used_at: str) -> None: ...

    def create_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        label: str,
        expires_at: str,
        created_at: str,
    ) -> int | None: ...

    def revoke_token(self, *, user_id: int, token_id: int, revoked_at: str) -> bool: ...


class OwnershipRepository(Protocol):
    def list_resumes(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    def list_job_descriptions(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    def list_matches(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    def list_applications(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    def get_resume(self, user_id: int, resource_id: int) -> dict[str, Any] | None: ...

    def get_job_description(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def get_match(self, user_id: int, resource_id: int) -> dict[str, Any] | None: ...

    def get_application(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def get_evidence_match(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def list_match_evidence(
        self,
        user_id: int,
        match_id: int,
    ) -> list[dict[str, Any]]: ...

    def get_interview_question(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def list_interview_questions(
        self,
        user_id: int,
        application_id: int,
    ) -> list[dict[str, Any]]: ...

    def get_interview_attempt(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def get_interview_follow_up(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None: ...

    def get_workbench_summary(self, user_id: int) -> Any: ...

    def get_interview_insights(self, user_id: int, application_id: int) -> Any: ...


class OperationRepository(Protocol):
    def get(self, user_id: int, operation_id: int) -> dict[str, Any] | None: ...

    def get_by_key(
        self,
        user_id: int,
        operation_type: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    def create(self, **values) -> dict[str, Any]: ...

    def update(self, operation_id: int, updates: dict[str, Any]) -> None: ...

    def count_active(self, user_id: int) -> int: ...

    def count_recent(self, user_id: int, since: str) -> int: ...

    def store_payload(self, operation_id: int, user_id: int, payload: dict) -> None: ...

    def get_payload(self, operation_id: int, user_id: int) -> dict | None: ...

    def delete_payload(self, operation_id: int, user_id: int) -> None: ...

    def list_queued(self, limit: int = 10) -> list[dict[str, Any]]: ...

    def claim(self, operation_id: int, started_at: str) -> bool: ...


class StoredObjectRepository(Protocol):
    def get(self, user_id: int, object_id: int) -> dict[str, Any] | None: ...

    def get_by_idempotency(
        self,
        user_id: int,
        kind: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    def create(self, **values) -> dict[str, Any]: ...

    def mark_deleted(self, user_id: int, object_id: int, deleted_at: str) -> None: ...

    def list_retained_audio(self, user_id: int) -> list[dict[str, Any]]: ...

    def list_expired_audio(self, cutoff: str, limit: int) -> list[dict[str, Any]]: ...

    def clear_audio_reference(self, object_key: str) -> None: ...


class PrivacyRepository(Protocol):
    def create_deletion_challenge(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: str,
        created_at: str,
    ) -> None: ...

    def export_snapshot(self, user_id: int) -> dict[str, Any] | None: ...

    def record_audit(self, **values) -> int: ...

    def delete_user_data(
        self,
        *,
        user_id: int,
        token_hash: str,
        now: str,
        correlation_id: str,
        subject_hash: str,
        request_id: str,
    ) -> dict[str, Any] | None: ...

    def list_cleanup_jobs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def complete_cleanup(self, job_id: int) -> None: ...

    def fail_cleanup(self, job_id: int, updated_at: str) -> None: ...

    def update_deletion_audit(self, audit_id: int, cleanup_pending: int) -> None: ...
