"""Application-bound gap explanation and evidence integrity contracts."""

import json
from unittest.mock import patch

from src.core.source_locator import assign_source_ids
from src.db.models import EvidenceMatch, JobRequirement, User
from src.db.sqlite_client import Database
from src.services.job_runner import OperationRunner
from tests.test_api_authentication import _authenticated_app, _issue
from tests.test_api_skeleton import _request
from tests.test_read_api import _seed_chain
from tests.test_write_api import FakeAIClient, _headers


def _evidence(database: Database, chain: dict, *, quote: str = "Built API owner") -> str:
    resume = database.get("resumes", chain["resume"])
    structured = resume["structured_json"]
    if isinstance(structured, str):
        structured = json.loads(structured)
    source_id = assign_source_ids(structured)["sections"][0]["entries"][0]["bullets"][0]["source_id"]
    requirement_id = database.insert(
        "job_requirements",
        JobRequirement(jd_id=chain["job"], category="required", text="Python", normalized_key="python", priority=1),
    )
    database.insert(
        "evidence_matches",
        EvidenceMatch(
            match_id=chain["match"], requirement_id=requirement_id, status="proven",
            evidence_json=[{
                "text": quote, "section": "Experience", "entry": "owner",
                "bullet_index": 0, "source_id": source_id,
            }],
            reasoning="Grounded quote",
        ),
    )
    return source_id


def test_gap_explanation_is_idempotent_and_bound_to_original_resume(tmp_path):
    database = Database(tmp_path / "gap.db")
    chain = _seed_chain(database, 1, "owner")
    source_id = _evidence(database, chain)
    token = _issue(database).token
    app = _authenticated_app(database)
    path = f"/api/v1/applications/{chain['application']}"
    headers = _headers(token, "gap-request-0001")

    requirements = _request(app, "GET", f"{path}/requirements", headers=headers)
    assert requirements.status_code == 200
    assert requirements.json()[0]["status"] == "proven"
    assert requirements.json()[0]["evidence"][0]["source_id"] == source_id

    first = _request(app, "POST", f"{path}/gap-explanations", headers=headers, json={"requirement_key": "python"})
    replay = _request(app, "POST", f"{path}/gap-explanations", headers=headers, json={"requirement_key": "python"})
    conflict = _request(app, "POST", f"{path}/gap-explanations", headers=headers, json={"requirement_key": "other"})
    assert first.status_code == replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    assert replay.json()["replayed"] is True
    assert conflict.status_code == 409

    with patch("src.ai.langchain_gap.propose_gap_action", return_value={
        "action_kind": "prepare_interview", "candidate_source_ids": [source_id],
    }):
        assert OperationRunner(database, client=FakeAIClient()).run_one(first.json()["id"])

    result = _request(app, "GET", f"/api/v1/gap-explanations/{first.json()['id']}", headers=headers)
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "proven"
    assert body["evidence"][0]["source_id"] == source_id
    assert body["candidate_evidence"][0]["source_id"] == source_id
    assert body["mode"] == "langchain"
    assert "原文" in body["explanation"]
    assert database.get("match_results", chain["match"])["total_score"] == 82
    database.close()


