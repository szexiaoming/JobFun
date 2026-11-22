"""SQLite ownership queries that hide foreign or inconsistent resources."""

from __future__ import annotations

from typing import Any

from src.core.interview_insights import InterviewInsights, get_interview_insights
from src.core.workbench import WorkbenchSummary, build_workbench_summary
from src.db.sqlite_client import Database


class SQLiteOwnershipRepository:
    def __init__(self, database: Database):
        self._database = database

    def _owned(
        self,
        query: str,
        user_id: int,
        resource_id: int,
        user_parameter_count: int,
    ) -> dict[str, Any] | None:
        parameters = (resource_id,) + (user_id,) * user_parameter_count
        return self._database.fetch_one(query, parameters)

    def _list(self, query: str, parameters: tuple) -> list[dict[str, Any]]:
        return self._database.fetch_all(query, parameters)

    def list_resumes(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return self._list(
            """
            SELECT r.* FROM resumes AS r
            WHERE r.user_id = ?
            ORDER BY r.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )

    def list_job_descriptions(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return self._list(
            """
            SELECT jd.* FROM job_descriptions AS jd
            WHERE jd.user_id = ?
            ORDER BY jd.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )

    def list_matches(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return self._list(
            """
            SELECT match.*
            FROM match_results AS match
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE r.user_id = ? AND jd.user_id = ?
            ORDER BY match.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, user_id, limit, offset),
        )

    def list_applications(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return self._list(
            """
            SELECT application.*
            FROM applications AS application
            JOIN resumes AS r ON r.id = application.resume_id
            JOIN job_descriptions AS jd ON jd.id = application.jd_id
            LEFT JOIN match_results AS match ON match.id = application.match_id
            WHERE application.user_id = ?
              AND r.user_id = ?
              AND jd.user_id = ?
              AND (
                    COALESCE(application.match_id, 0) = 0
                    OR (
                        match.resume_id = application.resume_id
                        AND match.jd_id = application.jd_id
                    )
              )
            ORDER BY application.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, user_id, user_id, limit, offset),
        )

    def get_resume(self, user_id: int, resource_id: int) -> dict[str, Any] | None:
        return self._owned(
            "SELECT r.* FROM resumes AS r WHERE r.id = ? AND r.user_id = ?",
            user_id,
            resource_id,
            1,
        )

    def get_job_description(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            "SELECT jd.* FROM job_descriptions AS jd WHERE jd.id = ? AND jd.user_id = ?",
            user_id,
            resource_id,
            1,
        )

    def get_match(self, user_id: int, resource_id: int) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT match.*
            FROM match_results AS match
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE match.id = ? AND r.user_id = ? AND jd.user_id = ?
            """,
            user_id,
            resource_id,
            2,
        )

    def get_application(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT application.*
            FROM applications AS application
            JOIN resumes AS r ON r.id = application.resume_id
            JOIN job_descriptions AS jd ON jd.id = application.jd_id
            LEFT JOIN match_results AS match ON match.id = application.match_id
            WHERE application.id = ?
              AND application.user_id = ?
              AND r.user_id = ?
              AND jd.user_id = ?
              AND (
                    COALESCE(application.match_id, 0) = 0
                    OR (
                        match.resume_id = application.resume_id
                        AND match.jd_id = application.jd_id
                    )
              )
            """,
            user_id,
            resource_id,
            3,
        )

    def get_evidence_match(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT evidence.*
            FROM evidence_matches AS evidence
            JOIN match_results AS match ON match.id = evidence.match_id
            JOIN job_requirements AS requirement
              ON requirement.id = evidence.requirement_id
             AND requirement.jd_id = match.jd_id
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE evidence.id = ? AND r.user_id = ? AND jd.user_id = ?
            """,
            user_id,
            resource_id,
            2,
        )

    def get_interview_question(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT question.*
            FROM interview_questions AS question
            JOIN match_results AS match ON match.id = question.match_id
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE question.id = ? AND r.user_id = ? AND jd.user_id = ?
            """,
            user_id,
            resource_id,
            2,
        )

    def list_interview_questions(
        self,
        user_id: int,
        application_id: int,
    ) -> list[dict[str, Any]]:
        return self._list(
            """
            SELECT question.*,
                   COUNT(attempt.id) AS attempt_count,
                   MAX(attempt.id) AS latest_attempt_id
            FROM applications AS application
            JOIN match_results AS match
              ON match.id = application.match_id
             AND match.resume_id = application.resume_id
             AND match.jd_id = application.jd_id
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            JOIN interview_questions AS question ON question.match_id = match.id
            LEFT JOIN interview_attempts AS attempt
              ON attempt.question_id = question.id
             AND attempt.application_id = application.id
            WHERE application.id = ?
              AND application.user_id = ?
              AND r.user_id = ?
              AND jd.user_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM interview_follow_ups AS follow_up
                  WHERE follow_up.question_id = question.id
              )
            GROUP BY question.id
            ORDER BY question.id ASC
            """,
            (application_id, user_id, user_id, user_id),
        )

    def get_interview_attempt(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT attempt.*
            FROM interview_attempts AS attempt
            JOIN interview_questions AS question ON question.id = attempt.question_id
            JOIN applications AS application ON application.id = attempt.application_id
            JOIN match_results AS match
              ON match.id = question.match_id
             AND match.id = application.match_id
             AND match.resume_id = application.resume_id
             AND match.jd_id = application.jd_id
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE attempt.id = ?
              AND application.user_id = ?
              AND r.user_id = ?
              AND jd.user_id = ?
            """,
            user_id,
            resource_id,
            3,
        )

    def get_interview_follow_up(
        self,
        user_id: int,
        resource_id: int,
    ) -> dict[str, Any] | None:
        return self._owned(
            """
            SELECT follow_up.*
            FROM interview_follow_ups AS follow_up
            JOIN interview_attempts AS parent_attempt
              ON parent_attempt.id = follow_up.parent_attempt_id
            JOIN applications AS application
              ON application.id = parent_attempt.application_id
            JOIN interview_questions AS parent_question
              ON parent_question.id = parent_attempt.question_id
            JOIN interview_questions AS follow_up_question
              ON follow_up_question.id = follow_up.question_id
             AND follow_up_question.match_id = parent_question.match_id
            JOIN match_results AS match
              ON match.id = parent_question.match_id
             AND match.id = application.match_id
             AND match.resume_id = application.resume_id
             AND match.jd_id = application.jd_id
            JOIN resumes AS r ON r.id = match.resume_id
            JOIN job_descriptions AS jd ON jd.id = match.jd_id
            WHERE follow_up.id = ?
              AND application.user_id = ?
              AND r.user_id = ?
              AND jd.user_id = ?
            """,
            user_id,
            resource_id,
            3,
        )

    def get_workbench_summary(self, user_id: int) -> WorkbenchSummary:
        applications = self.list_applications(user_id, limit=1000, offset=0)
        jobs = {
            row["id"]: row
            for row in self.list_job_descriptions(user_id, limit=1000, offset=0)
        }
        return build_workbench_summary(applications, jobs)

    def get_interview_insights(
        self,
        user_id: int,
        application_id: int,
    ) -> InterviewInsights | None:
        application = self.get_application(user_id, application_id)
        if application is None:
            return None
        match_id = int(application.get("match_id") or 0)
        if not match_id:
            return InterviewInsights()
        if self.get_match(user_id, match_id) is None:
            return None
        return get_interview_insights(
            match_id,
            application_id=application_id,
            db=self._database,
        )
