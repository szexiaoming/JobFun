"""
SQLite database client for JobFun.
Handles schema creation, CRUD operations, and dataclass mapping.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import SQLITE_PATH
from src.db.models import (
    ApiToken,
    Application,
    ApplicationEvent,
    EvidenceMatch,
    EvidenceReview,
    EvidenceSupplement,
    EvidenceSupplementEvent,
    InterviewAttempt,
    InterviewFollowUp,
    InterviewQuestion,
    JobRequirement,
    JobDescription,
    LatexChange,
    MatchResult,
    MaintenanceRun,
    ObjectCleanupJob,
    OperationJob,
    PrivacyAuditEvent,
    PrivacyDeletionChallenge,
    Resume,
    Suggestion,
    StoredObject,
    User,
)
from src.utils.logger import logger

# ── Schema ────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL DEFAULT 'default',
    created_at    TEXT DEFAULT (datetime('now','localtime')),
    settings_json TEXT DEFAULT '{}',
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    token_hash    TEXT NOT NULL UNIQUE,
    label         TEXT DEFAULT '',
    expires_at    TEXT NOT NULL,
    revoked_at    TEXT DEFAULT '',
    last_used_at  TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id
    ON api_tokens(user_id);

CREATE TABLE IF NOT EXISTS operation_jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    operation_type    TEXT NOT NULL,
    idempotency_key   TEXT NOT NULL,
    request_hash      TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'queued',
    progress          INTEGER NOT NULL DEFAULT 0,
    input_refs_json   TEXT NOT NULL DEFAULT '{}',
    result_refs_json  TEXT NOT NULL DEFAULT '{}',
    error_code        TEXT DEFAULT '',
    error_message     TEXT DEFAULT '',
    model             TEXT DEFAULT '',
    input_units       INTEGER NOT NULL DEFAULT 0,
    output_units      INTEGER NOT NULL DEFAULT 0,
    estimated_cost    REAL NOT NULL DEFAULT 0,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    max_retries       INTEGER NOT NULL DEFAULT 2,
    created_at        TEXT NOT NULL,
    started_at        TEXT DEFAULT '',
    completed_at      TEXT DEFAULT '',
    updated_at        TEXT NOT NULL,
    UNIQUE(user_id, operation_type, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_operation_jobs_user_status
    ON operation_jobs(user_id, status, created_at);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_name         TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL DEFAULT 'idle',
    last_seen_at        TEXT NOT NULL,
    last_started_at     TEXT DEFAULT '',
    last_completed_at   TEXT DEFAULT '',
    last_operation_id   INTEGER NOT NULL DEFAULT 0,
    last_error_code     TEXT DEFAULT '',
    processed_total     INTEGER NOT NULL DEFAULT 0,
    failed_total        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS maintenance_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name             TEXT NOT NULL UNIQUE,
    status                TEXT NOT NULL DEFAULT 'idle',
    last_started_at       TEXT DEFAULT '',
    last_completed_at     TEXT DEFAULT '',
    last_checked          INTEGER NOT NULL DEFAULT 0,
    last_deleted          INTEGER NOT NULL DEFAULT 0,
    last_failed           INTEGER NOT NULL DEFAULT 0,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    run_total             INTEGER NOT NULL DEFAULT 0,
    deleted_total         INTEGER NOT NULL DEFAULT 0,
    failed_total          INTEGER NOT NULL DEFAULT 0,
    last_error_code       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS maintenance_run_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name      TEXT NOT NULL,
    status         TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    completed_at   TEXT NOT NULL,
    checked_count  INTEGER NOT NULL DEFAULT 0,
    deleted_count  INTEGER NOT NULL DEFAULT 0,
    failed_count   INTEGER NOT NULL DEFAULT 0,
    error_code     TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_maintenance_run_events_task_completed
    ON maintenance_run_events(task_name, completed_at);

CREATE TABLE IF NOT EXISTS retention_policies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_name     TEXT NOT NULL UNIQUE,
    retention_days  INTEGER NOT NULL,
    observed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retention_policy_audit_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_name    TEXT NOT NULL,
    previous_days  INTEGER NOT NULL,
    new_days       INTEGER NOT NULL,
    changed_at     TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'configuration'
);

CREATE INDEX IF NOT EXISTS idx_retention_policy_audit_policy_changed
    ON retention_policy_audit_events(policy_name, changed_at);

CREATE TABLE IF NOT EXISTS operation_payloads (
    operation_id  INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    payload_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stored_objects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    object_key        TEXT NOT NULL UNIQUE,
    kind              TEXT NOT NULL,
    original_name     TEXT NOT NULL,
    content_type      TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    sha256            TEXT NOT NULL,
    idempotency_key   TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'available',
    created_at        TEXT NOT NULL,
    deleted_at        TEXT DEFAULT '',
    UNIQUE(user_id, kind, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_stored_objects_user_kind
    ON stored_objects(user_id, kind, created_at);

CREATE TABLE IF NOT EXISTS privacy_deletion_challenges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_privacy_deletion_challenges_user
    ON privacy_deletion_challenges(user_id, expires_at);

CREATE TABLE IF NOT EXISTS privacy_audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id  TEXT NOT NULL UNIQUE,
    subject_hash    TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    status          TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    details_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_privacy_audit_events_created
    ON privacy_audit_events(event_type, created_at);

CREATE TABLE IF NOT EXISTS object_cleanup_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    object_key  TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER NOT NULL DEFAULT 0,
    error_code  TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_object_cleanup_jobs_status
    ON object_cleanup_jobs(status, id);

CREATE TABLE IF NOT EXISTS resumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL DEFAULT 1,
    name            TEXT NOT NULL,
    base_version    INTEGER DEFAULT 0,
    parent_id       INTEGER,
    latex_path      TEXT NOT NULL,
    pdf_path        TEXT DEFAULT '',
    structured_json TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    is_active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS job_descriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL DEFAULT 1,
    company         TEXT DEFAULT '',
    position        TEXT DEFAULT '',
    raw_text        TEXT DEFAULT '',
    source_type     TEXT DEFAULT 'text',
    source_file     TEXT DEFAULT '',
    structured_json TEXT DEFAULT '{}',
    source_url      TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS match_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id           INTEGER NOT NULL,
    jd_id               INTEGER NOT NULL,
    total_score         REAL DEFAULT 0,
    skill_score         REAL DEFAULT 0,
    experience_score    REAL DEFAULT 0,
    education_score     REAL DEFAULT 0,
    soft_skill_score    REAL DEFAULT 0,
    culture_score       REAL DEFAULT 0,
    matched_skills TEXT DEFAULT '[]',
    missing_skills TEXT DEFAULT '[]',
    risks          TEXT DEFAULT '[]',
    raw_report          TEXT DEFAULT '',
    created_at          TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS job_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    jd_id           INTEGER NOT NULL,
    category        TEXT NOT NULL DEFAULT 'required',
    text            TEXT NOT NULL,
    normalized_key  TEXT NOT NULL,
    priority        INTEGER DEFAULT 0,
    source_span     TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(jd_id, normalized_key)
);

CREATE INDEX IF NOT EXISTS idx_job_requirements_jd_id
    ON job_requirements(jd_id);

CREATE TABLE IF NOT EXISTS evidence_matches (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id                 INTEGER NOT NULL,
    requirement_id           INTEGER NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'uncertain',
    evidence_json            TEXT DEFAULT '[]',
    reasoning                TEXT NOT NULL DEFAULT '',
    confidence               REAL NOT NULL DEFAULT 0,
    needs_user_confirmation  INTEGER NOT NULL DEFAULT 0,
    recommended_action       TEXT DEFAULT '',
    user_status              TEXT DEFAULT '',
    user_note                TEXT DEFAULT '',
    created_at               TEXT DEFAULT (datetime('now','localtime')),
    updated_at               TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(match_id, requirement_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_matches_match_id
    ON evidence_matches(match_id);

CREATE INDEX IF NOT EXISTS idx_evidence_matches_requirement_id
    ON evidence_matches(requirement_id);

CREATE TABLE IF NOT EXISTS evidence_reviews (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_match_id        INTEGER NOT NULL,
    match_id                 INTEGER NOT NULL,
    requirement_id           INTEGER NOT NULL,
    action                   TEXT NOT NULL,
    previous_status          TEXT NOT NULL DEFAULT '',
    corrected_status         TEXT NOT NULL DEFAULT '',
    previous_evidence_json   TEXT DEFAULT '[]',
    corrected_evidence_json  TEXT DEFAULT '[]',
    note                     TEXT DEFAULT '',
    created_at               TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_reviews_evidence_match_id
    ON evidence_reviews(evidence_match_id);

CREATE INDEX IF NOT EXISTS idx_evidence_reviews_match_id
    ON evidence_reviews(match_id);

CREATE TABLE IF NOT EXISTS evidence_supplements (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id                  INTEGER NOT NULL,
    requirement_id            INTEGER NOT NULL,
    evidence_match_id         INTEGER,
    title                     TEXT NOT NULL,
    description               TEXT NOT NULL,
    context_type              TEXT NOT NULL DEFAULT 'other',
    organization              TEXT DEFAULT '',
    start_date                TEXT DEFAULT '',
    end_date                  TEXT DEFAULT '',
    source_type               TEXT NOT NULL DEFAULT 'user_supplied',
    status                    TEXT NOT NULL DEFAULT 'draft',
    user_attested             INTEGER NOT NULL DEFAULT 0,
    eligible_for_matching     INTEGER NOT NULL DEFAULT 0,
    eligible_for_resume_edit  INTEGER NOT NULL DEFAULT 0,
    created_at                TEXT DEFAULT (datetime('now','localtime')),
    updated_at                TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_supplements_match_id
    ON evidence_supplements(match_id);

CREATE INDEX IF NOT EXISTS idx_evidence_supplements_requirement_id
    ON evidence_supplements(requirement_id);

CREATE TABLE IF NOT EXISTS evidence_supplement_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    supplement_id  INTEGER NOT NULL,
    event_type     TEXT NOT NULL,
    snapshot_json  TEXT NOT NULL DEFAULT '{}',
    note           TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_supplement_events_supplement_id
    ON evidence_supplement_events(supplement_id);

CREATE TABLE IF NOT EXISTS suggestions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL,
    category        TEXT DEFAULT '',
    priority        INTEGER DEFAULT 0,
    original_text   TEXT DEFAULT '',
    suggested_text  TEXT DEFAULT '',
    rationale       TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    created_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER DEFAULT 1,
    jd_id         INTEGER NOT NULL,
    resume_id     INTEGER NOT NULL,
    match_id      INTEGER,
    status        TEXT DEFAULT 'saved',
    applied_date  TEXT DEFAULT '',
    notes         TEXT DEFAULT '',
    next_step     TEXT DEFAULT '',
    next_step_due TEXT DEFAULT '',
    interview_at  TEXT DEFAULT '',
    updated_at    TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS application_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    from_status     TEXT DEFAULT '',
    to_status       TEXT DEFAULT '',
    title           TEXT NOT NULL,
    details         TEXT DEFAULT '',
    occurred_at     TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_application_events_application_id
    ON application_events(application_id);

CREATE INDEX IF NOT EXISTS idx_application_events_occurred_at
    ON application_events(application_id, occurred_at);

CREATE TABLE IF NOT EXISTS interview_questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id         INTEGER NOT NULL,
    category         TEXT DEFAULT '',
    question         TEXT DEFAULT '',
    suggested_answer TEXT DEFAULT '',
    difficulty       TEXT DEFAULT 'medium',
    created_at       TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS interview_attempts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id        INTEGER NOT NULL,
    application_id     INTEGER DEFAULT 0,
    answer_text        TEXT NOT NULL,
    audio_path         TEXT DEFAULT '',
    transcript         TEXT DEFAULT '',
    completeness_score REAL DEFAULT 0,
    truthfulness_score REAL DEFAULT 0,
    technical_score    REAL DEFAULT 0,
    structure_score    REAL DEFAULT 0,
    feedback_json      TEXT DEFAULT '{}',
    created_at         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_interview_attempts_question_id
    ON interview_attempts(question_id);

CREATE INDEX IF NOT EXISTS idx_interview_attempts_application_id
    ON interview_attempts(application_id);

CREATE TABLE IF NOT EXISTS interview_follow_ups (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_attempt_id  INTEGER NOT NULL,
    question_id        INTEGER NOT NULL,
    target_dimension   TEXT NOT NULL,
    rationale          TEXT NOT NULL,
    created_at         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_interview_follow_ups_parent_attempt_id
    ON interview_follow_ups(parent_attempt_id);

CREATE INDEX IF NOT EXISTS idx_interview_follow_ups_question_id
    ON interview_follow_ups(question_id);

CREATE TABLE IF NOT EXISTS latex_changes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id     INTEGER NOT NULL,
    suggestion_id INTEGER NOT NULL,
    file_path     TEXT DEFAULT '',
    old_content   TEXT DEFAULT '',
    new_content   TEXT DEFAULT '',
    commit_hash   TEXT DEFAULT '',
    created_at    TEXT DEFAULT (datetime('now','localtime'))
);
"""