def test_gap_explanation_rejects_foreign_application_and_unlisted_requirement(tmp_path):
    database = Database(tmp_path / "gap-ownership.db")
    second = database.insert("users", User(username="second"))
    owner = _seed_chain(database, 1, "owner")
    other = _seed_chain(database, second, "other")
    owner_token = _issue(database, user_id=1, label="owner").token
    other_token = _issue(database, user_id=second, label="second").token
    app = _authenticated_app(database)
    path = f"/api/v1/applications/{owner['application']}"
    assert _request(app, "GET", f"{path}/requirements", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
    assert _request(app, "POST", f"{path}/gap-explanations", headers=_headers(other_token, "foreign-gap-0001"), json={"requirement_key": "python"}).status_code == 404
    assert _request(app, "POST", f"{path}/gap-explanations", headers=_headers(owner_token, "invalid-gap-0001"), json={"requirement_key": "kafka"}).status_code == 422
    own = _request(app, "POST", f"{path}/gap-explanations", headers=_headers(owner_token, "valid-gap-00001"), json={"requirement_key": "python"})
    assert own.status_code == 202
    assert _request(app, "GET", f"/api/v1/gap-explanations/{own.json()['id']}", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
    assert other["application"] != owner["application"]
    database.close()


def test_tampered_evidence_is_not_exposed_as_proven(tmp_path):
    database = Database(tmp_path / "gap-stale.db")
    chain = _seed_chain(database, 1, "owner")
    _evidence(database, chain, quote="Invented Kubernetes deployment")
    token = _issue(database).token
    app = _authenticated_app(database)
    response = _request(
        app, "GET", f"/api/v1/applications/{chain['application']}/requirements",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()[0]["status"] == "uncertain"
    assert response.json()[0]["evidence"] == []
    database.close()


def test_gap_agent_calls_read_only_langchain_tools(monkeypatch):
    import pytest

    pytest.importorskip("langchain")
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from src.ai import langchain_gap

    class ToolCallingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[
            {"name": "read_requirement", "args": {}, "id": "read-1"},
            {"name": "read_verified_evidence", "args": {}, "id": "read-2"},
        ]),
        AIMessage(content=json.dumps({
            "action_kind": "prepare_interview", "candidate_source_ids": [],
        })),
    ])
    monkeypatch.setattr(langchain_gap, "_configured_model", lambda: model)
    result = langchain_gap.propose_gap_action(
        {"key": "python", "text": "Python", "status": "proven"},
        [{"source_id": "source-1", "text": "Built API"}],
        [], user_id=1, resume_id=1,
    )
    assert result == {"action_kind": "prepare_interview", "candidate_source_ids": []}
    assert model.i == 0


def test_gap_baseline_runs_without_configured_model(tmp_path, monkeypatch):
    database = Database(tmp_path / "gap-baseline.db")
    chain = _seed_chain(database, 1, "owner")
    _evidence(database, chain)
    token = _issue(database).token
    app = _authenticated_app(database)
    operation = _request(
        app, "POST", f"/api/v1/applications/{chain['application']}/gap-explanations",
        headers=_headers(token, "gap-baseline-0001"), json={"requirement_key": "python"},
    )
    assert operation.status_code == 202
    monkeypatch.setattr("src.services.job_runner.get_ai_client", lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr("src.ai.langchain_gap._configured_model", lambda: None)
    assert OperationRunner(database).run_one(operation.json()["id"])
    result = _request(
        app, "GET", f"/api/v1/gap-explanations/{operation.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 200
    assert result.json()["mode"] == "baseline"
    database.close()


def test_historical_match_without_evidence_returns_unassessed_baseline(tmp_path, monkeypatch):
    database = Database(tmp_path / "gap-historical.db")
    chain = _seed_chain(database, 1, "owner")
    token = _issue(database).token
    app = _authenticated_app(database)
    operation = _request(
        app, "POST", f"/api/v1/applications/{chain['application']}/gap-explanations",
        headers=_headers(token, "gap-historical-01"), json={"requirement_key": "python"},
    )
    assert operation.status_code == 202
    monkeypatch.setattr("src.services.job_runner.get_ai_client", lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr("src.core.evidence_matcher.get_ai_client", lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr("src.ai.langchain_gap._configured_model", lambda: None)
    assert OperationRunner(database).run_one(operation.json()["id"])
    result = _request(
        app, "GET", f"/api/v1/gap-explanations/{operation.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "unassessed"
    assert result.json()["evidence"] == []
    assert result.json()["mode"] == "baseline"
    database.close()


def test_langchain_vector_retrieval_is_scoped_to_pinned_resume(monkeypatch):
    import pytest

    pytest.importorskip("langchain_chroma")
    import langchain_huggingface
    from langchain_core.embeddings import Embeddings
    from src.ai import langchain_gap

    class LocalEmbeddings(Embeddings):
        def embed_documents(self, texts):
            return [self.embed_query(text) for text in texts]

        def embed_query(self, text):
            return [1.0, 0.0] if "python" in text.casefold() else [0.0, 1.0]

    monkeypatch.setattr(langchain_huggingface, "HuggingFaceEmbeddings", lambda **kwargs: LocalEmbeddings())
    monkeypatch.setattr(langchain_gap, "lexical_candidates", lambda *args: (_ for _ in ()).throw(AssertionError("vector failed")))
    candidates = [
        {"source_id": "api", "text": "Built Python API"},
        {"source_id": "other", "text": "Wrote product copy"},
    ]
    result = langchain_gap._retrieve_candidates("Python", candidates, 1, 7)
    assert result[0]["source_id"] == "api"
