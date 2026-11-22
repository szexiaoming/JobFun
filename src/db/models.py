"""
Data models for JobFun. Plain dataclasses — no ORM.
All JSON-serializable fields use dict/list typing for direct JSON storage.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: Optional[int] = None
    username: str = "default"
    settings: dict = field(default_factory=dict)
    created_at: str = ""
    is_active: bool = True


@dataclass
class ApiToken:
    id: Optional[int] = None
    user_id: int = 0
    token_hash: str = ""
    label: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    last_used_at: str = ""
    created_at: str = ""


@dataclass
class OperationJob:
    id: Optional[int] = None
    user_id: int = 0
    operation_type: str = ""
    idempotency_key: str = ""
    request_hash: str = ""
    status: str = "queued"
    progress: int = 0
    input_refs_json: dict = field(default_factory=dict)
    result_refs_json: dict = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    model: str = ""
    input_units: int = 0
    output_units: int = 0
    estimated_cost: float = 0.0
    retry_count: int = 0
    max_retries: int = 2
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""


@dataclass
class WorkerHeartbeat:
    id: Optional[int] = None
    worker_name: str = "default"
    status: str = "idle"
    last_seen_at: str = ""
    last_started_at: str = ""
    last_completed_at: str = ""
    last_operation_id: int = 0
    last_error_code: str = ""
    processed_total: int = 0
    failed_total: int = 0


@dataclass
class MaintenanceRun:
    id: Optional[int] = None
    task_name: str = ""
    status: str = "idle"
    last_started_at: str = ""
    last_completed_at: str = ""
    last_checked: int = 0
    last_deleted: int = 0
    last_failed: int = 0
    consecutive_failures: int = 0
    run_total: int = 0
    deleted_total: int = 0
    failed_total: int = 0
    last_error_code: str = ""


@dataclass
class MaintenanceRunEvent:
    id: Optional[int] = None
    task_name: str = ""
    status: str = "succeeded"
    started_at: str = ""
    completed_at: str = ""
    checked_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    error_code: str = ""


@dataclass
class RetentionPolicy:
    id: Optional[int] = None
    policy_name: str = ""
    retention_days: int = 0
    observed_at: str = ""


@dataclass
class RetentionPolicyAuditEvent:
    id: Optional[int] = None
    policy_name: str = ""
    previous_days: int = 0
    new_days: int = 0
    changed_at: str = ""
    source: str = "configuration"


@dataclass
class StoredObject:
    id: Optional[int] = None
    user_id: int = 0
    object_key: str = ""
    kind: str = ""
    original_name: str = ""
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str = ""
    idempotency_key: str = ""
    status: str = "available"
    created_at: str = ""
    deleted_at: str = ""


@dataclass
class PrivacyDeletionChallenge:
    id: Optional[int] = None
    user_id: int = 0
    token_hash: str = ""
    expires_at: str = ""
    created_at: str = ""


@dataclass
class PrivacyAuditEvent:
    id: Optional[int] = None
    correlation_id: str = ""
    subject_hash: str = ""
    event_type: str = ""
    status: str = "completed"
    request_id: str = ""
    details_json: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class ObjectCleanupJob:
    id: Optional[int] = None
    object_key: str = ""
    status: str = "pending"
    attempts: int = 0
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Resume:
    id: Optional[int] = None
    user_id: int = 1
    name: str = ""  # e.g. "Backend SDE 2026"
    base_version: int = 0  # 0 = original
    parent_id: Optional[int] = None  # version chain
    latex_path: str = ""  # directory path on disk
    pdf_path: str = ""
    structured_json: dict = field(default_factory=dict)
    created_at: str = ""
    is_active: bool = True


@dataclass
class JobDescription:
    id: Optional[int] = None
    user_id: int = 1
    company: str = ""
    position: str = ""
    raw_text: str = ""
    source_type: str = "text"  # text | image | pdf
    source_file: str = ""
    structured_json: dict = field(default_factory=dict)
    source_url: str = ""
    created_at: str = ""


@dataclass
class MatchResult:
    id: Optional[int] = None
    resume_id: int = 0
    jd_id: int = 0
    total_score: float = 0.0
    skill_score: float = 0.0
    experience_score: float = 0.0
    education_score: float = 0.0
    soft_skill_score: float = 0.0
    culture_score: float = 0.0
    matched_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    raw_report: str = ""
    created_at: str = ""


@dataclass
class JobRequirement:
    id: Optional[int] = None
    jd_id: int = 0
    category: str = "required"  # responsibility | required | preferred | education | experience
    text: str = ""
    normalized_key: str = ""
    priority: int = 0
    source_span: str = ""
    created_at: str = ""


@dataclass
class EvidenceMatch:
    id: Optional[int] = None
    match_id: int = 0
    requirement_id: int = 0
    status: str = "uncertain"  # proven | partial | missing | uncertain
    evidence_json: list = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0
    needs_user_confirmation: bool = False
    recommended_action: str = ""
    user_status: str = ""  # confirmed | rejected | corrected
    user_note: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EvidenceReview:
    id: Optional[int] = None
    evidence_match_id: int = 0
    match_id: int = 0
    requirement_id: int = 0
    action: str = "confirmed"  # confirmed | rejected | corrected
    previous_status: str = ""
    corrected_status: str = ""
    previous_evidence_json: list = field(default_factory=list)
    corrected_evidence_json: list = field(default_factory=list)
    note: str = ""
    created_at: str = ""


@dataclass
class EvidenceSupplement:
    id: Optional[int] = None
    match_id: int = 0
    requirement_id: int = 0
    evidence_match_id: Optional[int] = None
    title: str = ""
    description: str = ""
    context_type: str = "other"  # work | project | education | volunteering | other
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    source_type: str = "user_supplied"
    status: str = "draft"  # draft | confirmed | rejected
    user_attested: bool = False
    eligible_for_matching: bool = False
    eligible_for_resume_edit: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EvidenceSupplementEvent:
    id: Optional[int] = None
    supplement_id: int = 0
    event_type: str = "created"  # created | updated | confirmed | rejected
    snapshot_json: dict = field(default_factory=dict)
    note: str = ""
    created_at: str = ""


@dataclass
class Suggestion:
    id: Optional[int] = None
    match_id: int = 0
    category: str = ""  # keyword | structure | wording | highlight | de_emphasize | quantify
    priority: int = 0
    original_text: str = ""
    suggested_text: str = ""
    rationale: str = ""
    status: str = "pending"  # pending | accepted | rejected | modified
    created_at: str = ""


@dataclass
class Application:
    id: Optional[int] = None
    user_id: int = 1
    jd_id: int = 0
    resume_id: int = 0
    match_id: int = 0
    status: str = "saved"  # saved | applied | oa | interview | offer | rejected | withdrawn
    applied_date: str = ""
    notes: str = ""
    next_step: str = ""
    next_step_due: str = ""
    interview_at: str = ""
    updated_at: str = ""


@dataclass
class ApplicationEvent:
    id: Optional[int] = None
    application_id: int = 0
    event_type: str = "created"
    from_status: str = ""
    to_status: str = ""
    title: str = ""
    details: str = ""
    occurred_at: str = ""
    created_at: str = ""


@dataclass
class InterviewQuestion:
    id: Optional[int] = None
    match_id: int = 0
    category: str = ""  # technical | project_deep_dive | behavioral | english | system_design
    question: str = ""
    suggested_answer: str = ""
    difficulty: str = "medium"  # easy | medium | hard
    created_at: str = ""


@dataclass
class InterviewAttempt:
    id: Optional[int] = None
    question_id: int = 0
    application_id: int = 0
    answer_text: str = ""
    audio_path: str = ""
    transcript: str = ""
    completeness_score: float = 0.0
    truthfulness_score: float = 0.0
    technical_score: float = 0.0
    structure_score: float = 0.0
    feedback_json: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class InterviewFollowUp:
    id: Optional[int] = None
    parent_attempt_id: int = 0
    question_id: int = 0
    target_dimension: str = ""
    rationale: str = ""
    created_at: str = ""


@dataclass
class LatexChange:
    id: Optional[int] = None
    resume_id: int = 0
    suggestion_id: int = 0
    file_path: str = ""
    old_content: str = ""
    new_content: str = ""
    commit_hash: str = ""
    created_at: str = ""


# ── Helper: map table name → model class ──────────────
TABLE_MAP = {
    "users": User,
    "api_tokens": ApiToken,
    "operation_jobs": OperationJob,
    "worker_heartbeats": WorkerHeartbeat,
    "maintenance_runs": MaintenanceRun,
    "maintenance_run_events": MaintenanceRunEvent,
    "retention_policies": RetentionPolicy,
    "retention_policy_audit_events": RetentionPolicyAuditEvent,
    "stored_objects": StoredObject,
    "privacy_deletion_challenges": PrivacyDeletionChallenge,
    "privacy_audit_events": PrivacyAuditEvent,
    "object_cleanup_jobs": ObjectCleanupJob,
    "resumes": Resume,
    "job_descriptions": JobDescription,
    "match_results": MatchResult,
    "job_requirements": JobRequirement,
    "evidence_matches": EvidenceMatch,
    "evidence_reviews": EvidenceReview,
    "evidence_supplements": EvidenceSupplement,
    "evidence_supplement_events": EvidenceSupplementEvent,
    "suggestions": Suggestion,
    "applications": Application,
    "application_events": ApplicationEvent,
    "interview_questions": InterviewQuestion,
    "interview_attempts": InterviewAttempt,
    "interview_follow_ups": InterviewFollowUp,
    "latex_changes": LatexChange,
}
