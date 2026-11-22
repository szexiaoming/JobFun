"""Cross-user ownership checks for the Phase 4 repository boundary."""

from src.db.models import (
    Application,
    EvidenceMatch,
    InterviewAttempt,
    InterviewFollowUp,
    InterviewQuestion,
    JobDescription,
    JobRequirement,
    MatchResult,
    Resume,
    User,
)
from src.db.sqlite_client import Database
from src.repositories.sqlite_ownership import SQLiteOwnershipRepository


def _chain(database: Database, user_id: int, suffix: str) -> dict[str, int]:
    resume_id = database.insert(
        "resumes",
        Resume(user_id=user_id, name=f"Resume {suffix}", latex_path=""),
    )
    jd_id = database.insert(
        "job_descriptions",
        JobDescription(user_id=user_id, company=f"Company {suffix}", position="Engineer"),
    )
    match_id = database.insert(
        "match_results",
        MatchResult(resume_id=resume_id, jd_id=jd_id, total_score=80),
    )
    requirement_id = database.insert(
        "job_requirements",
        JobRequirement(
            jd_id=jd_id,
            text=f"Python {suffix}",
            normalized_key=f"python-{suffix}",
        ),
    )
    evidence_id = database.insert(
        "evidence_matches",
        EvidenceMatch(match_id=match_id, requirement_id=requirement_id),
    )
    application_id = database.insert(
        "applications",
        Application(
            user_id=user_id,
            jd_id=jd_id,
            resume_id=resume_id,
            match_id=match_id,
        ),
    )
    question_id = database.insert(
        "interview_questions",
        InterviewQuestion(match_id=match_id, question=f"Question {suffix}"),
    )
    attempt_id = database.insert(
        "interview_attempts",
        InterviewAttempt(
            question_id=question_id,
            application_id=application_id,
            answer_text=f"Answer {suffix}",
        ),
    )
    follow_up_question_id = database.insert(
        "interview_questions",
        InterviewQuestion(match_id=match_id, question=f"Follow-up {suffix}"),
    )
    follow_up_id = database.insert(
        "interview_follow_ups",
        InterviewFollowUp(
            parent_attempt_id=attempt_id,
            question_id=follow_up_question_id,
            target_dimension="technical_accuracy",
            rationale="Need detail",
        ),
    )
    return {
        "resume": resume_id,
        "job": jd_id,
        "match": match_id,
        "requirement": requirement_id,
        "evidence": evidence_id,
        "application": application_id,
        "question": question_id,
        "attempt": attempt_id,
        "follow_up": follow_up_id,
    }


def test_every_resource_is_visible_only_to_its_owner(tmp_path):
    database = Database(tmp_path / "ownership.db")
    user_two = database.insert("users", User(username="bob"))
    owner_one = _chain(database, 1, "one")
    owner_two = _chain(database, user_two, "two")
    repository = SQLiteOwnershipRepository(database)

    getters = {
        "resume": repository.get_resume,
        "job": repository.get_job_description,
        "match": repository.get_match,
        "application": repository.get_application,
        "evidence": repository.get_evidence_match,
        "question": repository.get_interview_question,
        "attempt": repository.get_interview_attempt,
        "follow_up": repository.get_interview_follow_up,
    }
    for name, getter in getters.items():
        assert getter(1, owner_one[name]) is not None
        assert getter(user_two, owner_two[name]) is not None
        assert getter(1, owner_two[name]) is None
        assert getter(user_two, owner_one[name]) is None
        assert getter(1, 999999) is None
    database.close()


def test_inconsistent_cross_user_links_are_hidden_from_both_users(tmp_path):
    database = Database(tmp_path / "inconsistent.db")
    user_two = database.insert("users", User(username="bob"))
    owner_one = _chain(database, 1, "one")
    owner_two = _chain(database, user_two, "two")
    repository = SQLiteOwnershipRepository(database)

    crossed_application = database.insert(
        "applications",
        Application(
            user_id=1,
            jd_id=owner_two["job"],
            resume_id=owner_two["resume"],
            match_id=owner_two["match"],
        ),
    )
    crossed_evidence = database.insert(
        "evidence_matches",
        EvidenceMatch(
            match_id=owner_one["match"],
            requirement_id=owner_two["requirement"],
        ),
    )
    crossed_attempt = database.insert(
        "interview_attempts",
        InterviewAttempt(
            question_id=owner_two["question"],
            application_id=owner_one["application"],
            answer_text="Invalid cross-user answer",
        ),
    )

    for user_id in (1, user_two):
        assert repository.get_application(user_id, crossed_application) is None
        assert repository.get_evidence_match(user_id, crossed_evidence) is None
        assert repository.get_interview_attempt(user_id, crossed_attempt) is None
    database.close()
