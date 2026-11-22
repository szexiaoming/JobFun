"""Tests for cross-version stable resume source identifiers."""

import copy

from src.core.source_locator import assign_source_ids, find_source_by_id


RESUME = {
    "sections": [
        {
            "title": "Experience",
            "entries": [
                {
                    "header": "Engineer @ Acme",
                    "bullets": [
                        "Built Python APIs",
                        "Reduced latency by 30%",
                    ],
                }
            ],
        }
    ]
}


def _bullet_ids(resume):
    return {
        bullet["text"]: bullet["source_id"]
        for bullet in resume["sections"][0]["entries"][0]["bullets"]
    }


def test_assign_source_ids_is_deterministic_and_does_not_mutate_input():
    original = copy.deepcopy(RESUME)

    first = assign_source_ids(RESUME)
    second = assign_source_ids(RESUME)

    assert first == second
    assert RESUME == original
    assert first["sections"][0]["source_id"].startswith("sec_")
    assert first["sections"][0]["entries"][0]["source_id"].startswith("ent_")
    assert all(
        bullet["source_id"].startswith("bul_")
        for bullet in first["sections"][0]["entries"][0]["bullets"]
    )


def test_exact_bullets_keep_ids_when_reordered_or_shifted_by_insertion():
    previous = assign_source_ids(RESUME)
    current = copy.deepcopy(RESUME)
    current["sections"][0]["entries"][0]["bullets"] = [
        "Launched a new service",
        "Reduced latency by 30%",
        "Built Python APIs",
    ]

    reconciled = assign_source_ids(current, previous)
    before = _bullet_ids(previous)
    after = _bullet_ids(reconciled)

    assert after["Built Python APIs"] == before["Built Python APIs"]
    assert after["Reduced latency by 30%"] == before["Reduced latency by 30%"]
    assert after["Launched a new service"] not in set(before.values())


def test_edited_bullet_at_same_index_inherits_source_id():
    previous = assign_source_ids(RESUME)
    current = copy.deepcopy(RESUME)
    current["sections"][0]["entries"][0]["bullets"][0] = (
        "Built and operated Python APIs"
    )

    reconciled = assign_source_ids(current, previous)

    assert (
        reconciled["sections"][0]["entries"][0]["bullets"][0]["source_id"]
        == previous["sections"][0]["entries"][0]["bullets"][0]["source_id"]
    )


def test_duplicate_nodes_receive_unique_ids():
    duplicate_resume = {
        "sections": [
            {"title": "Projects", "entries": []},
            {"title": "Projects", "entries": []},
        ]
    }

    located = assign_source_ids(duplicate_resume)

    assert located["sections"][0]["source_id"] != located["sections"][1]["source_id"]


def test_find_source_by_id_returns_bullet_context():
    located = assign_source_ids(RESUME)
    bullet = located["sections"][0]["entries"][0]["bullets"][1]

    found = find_source_by_id(located, bullet["source_id"])

    assert found["kind"] == "bullet"
    assert found["index"] == 1
    assert found["node"]["text"] == "Reduced latency by 30%"


def test_existing_ids_and_bullet_metadata_are_preserved():
    resume = copy.deepcopy(RESUME)
    resume["sections"][0]["source_id"] = "sec_existing"
    resume["sections"][0]["entries"][0]["source_id"] = "ent_existing"
    resume["sections"][0]["entries"][0]["bullets"][0] = {
        "text": "Built Python APIs",
        "source_id": "bul_existing",
        "latex_command": "item",
    }

    located = assign_source_ids(resume)
    bullet = located["sections"][0]["entries"][0]["bullets"][0]

    assert located["sections"][0]["source_id"] == "sec_existing"
    assert located["sections"][0]["entries"][0]["source_id"] == "ent_existing"
    assert bullet["source_id"] == "bul_existing"
    assert bullet["latex_command"] == "item"