# ── Client ────────────────────────────────────────────

class Database:
    def __init__(self, db_path: Path = SQLITE_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._transaction_depth = 0
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._ensure_column("applications", "next_step_due", "TEXT DEFAULT ''")
        self._ensure_column("applications", "interview_at", "TEXT DEFAULT ''")
        self._ensure_column("users", "is_active", "INTEGER NOT NULL DEFAULT 1")
        self._conn.commit()
        # Ensure default user exists
        cur = self._conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            self._conn.execute(
                "INSERT INTO users (username) VALUES ('default')"
            )
            self._conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """Add a backwards-compatible column to an existing SQLite table."""
        columns = {
            row[1]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    # ── Generic CRUD ────────────────────────────────

    def insert(self, table: str, obj: Any) -> int:
        """Insert a dataclass object and return its new ID."""
        data = _to_db(obj)
        data.pop("id", None)
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cur = self._conn.execute(sql, list(data.values()))
        self._commit_if_needed()
        return cur.lastrowid

    def get(self, table: str, obj_id: int) -> Optional[dict]:
        """Get a row by id, returned as dict."""
        cur = self._conn.execute(
            f"SELECT * FROM {table} WHERE id = ?", (obj_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list(self, table: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """List rows from a table."""
        cur = self._conn.execute(
            f"SELECT * FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def update(self, table: str, obj_id: int, updates: dict) -> None:
        """Update a row with given key-value pairs."""
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [obj_id]
        self._conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", values)
        self._commit_if_needed()

    def delete(self, table: str, obj_id: int) -> None:
        """Delete a row by id."""
        self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (obj_id,))
        self._commit_if_needed()

    def find_by(self, table: str, column: str, value: Any) -> list[dict]:
        """Find rows where column matches value."""
        cur = self._conn.execute(
            f"SELECT * FROM {table} WHERE {column} = ?", (value,)
        )
        return [dict(r) for r in cur.fetchall()]

    def count(self, table: str) -> int:
        cur = self._conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]

    def fetch_one(self, query: str, parameters: tuple = ()) -> Optional[dict]:
        """Run a fixed, parameterized adapter query and return one row."""
        row = self._conn.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def fetch_all(self, query: str, parameters: tuple = ()) -> list[dict]:
        """Run a fixed, parameterized adapter query and return all rows."""
        rows = self._conn.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def execute(self, query: str, parameters: tuple = ()) -> int:
        """Run a fixed, parameterized adapter write and commit it."""
        cursor = self._conn.execute(query, parameters)
        self._commit_if_needed()
        return cursor.rowcount

    @contextmanager
    def transaction(self):
        """Commit related writes atomically while preserving legacy auto-commit."""
        is_outermost = self._transaction_depth == 0
        if is_outermost:
            self._conn.execute("BEGIN IMMEDIATE")
        self._transaction_depth += 1
        try:
            yield self
        except Exception:
            if is_outermost:
                self._conn.rollback()
            raise
        else:
            if is_outermost:
                self._conn.commit()
        finally:
            self._transaction_depth -= 1

    def _commit_if_needed(self) -> None:
        if self._transaction_depth == 0:
            self._conn.commit()

    # ── Convenience methods ─────────────────────────

    def get_latest_match(self, resume_id: int = None, jd_id: int = None) -> Optional[dict]:
        """Get the most recent match result, optionally filtered."""
        if resume_id and jd_id:
            cur = self._conn.execute(
                "SELECT * FROM match_results WHERE resume_id = ? AND jd_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (resume_id, jd_id),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM match_results ORDER BY id DESC LIMIT 1"
            )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_suggestions_for_match(self, match_id: int) -> list[dict]:
        return self.find_by("suggestions", "match_id", match_id)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Single global instance ───────────────────────────

_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


# ── Helpers ──────────────────────────────────────────

def _to_db(obj: Any) -> dict:
    """Convert dataclass to DB-safe dict, JSON-encoding complex fields."""
    data = {}
    for f, val in obj.__dataclass_fields__.items():
        attr = getattr(obj, f)
        if isinstance(attr, (list, dict)):
            data[f] = json.dumps(attr, ensure_ascii=False)
        elif isinstance(attr, bool):
            data[f] = int(attr)
        else:
            data[f] = attr
    if isinstance(obj, User):
        data["settings_json"] = data.pop("settings")
    return data


def row_to_model(row: dict, model_class: type) -> Any:
    """Convert a DB row dict back to the dataclass instance."""
    row = dict(row)
    if model_class is User:
        row["settings"] = row.get("settings_json", "{}")
        row["is_active"] = bool(row.get("is_active", 1))
    kwargs = {}
    for f, field_obj in model_class.__dataclass_fields__.items():
        val = row.get(f)
        # JSON-decode list/dict fields
        if field_obj.type in (list, dict) or str(field_obj.type).startswith("list") or str(field_obj.type).startswith("dict"):
            if isinstance(val, str):
                val = json.loads(val)
            elif val is None:
                val = field_obj.type() if field_obj.type in (list, dict) else field_obj.default_factory()
        kwargs[f] = val
    return model_class(**kwargs)
