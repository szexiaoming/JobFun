"""Static architecture and security guards for the Iteration 0.37 web client."""

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
WEB = ROOT / "web"


def _read(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_next_client_is_versioned_and_has_required_quality_commands():
    package = json.loads(_read("package.json"))
    package_lock = json.loads(_read("package-lock.json"))
    assert package["version"] == "0.41.0"
    assert package_lock["version"] == package["version"]
    assert package_lock["packages"][""]["version"] == package["version"]
    assert package["dependencies"]["next"] == "16.4.6"
    assert package["scripts"]["check"] == (
        "npm run lint && npm run typecheck && npm run build"
    )


def test_session_token_is_http_only_and_never_uses_browser_script_storage():
    auth = _read("src/lib/auth.ts")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (WEB / "src").rglob("*.ts*")
    )
    assert "httpOnly: true" in auth
    assert 'sameSite: "strict"' in auth
    assert "localStorage." not in source
    assert "sessionStorage." not in source


def test_backend_proxy_uses_cookie_auth_path_allowlist_and_same_origin_writes():
    proxy = _read("src/app/api/backend/[...path]/route.ts")
    server_api = _read("src/lib/server-api.ts")
    assert "ALLOWED_PATHS" in proxy
    assert "isSameOrigin(request)" in proxy
    assert "SESSION_COOKIE" in proxy
    assert 'headers.set("Authorization", `Bearer ${token}`)' in server_api
    assert 'incoming.get("authorization")' not in server_api.lower()


def test_pwa_does_not_cache_api_responses_and_has_mobile_breakpoints():
    worker = _read("public/sw.js")
    register = _read("src/components/pwa-register.tsx")
    css = _read("src/app/globals.css")
    manifest = _read("src/app/manifest.ts")
    assert 'url.pathname.startsWith("/api/")' in worker
    assert "/_next/static/" in worker
    assert 'const CACHE = "jobfun-shell-v0.34"' in worker
    assert "if (LOCAL_PREVIEW)" in worker
    assert 'process.env.NODE_ENV !== "production"' in register
    assert 'getRegistration("/")' in register and "unregister()" in register
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 520px)" in css
    assert ".bottomNav" in css
    assert 'display: "standalone"' in manifest
    assert "icon-192.png" in manifest and "icon-512.png" in manifest


def test_read_only_dashboard_pages_use_the_versioned_backend_contract():
    client = _read("src/lib/jobfun-api.ts")
    assert 'backendRequest<Workbench>("/workbench")' in client
    assert 'pagedRequest<ResumeSummary>("/resumes", page)' in client
    assert 'pagedRequest<JobSummary>("/jobs", page)' in client
    assert 'pagedRequest<ApplicationSummary>("/applications", page)' in client
    assert "cache: \"no-store\"" in _read("src/lib/server-api.ts")


def test_migrated_navigation_and_pages_remain_read_only():
    navigation = _read("src/components/app-navigation.tsx")
    assert 'href: "/dashboard/resumes"' in navigation
    assert 'href: "/dashboard/jobs"' in navigation
    assert 'href: "/dashboard/applications"' in navigation
    pages = "\n".join(
        _read(path)
        for path in (
            "src/app/dashboard/page.tsx",
            "src/app/dashboard/resumes/page.tsx",
            "src/app/dashboard/jobs/page.tsx",
            "src/app/dashboard/applications/page.tsx",
        )
    )
    assert "<form" not in pages
    assert "method=\"POST\"" not in pages
    assert "method=\"PATCH\"" not in pages


def test_detail_pages_use_owned_read_models_and_expose_no_mutations():
    client = _read("src/lib/jobfun-api.ts")
    assert 'backendRequest<ResumeDetail>(`/resumes/${id}`)' in client
    assert 'backendRequest<JobDetail>(`/jobs/${id}`)' in client
    assert 'backendRequest<ApplicationDetail>(`/applications/${id}`)' in client
    details = "\n".join(
        _read(path)
        for path in (
            "src/app/dashboard/resumes/[id]/page.tsx",
            "src/app/dashboard/jobs/[id]/page.tsx",
            "src/app/dashboard/applications/[id]/page.tsx",
        )
    )
    assert "detailOrNotFound" in details
    assert "<form" not in details
    assert "POST" not in details and "PATCH" not in details and "DELETE" not in details


def test_import_pages_only_submit_in_scope_sources_and_track_operations():
    workspace = _read("src/components/import-workspace.tsx")
    resume_page = _read("src/app/dashboard/resumes/new/page.tsx")
    job_page = _read("src/app/dashboard/jobs/new/page.tsx")
    assert '<ImportWorkspace kind="resume" />' in resume_page
    assert '<ImportWorkspace kind="job" />' in job_page
    assert 'endpoint: "/api/backend/resumes"' in workspace
    assert 'endpoint: "/api/backend/jobs"' in workspace
    assert 'uploadEndpoint: "/api/backend/uploads/resume_source"' in workspace
    assert 'uploadEndpoint: "/api/backend/uploads/job_source"' in workspace
    assert '"Idempotency-Key"' in workspace
    assert "/api/backend/operations/${operation.id}" in workspace
    assert "operation.retry_count" in workspace
    assert "object_key" not in workspace
    assert "/api/backend/matches" not in workspace
    assert "/api/backend/applications" not in workspace
    assert "/api/backend/interview-attempts" not in workspace


