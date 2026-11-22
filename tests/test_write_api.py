"""Idempotent write and durable AI job acceptance tests for Iteration 0.23."""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from src.db.models import InterviewQuestion, User
from src.db.sqlite_client import Database
from src.repositories.operations import SQLiteOperationRepository
from src.repositories.sqlite_ownership import SQLiteOwnershipRepository
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.context import RequestContext
from src.services.job_runner import OperationRunner
from src.services.uploads import UploadApplicationService
from src.services.write_models import WriteApplicationService
from src.storage.local import LocalObjectStore
from tests.test_api_authentication import _authenticated_app, _issue
from tests.test_api_skeleton import _request
from tests.test_read_api import _seed_chain


VALID_EVALUATION = {
    "scores": {
        "completeness": 4,
        "truthfulness": 4,
        "technical": 4,
        "structure": 4,
    },
    "feedback": {
        "summary": "Clear answer",
        "strengths": ["Specific"],
        "improvements": ["Add metrics"],
        "next_practice": "Add one trade-off",
        "evidence_citations": [],
        "unsupported_claims": [],
    },
}


class FakeAIClient:
    def extract_resume_from_text(self, text):
        return {
            "sections": [{
                "title": "Experience",
                "entries": [{"header": "Engineer", "bullets": [text[:40]]}],
            }],
        }

    def extract_jd_from_text(self, text):
        return {
            "company": "Worker Co",
            "position": "Backend Engineer",
            "required_skills": ["Python"],
        }

    def match_and_suggest(self, jd_json, resume_json, rag_context):
        return {
            "total_score": 80,
            "skill_score": 80,
            "experience_score": 80,
            "education_score": 80,
            "soft_skill_score": 80,
            "culture_score": 80,
            "matched_skills": ["Python"],
            "missing_skills": [],
            "risks": [],
            "suggestions": [],
            "summary": "Good match",
        }

    def _call(self, **kwargs):
        return VALID_EVALUATION


class FailingAIClient:
    def extract_resume_from_text(self, text):
        raise RuntimeError("private-provider-secret")


class FakeTranscriptions:
    def create(self, **kwargs):
        assert kwargs["model"]
        assert kwargs["file"][0] == "answer.webm"
        return SimpleNamespace(text="我使用幂等键、状态机和有限重试保证任务可追踪。")


class FakeAudioClient:
    def __init__(self):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())


class RecordingAlertSink:
    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(dict(event))


def _headers(token: str, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
    }


def _write_service(database: Database, user_id: int = 1) -> WriteApplicationService:
    return WriteApplicationService(
        RequestContext(
            request_id=f"req_write_{user_id}",
            user_id=user_id,
            username=f"user-{user_id}",
        ),
        database,
        SQLiteOwnershipRepository(database),
        SQLiteOperationRepository(database),
        StoredObjectDatabaseRepository(database),
    )


