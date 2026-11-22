"""Tests for the four-item navigation and read-only job catalog."""

from ui.jobs import build_job_catalog, filter_job_catalog
from ui.navigation import PRIMARY_NAV_ITEMS, normalize_page


def test_primary_navigation_contains_exactly_the_planned_four_items():
    assert PRIMARY_NAV_ITEMS == (
        ("workbench", "🏠 工作台"),
        ("jobs", "💼 岗位"),
        ("interview", "🎯 面试"),
        ("profile", "👤 个人档案"),
    )


def test_legacy_routes_are_normalized_without_losing_access():
    assert normalize_page("home") == "workbench"
    assert normalize_page("tracker") == "workbench"
    assert normalize_page("editor") == "profile"
    assert normalize_page("resumes") == "profile"
    assert normalize_page("agent") == "agent"
    assert normalize_page("unknown") == "workbench"


def test_catalog_uses_latest_match_and_collects_application_statuses():
    jobs = [{
        "id": 3,
        "company": "Acme",
        "position": "Engineer",
        "raw_text": "Python role",
        "structured_json": "{}",
        "source_type": "text",
        "created_at": "2026-11-20",
    }]
    matches = [
        {"id": 10, "jd_id": 3, "total_score": 60},
        {"id": 12, "jd_id": 3, "total_score": 82},
    ]
    applications = [
        {"id": 1, "jd_id": 3, "status": "saved"},
        {"id": 2, "jd_id": 3, "status": "interview"},
    ]

    item = build_job_catalog(jobs, matches, applications)[0]

    assert item.latest_match["id"] == 12
    assert item.latest_match["total_score"] == 82
    assert item.match_count == 2
    assert item.application_statuses == ["saved", "interview"]
    assert item.application_count == 2


def test_catalog_falls_back_to_structured_company_and_position():
    jobs = [{
        "id": 4,
        "company": "",
        "position": "",
        "raw_text": "",
        "structured_json": '{"company":"Lumen","position":"Data Analyst"}',
        "source_type": "pdf",
        "created_at": "",
    }]

    item = build_job_catalog(jobs, [], [])[0]

    assert item.company == "Lumen"
    assert item.position == "Data Analyst"
    assert item.structured_json["company"] == "Lumen"


def test_catalog_filters_search_match_and_application_scopes():
    jobs = [
        {"id": 1, "company": "Acme", "position": "Python Engineer", "raw_text": "AWS", "structured_json": "{}"},
        {"id": 2, "company": "Lumen", "position": "Designer", "raw_text": "Figma", "structured_json": "{}"},
    ]
    items = build_job_catalog(
        jobs,
        [{"id": 1, "jd_id": 1, "total_score": 70}],
        [{"id": 1, "jd_id": 2, "status": "saved"}],
    )

    assert [item.id for item in filter_job_catalog(items, "python")] == [1]
    assert [item.id for item in filter_job_catalog(items, scope="有匹配")] == [1]
    assert [item.id for item in filter_job_catalog(items, scope="未匹配")] == [2]
    assert [item.id for item in filter_job_catalog(items, scope="有申请")] == [2]


def test_invalid_structured_json_does_not_break_catalog():
    jobs = [{
        "id": 9,
        "company": "",
        "position": "",
        "structured_json": "not-json",
    }]

    item = build_job_catalog(jobs, [], [])[0]

    assert item.company == "未填写公司"
    assert item.position == "未填写岗位"
    assert item.structured_json == {}