def test_match_execution_is_explicit_scoped_and_links_to_evidence_report():
    workspace = _read("src/components/match-workspace.tsx")
    page = _read("src/app/dashboard/matches/new/page.tsx")
    client = _read("src/lib/jobfun-api.ts")
    assert "listMatchOptions()" in page
    assert 'backendRequest<ResumeSummary[]>("/resumes?limit=100&offset=0")' in client
    assert 'backendRequest<JobSummary[]>("/jobs?limit=100&offset=0")' in client
    assert 'fetch("/api/backend/matches"' in workspace
    assert '"Idempotency-Key"' in workspace
    assert "resume_id: selectedResume" in workspace
    assert "job_id: selectedJob" in workspace
    assert "/api/backend/operations/${operation.id}" in workspace
    assert "operation?.result_refs.match_id" in workspace
    assert '#match-report-title' in workspace
    assert "/api/backend/applications" not in workspace
    assert "/api/backend/interview-attempts" not in workspace


def test_application_writes_require_matched_evidence_and_follow_status_flow():
    create_page = _read("src/app/dashboard/applications/new/page.tsx")
    create_form = _read("src/components/application-create-form.tsx")
    update_form = _read("src/components/application-update-form.tsx")
    match_workspace = _read("src/components/match-workspace.tsx")
    assert "job.latest_match.id !== matchId" in create_page
    assert "detailOrNotFound(getJob(jobId))" in create_page
    assert "detailOrNotFound(getResume(resumeId))" in create_page
    assert 'fetch("/api/backend/applications"' in create_form
    assert '"Idempotency-Key"' in create_form
    assert "job_id: evidence.jobId" in create_form
    assert "resume_id: evidence.resumeId" in create_form
    assert "match_id: evidence.matchId" in create_form
    assert "confirmed" in create_form
    assert 'method: "PATCH"' in update_form
    assert "STATUS_TRANSITIONS" in update_form
    assert "Object.keys(changes).length" in update_form
    assert "changes.note = note.trim()" in update_form
    assert "/dashboard/applications/new?job_id=" in match_workspace
    combined = create_form + update_form
    assert "/api/backend/interview-attempts" not in combined
    assert "/api/backend/matches" not in combined


def test_interview_practice_is_scoped_text_only_and_reads_evaluation_result():
    page = _read("src/app/dashboard/applications/[id]/interview/page.tsx")
    workspace = _read("src/components/interview-practice-workspace.tsx")
    client = _read("src/lib/jobfun-api.ts")
    proxy = _read("src/app/api/backend/[...path]/route.ts")
    assert "listInterviewQuestions(id)" in page
    assert "getInterviewInsights(id)" in page
    assert "applicationId={id}" in page
    assert "interview-questions" in client
    assert 'fetch("/api/backend/interview-attempts"' in workspace
    assert '"Idempotency-Key"' in workspace
    assert "application_id: applicationId" in workspace
    assert "question_id: selectedQuestion" in workspace
    assert "answer_text: cleanAnswer" in workspace
    assert "/api/backend/operations/${operation.id}" in workspace
    assert "next.result_refs.attempt_id" in workspace
    assert "/api/backend/interview-attempts/${attemptId}" in workspace
    assert "interview-(?:insights|questions)" in proxy
    assert "/api/backend/uploads" not in workspace
    assert "/api/backend/matches" not in workspace
    assert 'method: "PATCH"' not in workspace


def test_voice_practice_requires_consent_confirmation_and_private_audio_lifecycle():
    voice = _read("src/components/interview-voice-practice.tsx")
    types = _read("src/lib/client-api-types.ts")
    proxy = _read("src/app/api/backend/[...path]/route.ts")
    assert "我同意为本次练习处理音频" in voice
    assert "navigator.mediaDevices.getUserMedia" in voice
    assert "if (!consented)" in voice
    assert "MAX_AUDIO_BYTES = 10 * 1024 * 1024" in voice
    assert 'fetch("/api/backend/uploads/interview_audio"' in voice
    assert 'fetch("/api/backend/interview-transcriptions"' in voice
    assert '"Idempotency-Key"' in voice
    assert "/api/backend/operations/${operation.id}" in voice
    assert "/api/backend/interview-transcriptions/${next.id}" in voice
    assert "我已检查并修改转写内容" in voice
    assert "transcriptionOperationId: draft.operation_id" in voice
    assert "retain_audio: retainOriginal" in voice
    assert 'method: "DELETE"' in voice
    assert "24 小时" in voice
    assert "object_key" not in voice
    assert "object_key" not in types
    assert "interview-transcriptions" in proxy


def test_retained_audio_manager_is_owner_scoped_and_uses_batch_delete():
    page = _read("src/app/dashboard/audio/page.tsx")
    manager = _read("src/components/retained-audio-manager.tsx")
    client = _read("src/lib/jobfun-api.ts")
    navigation = _read("src/components/app-navigation.tsx")
    proxy = _read("src/app/api/backend/[...path]/route.ts")
    voice = _read("src/components/interview-voice-practice.tsx")
    assert "listRetainedAudio()" in page
    assert "retention_days" in page
    assert 'fetch("/api/backend/retained-audio"' in manager
    assert 'method: "DELETE"' in manager
    assert "object_ids: selected" in manager
    assert "object_key" not in manager
    assert 'backendRequest<RetainedAudioList>("/retained-audio")' in client
    assert 'href: "/dashboard/audio"' in navigation
    assert "retained-audio" in proxy
    assert "自动到期" in voice
    assert "maintenance.status" in page
    assert "consecutive_failures" in page
    assert "last_deleted" in page
    assert "maintenance.recent_runs" in page
    assert "success_rate_percent" in page
    assert "retention_policy.changes" in page
    assert "首次运行只建立基线" in page
