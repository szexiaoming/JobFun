"""HTTP-only response schemas. Database models must not be exposed directly."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ok", "failed"]]


class WorkerHealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    worker_status: str
    heartbeat_age_seconds: int | None = None
    queued_operations: int = 0
    running_operations: int = 0
    failed_operations_24h: int = 0
    stale_running_operations: int = 0
    oldest_queued_age_seconds: int | None = None
    processed_total: int = 0
    failed_total: int = 0
    checks: dict[str, str] = Field(default_factory=dict)


class MaintenanceTrendResponse(BaseModel):
    window_runs: int = 0
    success_rate_percent: float = 0.0
    checked_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0


class MaintenanceRunHistoryResponse(BaseModel):
    status: str
    completed_at: str
    checked_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    error_code: str = ""


class MaintenanceHealthResponse(BaseModel):
    status: Literal["healthy", "warning", "degraded"]
    task_status: str
    last_completed_age_seconds: int | None = None
    last_started_age_seconds: int | None = None
    last_checked: int = 0
    last_deleted: int = 0
    last_failed: int = 0
    consecutive_failures: int = 0
    run_total: int = 0
    deleted_total: int = 0
    failed_total: int = 0
    checks: dict[str, str] = Field(default_factory=dict)
    trend: MaintenanceTrendResponse = Field(default_factory=MaintenanceTrendResponse)
    recent_runs: list[MaintenanceRunHistoryResponse] = Field(default_factory=list)


class VersionResponse(BaseModel):
    api_version: Literal["v1"] = "v1"
    service: str
    version: str


class MeResponse(BaseModel):
    id: int
    username: str
    roles: list[str] = Field(default_factory=list)


class WorkbenchItemResponse(BaseModel):
    application_id: int
    jd_id: int
    company: str
    position: str
    status: str
    next_step: str = ""
    next_step_due: str = ""
    interview_at: str = ""
    is_overdue: bool = False


class WorkbenchResponse(BaseModel):
    total_applications: int
    active_applications: int
    pending_actions: list[WorkbenchItemResponse] = Field(default_factory=list)
    overdue_actions: list[WorkbenchItemResponse] = Field(default_factory=list)
    upcoming_interviews: list[WorkbenchItemResponse] = Field(default_factory=list)


class ResumeSummaryResponse(BaseModel):
    id: int
    name: str
    base_version: int
    parent_id: int | None = None
    created_at: str = ""
    is_active: bool = True


class ResumeDetailResponse(ResumeSummaryResponse):
    structured_json: dict[str, Any] = Field(default_factory=dict)


class MatchSummaryResponse(BaseModel):
    id: int
    total_score: float
    skill_score: float
    experience_score: float
    education_score: float
    soft_skill_score: float
    culture_score: float
    matched_skills: list[Any] = Field(default_factory=list)
    missing_skills: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    created_at: str = ""


class JobSummaryResponse(BaseModel):
    id: int
    company: str
    position: str
    source_type: str
    source_url: str = ""
    created_at: str = ""
    match_count: int = 0
    application_count: int = 0
    latest_match: MatchSummaryResponse | None = None


class JobDetailResponse(JobSummaryResponse):
    raw_text: str = ""
    structured_json: dict[str, Any] = Field(default_factory=dict)


class ApplicationJobResponse(BaseModel):
    id: int
    company: str
    position: str
    structured_json: dict[str, Any] | None = None


class ApplicationResumeResponse(BaseModel):
    id: int
    name: str
    base_version: int
    structured_json: dict[str, Any] | None = None


class ApplicationSummaryResponse(BaseModel):
    id: int
    status: str
    applied_date: str = ""
    next_step: str = ""
    next_step_due: str = ""
    interview_at: str = ""
    updated_at: str = ""
    job: ApplicationJobResponse
    resume: ApplicationResumeResponse
    match: MatchSummaryResponse | None = None


class ApplicationDetailResponse(ApplicationSummaryResponse):
    notes: str = ""


class PracticeRecommendationResponse(BaseModel):
    question_id: int
    question: str
    category: str
    attempt_count: int
    latest_score: float
    weakest_dimension: str
    next_practice: str


class InterviewInsightsResponse(BaseModel):
    attempt_count: int = 0
    practiced_question_count: int = 0
    comparison_count: int = 0
    main_attempt_count: int = 0
    follow_up_attempt_count: int = 0
    overall_average: float = 0.0
    dimension_averages: dict[str, float] = Field(default_factory=dict)
    dimension_changes: dict[str, float] = Field(default_factory=dict)
    category_averages: dict[str, float] = Field(default_factory=dict)
    weak_dimensions: list[str] = Field(default_factory=list)
    weak_categories: list[str] = Field(default_factory=list)
    recommendations: list[PracticeRecommendationResponse] = Field(default_factory=list)


class InterviewQuestionResponse(BaseModel):
    id: int
    category: str
    question: str
    difficulty: str
    attempt_count: int = 0
    latest_attempt_id: int | None = None
    latest_score: float | None = None


class InterviewAttemptDetailResponse(BaseModel):
    id: int
    question_id: int
    application_id: int
    question: str
    category: str
    answer_text: str
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0
    feedback: dict[str, Any] = Field(default_factory=dict)
    answer_mode: Literal["text", "voice"] = "text"
    audio_retained: bool = False
    created_at: str = ""


class OperationResponse(BaseModel):
    id: int
    operation_type: str
    status: str
    progress: int
    input_refs: dict[str, int] = Field(default_factory=dict)
    result_refs: dict[str, int] = Field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    model: str = ""
    input_units: int = 0
    output_units: int = 0
    estimated_cost: float = 0.0
    retry_count: int = 0
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    replayed: bool = False


class ResumeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)


class JobCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    source_url: str = Field(default="", max_length=2_000)


class MatchCreateRequest(BaseModel):
    resume_id: int = Field(gt=0)
    job_id: int = Field(gt=0)


class InterviewAttemptCreateRequest(BaseModel):
    application_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    answer_text: str = Field(min_length=1, max_length=12_000)
    transcription_operation_id: int | None = Field(default=None, gt=0)
    retain_audio: bool = False


class InterviewTranscriptionCreateRequest(BaseModel):
    application_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    retain_audio: bool = False


class InterviewTranscriptionDraftResponse(BaseModel):
    operation_id: int
    application_id: int
    question_id: int
    object_id: int
    transcript: str
    original_name: str
    content_type: str
    size_bytes: int
    audio_retained: bool = False
    expires_at: str


class ApplicationCreateRequest(BaseModel):
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    match_id: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=5_000)


class ApplicationUpdateRequest(BaseModel):
    status: str | None = None
    note: str | None = Field(default=None, max_length=5_000)
    next_step: str | None = Field(default=None, max_length=500)
    next_step_due: str | None = None
    interview_at: str | None = None


class ApplicationMutationResponse(BaseModel):
    operation: OperationResponse
    application: ApplicationDetailResponse


class StoredObjectResponse(BaseModel):
    id: int
    kind: Literal["resume_source", "job_source", "interview_audio"]
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    created_at: str = ""
    replayed: bool = False


class StoredObjectDeletionResponse(BaseModel):
    id: int
    status: Literal["deleted"] = "deleted"


class RetainedAudioItem(BaseModel):
    id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: str
    expires_at: str


class RetentionPolicyChangeResponse(BaseModel):
    previous_days: int
    new_days: int
    changed_at: str
    source: Literal["configuration"] = "configuration"


class RetentionPolicyAuditResponse(BaseModel):
    configured_days: int
    observed_days: int | None = None
    last_observed_at: str = ""
    changes: list[RetentionPolicyChangeResponse] = Field(default_factory=list)


class RetainedAudioListResponse(BaseModel):
    items: list[RetainedAudioItem]
    retention_days: int
    maintenance: MaintenanceHealthResponse
    retention_policy: RetentionPolicyAuditResponse


class RetainedAudioDeletionRequest(BaseModel):
    object_ids: list[int] = Field(min_length=1, max_length=100)


class RetainedAudioDeletionResponse(BaseModel):
    requested: int
    deleted: int
    already_absent: int


class DeletionChallengeResponse(BaseModel):
    deletion_token: str
    expires_at: str
    required_confirmation: Literal["DELETE MY DATA"] = "DELETE MY DATA"


class AccountDeletionRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    confirmation: str = Field(min_length=1, max_length=100)


class AccountDeletionResponse(BaseModel):
    status: Literal["deleted"] = "deleted"
    correlation_id: str
    deleted_records: int
    object_cleanup_pending: int
