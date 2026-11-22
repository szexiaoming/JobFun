"""Tests for the evidence matrix presentation model."""

from src.db.models import (
    EvidenceMatch,
    EvidenceReview,
    EvidenceSupplement,
    JobRequirement,
)
from ui.evidence_matrix import (
    STATUS_PRESENTATION,
    _source_caption,
    build_evidence_matrix_rows,
)
from ui.match import SCORE_DISCLAIMER


def test_matrix_rows_are_priority_sorted_and_joined_by_requirement():
    high = JobRequirement(id=2, priority=1, text="Python")
    low = JobRequirement(id=1, priority=3, text="Docker")
    evidence = EvidenceMatch(
        id=10,
        match_id=7,
        requirement_id=2,
        status="proven",
        evidence_json=[{"text": "Python", "bullet_index": 0}],
    )
    review = EvidenceReview(id=20, evidence_match_id=10, action="confirmed")
    supplement = EvidenceSupplement(
        id=30,
        match_id=7,
        requirement_id=2,
        title="Extra context",
    )

    rows = build_evidence_matrix_rows(
        [low, high],
        [evidence],
        [supplement],
        {10: [review]},
    )

    assert [row.requirement.id for row in rows] == [2, 1]
    assert rows[0].evidence_match is evidence
    assert rows[0].reviews == [review]
    assert rows[0].supplements == [supplement]
    assert rows[0].status == "proven"


def test_requirement_without_evidence_is_not_mislabelled_as_missing():
    requirement = JobRequirement(id=1, priority=1, text="Go")

    row = build_evidence_matrix_rows([requirement], [], [])[0]

    assert row.status == "not_analyzed"
    assert STATUS_PRESENTATION[row.status][1] == "尚未分析"


def test_supplements_do_not_cross_requirement_boundaries():
    requirements = [
        JobRequirement(id=1, priority=1, text="Python"),
        JobRequirement(id=2, priority=1, text="AWS"),
    ]
    supplement = EvidenceSupplement(id=5, requirement_id=2, title="AWS project")

    rows = build_evidence_matrix_rows(requirements, [], [supplement])

    assert rows[0].supplements == []
    assert rows[1].supplements == [supplement]


def test_source_caption_uses_human_readable_one_based_index():
    caption = _source_caption({
        "section": "Experience",
        "entry": "Engineer @ Acme",
        "bullet_index": 0,
    })

    assert caption == "来源：Experience › Engineer @ Acme › 第 1 条要点"


def test_score_disclaimer_does_not_describe_probability():
    assert "辅助判断" in SCORE_DISCLAIMER
    assert "不代表" in SCORE_DISCLAIMER
    assert "录用" in SCORE_DISCLAIMER
