"""Tests for the manually labelled Evidence Matcher benchmark."""

import copy

import pytest

from src.core.evidence_evaluator import (
    EvidenceEvaluationError,
    evaluate_evidence_predictions,
    load_evidence_benchmark,
    validate_evidence_benchmark,
)


def _gold_predictions(benchmark):
    return [
        {
            "sample_id": sample["sample_id"],
            "status": sample["expected_status"],
            "evidence": copy.deepcopy(sample["expected_evidence"]),
        }
        for sample in benchmark["samples"]
    ]


def test_benchmark_contains_30_grounded_samples_and_all_statuses():
    benchmark = load_evidence_benchmark()

    assert benchmark["version"] == "1.0"
    assert len(benchmark["samples"]) == 30
    assert {sample["expected_status"] for sample in benchmark["samples"]} == {
        "proven", "partial", "missing", "uncertain"
    }
    assert len({sample["sample_id"] for sample in benchmark["samples"]}) == 30


def test_perfect_predictions_receive_perfect_metrics():
    benchmark = load_evidence_benchmark()

    metrics = evaluate_evidence_predictions(benchmark, _gold_predictions(benchmark))

    assert metrics["coverage"] == 1.0
    assert metrics["status_accuracy"] == 1.0
    assert metrics["source_location_accuracy"] == 1.0
    assert metrics["grounded_evidence_rate"] == 1.0
    assert metrics["unsupported_evidence_count"] == 0


def test_missing_and_wrong_predictions_reduce_metrics():
    benchmark = load_evidence_benchmark()
    predictions = _gold_predictions(benchmark)[:-1]
    predictions[0]["status"] = "missing"
    predictions[1]["evidence"] = []

    metrics = evaluate_evidence_predictions(benchmark, predictions)

    assert metrics["coverage"] < 1
    assert metrics["status_accuracy"] < 1
    assert metrics["source_location_accuracy"] < 1
    assert metrics["confusion_matrix"]["proven"]["missing"] == 1
    assert sum(row["not_predicted"] for row in metrics["confusion_matrix"].values()) == 1


def test_benchmark_rejects_ungrounded_manual_annotation():
    benchmark = load_evidence_benchmark()
    broken = copy.deepcopy(benchmark)
    sample = next(item for item in broken["samples"] if item["expected_evidence"])
    sample["expected_evidence"][0]["text"] = "Fabricated achievement"

    with pytest.raises(EvidenceEvaluationError, match="not grounded"):
        validate_evidence_benchmark(broken)


def test_evaluator_rejects_duplicate_or_unknown_predictions():
    benchmark = load_evidence_benchmark()
    first = _gold_predictions(benchmark)[0]

    with pytest.raises(EvidenceEvaluationError, match="Duplicate prediction"):
        evaluate_evidence_predictions(benchmark, [first, copy.deepcopy(first)])
    unknown = copy.deepcopy(first)
    unknown["sample_id"] = "unknown_sample"
    with pytest.raises(EvidenceEvaluationError, match="Unknown prediction"):
        evaluate_evidence_predictions(benchmark, [unknown])