def test_resume_submission_is_idempotent_and_hides_private_payload(tmp_path):
    database = Database(tmp_path / "resume-job.db")
    token = _issue(database).token
    application = _authenticated_app(database)
    body = {"name": "Backend Resume", "text": "Private resume text with Python"}
    headers = _headers(token, "resume-request-0001")

    first = _request(application, "POST", "/api/v1/resumes", headers=headers, json=body)
    replay = _request(application, "POST", "/api/v1/resumes", headers=headers, json=body)
    conflict = _request(
        application,
        "POST",
        "/api/v1/resumes",
        headers=headers,
        json={"name": "Changed", "text": "Different content"},
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["result_refs"] == replay.json()["result_refs"]
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert database.count("resumes") == 1
    assert database.count("operation_jobs") == 1
    assert body["text"] not in json.dumps(first.json())
    stored_operation = database.list("operation_jobs", limit=1)[0]
    assert body["text"] not in json.dumps(stored_operation)
    payload = database.fetch_one(
        "SELECT payload_json FROM operation_payloads WHERE operation_id = ?",
        (first.json()["id"],),
    )
    assert body["text"] in payload["payload_json"]
    database.close()


def test_operation_status_is_user_scoped(tmp_path):
    database = Database(tmp_path / "operation-isolation.db")
    user_two = database.insert("users", User(username="bob"))
    alice_token = _issue(database, user_id=1, label="alice").token
    bob_token = _issue(database, user_id=user_two, label="bob").token
    application = _authenticated_app(database)
    queued = _request(
        application,
        "POST",
        "/api/v1/jobs",
        headers=_headers(alice_token, "job-request-0001"),
        json={"text": "Private JD", "source_url": ""},
    ).json()

    owner = _request(
        application,
        "GET",
        f"/api/v1/operations/{queued['id']}",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    foreign = _request(
        application,
        "GET",
        f"/api/v1/operations/{queued['id']}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )

    assert owner.status_code == 200
    assert foreign.status_code == 404
    database.close()


def test_application_create_and_update_are_transactional_and_idempotent(tmp_path):
    database = Database(tmp_path / "application-write.db")
    chain = _seed_chain(database, 1, "owner")
    token = _issue(database).token
    application = _authenticated_app(database)

    create_body = {
        "job_id": chain["job"],
        "resume_id": chain["resume"],
        "match_id": chain["match"],
        "notes": "Created through API",
    }
    created = _request(
        application,
        "POST",
        "/api/v1/applications",
        headers=_headers(token, "application-create-0001"),
        json=create_body,
    )
    replayed = _request(
        application,
        "POST",
        "/api/v1/applications",
        headers=_headers(token, "application-create-0001"),
        json=create_body,
    )
    application_id = created.json()["application"]["id"]

    updated = _request(
        application,
        "PATCH",
        f"/api/v1/applications/{application_id}",
        headers=_headers(token, "application-update-0001"),
        json={"status": "applied", "next_step": "Wait for response"},
    )
    update_replay = _request(
        application,
        "PATCH",
        f"/api/v1/applications/{application_id}",
        headers=_headers(token, "application-update-0001"),
        json={"status": "applied", "next_step": "Wait for response"},
    )
    invalid = _request(
        application,
        "PATCH",
        f"/api/v1/applications/{application_id}",
        headers=_headers(token, "application-update-0002"),
        json={"status": "offer"},
    )

    assert created.status_code == 201
    assert replayed.json()["operation"]["replayed"] is True
    assert replayed.json()["application"]["id"] == application_id
    assert updated.status_code == 200
    assert updated.json()["application"]["status"] == "applied"
    assert update_replay.json()["operation"]["replayed"] is True
    assert invalid.status_code == 422
    events = database.find_by("application_events", "application_id", application_id)
    assert [event["event_type"] for event in events] == ["created", "api_updated"]
    database.close()


def test_foreign_inputs_are_rejected_for_match_application_and_interview(tmp_path):
    database = Database(tmp_path / "write-ownership.db")
    user_two = database.insert("users", User(username="bob"))
    alice = _seed_chain(database, 1, "alice")
    bob = _seed_chain(database, user_two, "bob")
    bob_token = _issue(database, user_id=user_two).token
    application = _authenticated_app(database)

    match = _request(
        application,
        "POST",
        "/api/v1/matches",
        headers=_headers(bob_token, "foreign-match-0001"),
        json={"resume_id": alice["resume"], "job_id": alice["job"]},
    )
    app_create = _request(
        application,
        "POST",
        "/api/v1/applications",
        headers=_headers(bob_token, "foreign-app-00001"),
        json={"resume_id": alice["resume"], "job_id": alice["job"], "match_id": alice["match"]},
    )
    answer = _request(
        application,
        "POST",
        "/api/v1/interview-attempts",
        headers=_headers(bob_token, "foreign-answer-01"),
        json={
            "application_id": alice["application"],
            "question_id": alice["question"],
            "answer_text": "I designed retries",
        },
    )

    assert [match.status_code, app_create.status_code, answer.status_code] == [404, 404, 404]
    assert bob["application"] != alice["application"]
    database.close()


def test_active_job_limit_returns_retry_after_and_replays_still_work(tmp_path):
    database = Database(tmp_path / "rate-limit.db")
    token = _issue(database).token
    application = _authenticated_app(database)
    first_body = {"text": "JD number 0", "source_url": ""}

    first = None
    for index in range(5):
        response = _request(
            application,
            "POST",
            "/api/v1/jobs",
            headers=_headers(token, f"rate-limit-key-{index:02d}"),
            json={"text": f"JD number {index}", "source_url": ""},
        )
        assert response.status_code == 202
        first = first or response
    limited = _request(
        application,
        "POST",
        "/api/v1/jobs",
        headers=_headers(token, "rate-limit-key-99"),
        json={"text": "One too many", "source_url": ""},
    )
    replay = _request(
        application,
        "POST",
        "/api/v1/jobs",
        headers=_headers(token, "rate-limit-key-00"),
        json=first_body,
    )

    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["replayed"] is True
    database.close()


def test_worker_executes_all_supported_ai_jobs_and_deletes_success_payloads(tmp_path):
    database = Database(tmp_path / "worker-success.db")
    service = _write_service(database)
    runner = OperationRunner(database, client=FakeAIClient())

    resume_job = service.queue_resume_parse(
        name="Worker Resume",
        text="Built Python services",
        idempotency_key="worker-resume-0001",
    )
    jd_job = service.queue_job_parse(
        text="Backend role requiring Python",
        source_url="",
        idempotency_key="worker-job-000001",
    )
    assert runner.run_next(limit=2) == [resume_job["id"], jd_job["id"]]

    resume_id = resume_job["result_refs"]["resume_id"]
    job_id = jd_job["result_refs"]["job_id"]
    match_job = service.queue_match(
        resume_id=resume_id,
        job_id=job_id,
        idempotency_key="worker-match-0001",
    )
    with patch("src.core.retriever.retrieve_context", return_value={}):
        assert runner.run_one(match_job["id"])
    match_operation = service.get_operation(match_job["id"])
    match_id = match_operation["result_refs"]["match_id"]
    application_result = service.create_application(
        job_id=job_id,
        resume_id=resume_id,
        match_id=match_id,
        idempotency_key="worker-app-000001",
    )
    application_id = application_result["application"]["id"]
    question_id = database.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=match_id,
            category="technical",
            question="Explain retries",
        ),
    )
    answer_job = service.queue_interview_answer(
        application_id=application_id,
        question_id=question_id,
        answer_text="I used bounded retries and idempotency keys.",
        idempotency_key="worker-answer-001",
    )
    assert runner.run_one(answer_job["id"])

    for operation_id in (resume_job["id"], jd_job["id"], match_job["id"], answer_job["id"]):
        operation = service.get_operation(operation_id)
        assert operation["status"] == "succeeded"
        assert operation["progress"] == 100
        assert SQLiteOperationRepository(database).get_payload(operation_id, 1) is None
    assert database.count("match_results") == 1
    assert database.count("interview_attempts") == 1
    database.close()


def test_worker_failure_is_sanitized_and_keeps_payload_for_retry(tmp_path):
    database = Database(tmp_path / "worker-failure.db")
    service = _write_service(database)
    operation = service.queue_resume_parse(
        name="Failure Resume",
        text="Sensitive resume content",
        idempotency_key="worker-failure-01",
    )

    alerts = RecordingAlertSink()
    assert OperationRunner(
        database,
        client=FailingAIClient(),
        alert_sink=alerts,
    ).run_one(operation["id"])
    retry_one = service.get_operation(operation["id"])
    assert retry_one["status"] == "queued"
    assert retry_one["error_code"] == "operation_retry_scheduled"
    assert retry_one["retry_count"] == 1
    assert SQLiteOperationRepository(database).get_payload(operation["id"], 1) is not None

    runner = OperationRunner(
        database,
        client=FailingAIClient(),
        alert_sink=alerts,
    )
    assert runner.run_one(operation["id"])
    assert service.get_operation(operation["id"])["status"] == "queued"
    assert runner.run_one(operation["id"])
    failed = service.get_operation(operation["id"])

    assert failed["status"] == "failed"
    assert failed["error_code"] == "operation_execution_failed"
    assert failed["retry_count"] == 3
    assert "private-provider-secret" not in json.dumps(failed)
    assert SQLiteOperationRepository(database).get_payload(operation["id"], 1) is not None
    assert len(alerts.events) == 1
    assert alerts.events[0]["operation_id"] == operation["id"]
    assert "user_id" not in alerts.events[0]
    database.close()


def test_voice_transcription_requires_confirmation_and_deletes_audio_by_default(tmp_path):
    database = Database(tmp_path / "voice-worker.db")
    chain = _seed_chain(database, 1, "voice")
    store = LocalObjectStore(tmp_path / "objects")
    upload_service = UploadApplicationService(
        RequestContext(request_id="req_voice_upload", user_id=1, username="owner"),
        store,
        StoredObjectDatabaseRepository(database),
    )
    uploaded = upload_service.upload(
        kind="interview_audio",
        filename="answer.webm",
        content_type="audio/webm",
        stream=io.BytesIO(b"private mock interview audio"),
        idempotency_key="voice-upload-0001",
    )
    service = _write_service(database)
    transcription = service.queue_interview_transcription(
        application_id=chain["application"],
        question_id=chain["question"],
        object_id=uploaded["id"],
        idempotency_key="voice-transcribe-01",
    )
    runner = OperationRunner(
        database,
        client=FakeAIClient(),
        transcription_client=FakeAudioClient(),
        object_store=store,
    )
    assert runner.run_one(transcription["id"])
    draft = service.get_interview_transcription(transcription["id"])
    assert draft["transcript"].startswith("我使用幂等键")
    assert draft["object_id"] == uploaded["id"]
    assert "T" in draft["expires_at"]
    owner_token = _issue(database, user_id=1, label="voice-owner").token
    other_user = database.insert("users", User(username="voice-other"))
    other_token = _issue(database, user_id=other_user, label="voice-other").token
    application = _authenticated_app(database)
    owner_draft = _request(
        application,
        "GET",
        f"/api/v1/interview-transcriptions/{transcription['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    foreign_draft = _request(
        application,
        "GET",
        f"/api/v1/interview-transcriptions/{transcription['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert owner_draft.status_code == 200
    assert owner_draft.json()["transcript"] == draft["transcript"]
    assert foreign_draft.status_code == 404

    evaluation = service.queue_interview_answer(
        application_id=chain["application"],
        question_id=chain["question"],
        answer_text=draft["transcript"],
        transcription_operation_id=transcription["id"],
        retain_audio=False,
        idempotency_key="voice-evaluate-0001",
    )
    assert runner.run_one(evaluation["id"])
    attempt_id = service.get_operation(evaluation["id"])["result_refs"]["attempt_id"]
    attempt = service._reads.get_interview_attempt(attempt_id)
    assert attempt["answer_mode"] == "voice"
    assert attempt["audio_retained"] is False
    assert not store.exists(uploaded["object_key"])
    assert StoredObjectDatabaseRepository(database).get(1, uploaded["id"]) is None
    assert SQLiteOperationRepository(database).get_payload(transcription["id"], 1) is None
    database.close()


def test_database_transaction_rolls_back_related_writes(tmp_path):
    database = Database(tmp_path / "rollback.db")
    before = database.count("users")
    try:
        with database.transaction():
            database.insert("users", User(username="rolled-back"))
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    assert database.count("users") == before
    database.close()


def test_write_openapi_requires_idempotency_and_exposes_expected_methods(tmp_path):
    database = Database(tmp_path / "write-contract.db")
    token = _issue(database).token
    application = _authenticated_app(database)

    missing_key = _request(
        application,
        "POST",
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "Backend role", "source_url": ""},
    )
    document = _request(application, "GET", "/openapi.json").json()

    assert missing_key.status_code == 422
    assert set(document["paths"]["/api/v1/resumes"]) == {"get", "post"}
    assert set(document["paths"]["/api/v1/jobs"]) == {"get", "post"}
    assert set(document["paths"]["/api/v1/applications"]) == {"get", "post"}
    assert set(document["paths"]["/api/v1/applications/{application_id}"]) == {"get", "patch"}
    assert set(document["paths"]["/api/v1/matches"]) == {"post"}
    assert set(document["paths"]["/api/v1/interview-attempts"]) == {"post"}
    assert set(document["paths"]["/api/v1/interview-transcriptions"]) == {"post"}
    assert set(document["paths"]["/api/v1/interview-transcriptions/{operation_id}"]) == {"get"}
    assert set(document["paths"]["/api/v1/uploads/{object_id}"]) == {"get", "delete"}
    assert set(document["paths"]["/api/v1/operations/{operation_id}"]) == {"get"}
    post_parameters = document["paths"]["/api/v1/jobs"]["post"]["parameters"]
    idempotency = next(item for item in post_parameters if item["name"] == "Idempotency-Key")
    assert idempotency["required"] is True
    database.close()
