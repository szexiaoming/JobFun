"""Offline evaluation for manually labelled Evidence Matcher samples."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.core.source_locator import bullet_text


DEFAULT_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "evaluation"
    / "evidence_benchmark_v1.json"
)
EVIDENCE_STATUSES = {"proven", "partial", "missing", "uncertain"}
_SAMPLE_KEYS = {
    "sample_id",
    "resume_id",
    "requirement",
    "expected_status",
    "expected_evidence",
    "annotation_note",
}
_EVIDENCE_KEYS = {"text", "section", "entry", "bullet_index"}


class EvidenceEvaluationError(Exception):
    """Raised when benchmark data or predictions violate the contract."""


def load_evidence_benchmark(path: Optional[Path] = None) -> dict:
    """Load and validate the versioned, manually labelled benchmark."""
    benchmark_path = Path(path or DEFAULT_BENCHMARK_PATH)
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceEvaluationError(
            f"Unable to load evidence benchmark: {benchmark_path}"
        ) from exc
    validate_evidence_benchmark(benchmark)
    return benchmark


def validate_evidence_benchmark(benchmark: dict) -> None:
    """Validate labels and ensure every annotated quote is resume-grounded."""
    if not isinstance(benchmark, dict):
        raise EvidenceEvaluationError("Benchmark must be an object")
    if not isinstance(benchmark.get("version"), str) or not benchmark["version"]:
        raise EvidenceEvaluationError("Benchmark version is required")
    resumes = benchmark.get("resumes")
    samples = benchmark.get("samples")
    if not isinstance(resumes, dict) or not resumes:
        raise EvidenceEvaluationError("Benchmark resumes are required")
    if not isinstance(samples, list) or not samples:
        raise EvidenceEvaluationError("Benchmark samples are required")

    seen_ids: set[str] = set()
    for index, sample in enumerate(samples):
        path = f"samples[{index}]"
        if not isinstance(sample, dict) or set(sample) != _SAMPLE_KEYS:
            raise EvidenceEvaluationError(f"{path} does not match the sample contract")
        sample_id = sample["sample_id"]
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise EvidenceEvaluationError(f"{path}.sample_id is required")
        if sample_id in seen_ids:
            raise EvidenceEvaluationError(f"Duplicate sample_id: {sample_id}")
        seen_ids.add(sample_id)
        resume = resumes.get(sample["resume_id"])
        if not isinstance(resume, dict):
            raise EvidenceEvaluationError(f"{path} references an unknown resume")
        if not isinstance(sample["requirement"], str) or not sample["requirement"].strip():
            raise EvidenceEvaluationError(f"{path}.requirement is required")
        if sample["expected_status"] not in EVIDENCE_STATUSES:
            raise EvidenceEvaluationError(f"{path}.expected_status is invalid")
        evidence = sample["expected_evidence"]
        if not isinstance(evidence, list):
            raise EvidenceEvaluationError(f"{path}.expected_evidence must be a list")
        if sample["expected_status"] in {"proven", "partial"} and not evidence:
            raise EvidenceEvaluationError(f"{path} requires annotated evidence")
        if sample["expected_status"] == "missing" and evidence:
            raise EvidenceEvaluationError(f"{path} missing label cannot contain evidence")
        if not isinstance(sample["annotation_note"], str) or not sample["annotation_note"].strip():
            raise EvidenceEvaluationError(f"{path}.annotation_note is required")
        for evidence_index, item in enumerate(evidence):
            if not _is_grounded(item, resume, strict=True):
                raise EvidenceEvaluationError(
                    f"{path}.expected_evidence[{evidence_index}] is not grounded"
                )


def evaluate_evidence_predictions(benchmark: dict, predictions: list[dict]) -> dict:
    """Compare model predictions against manual status and source annotations."""
    validate_evidence_benchmark(benchmark)
    if not isinstance(predictions, list):
        raise EvidenceEvaluationError("Predictions must be a list")

    samples = {sample["sample_id"]: sample for sample in benchmark["samples"]}
    prediction_map: dict[str, dict] = {}
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, dict) or set(prediction) != {
            "sample_id", "status", "evidence"
        }:
            raise EvidenceEvaluationError(
                f"predictions[{index}] does not match the prediction contract"
            )
        sample_id = prediction["sample_id"]
        if sample_id not in samples:
            raise EvidenceEvaluationError(f"Unknown prediction sample_id: {sample_id}")
        if sample_id in prediction_map:
            raise EvidenceEvaluationError(f"Duplicate prediction: {sample_id}")
        if prediction["status"] not in EVIDENCE_STATUSES:
            raise EvidenceEvaluationError(f"Invalid predicted status: {sample_id}")
        if not isinstance(prediction["evidence"], list):
            raise EvidenceEvaluationError(f"Prediction evidence must be a list: {sample_id}")
        prediction_map[sample_id] = prediction

    total = len(samples)
    status_correct = 0
    source_exact = 0
    grounded_count = 0
    predicted_evidence_count = 0
    unsupported_count = 0
    confusion = {
        expected: {actual: 0 for actual in (*sorted(EVIDENCE_STATUSES), "not_predicted")}
        for expected in sorted(EVIDENCE_STATUSES)
    }

    for sample_id, sample in samples.items():
        prediction = prediction_map.get(sample_id)
        actual_status = prediction["status"] if prediction else "not_predicted"
        confusion[sample["expected_status"]][actual_status] += 1
        if prediction is None:
            continue
        if actual_status == sample["expected_status"]:
            status_correct += 1

        expected_locations = {_location(item) for item in sample["expected_evidence"]}
        predicted_locations = {_location(item) for item in prediction["evidence"]}
        if predicted_locations == expected_locations:
            source_exact += 1
        unsupported_count += len(predicted_locations - expected_locations)

        resume = benchmark["resumes"][sample["resume_id"]]
        for item in prediction["evidence"]:
            predicted_evidence_count += 1
            if _is_grounded(item, resume, strict=False):
                grounded_count += 1

    return {
        "benchmark_version": benchmark["version"],
        "sample_count": total,
        "prediction_count": len(prediction_map),
        "coverage": _ratio(len(prediction_map), total),
        "status_accuracy": _ratio(status_correct, total),
        "source_location_accuracy": _ratio(source_exact, total),
        "grounded_evidence_rate": _ratio(
            grounded_count,
            predicted_evidence_count,
            empty_value=1.0,
        ),
        "unsupported_evidence_count": unsupported_count,
        "confusion_matrix": confusion,
    }


def _is_grounded(item: dict, resume: dict, *, strict: bool) -> bool:
    if not isinstance(item, dict) or set(item) != _EVIDENCE_KEYS:
        if strict:
            raise EvidenceEvaluationError("Evidence does not match the contract")
        return False
    text, section_name, entry_name = item["text"], item["section"], item["entry"]
    bullet_index = item["bullet_index"]
    if not all(isinstance(value, str) and value.strip() for value in (text, section_name, entry_name)):
        return False
    if bullet_index is not None and (
        isinstance(bullet_index, bool) or not isinstance(bullet_index, int) or bullet_index < 0
    ):
        return False
    section = next((node for node in resume.get("sections", []) if isinstance(node, dict) and _same(node.get("title", ""), section_name)), None)
    if section is None:
        return False
    entry = next((node for node in section.get("entries", []) if isinstance(node, dict) and _same(node.get("header", ""), entry_name)), None)
    if entry is None:
        return False
    bullets = entry.get("bullets", [])
    if bullet_index is None:
        candidates = [entry.get("header", ""), *(bullet_text(item) for item in bullets)]
    elif bullet_index < len(bullets):
        candidates = [bullet_text(bullets[bullet_index])]
    else:
        return False
    quote = _normalize(text)
    return any(quote in _normalize(candidate) for candidate in candidates)


def _location(item: dict) -> tuple:
    if not isinstance(item, dict):
        return ("invalid", repr(item))
    return (
        _normalize(item.get("section", "")),
        _normalize(item.get("entry", "")),
        item.get("bullet_index"),
    )


def _normalize(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _same(left, right) -> bool:
    return _normalize(left) == _normalize(right)


def _ratio(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    return round(numerator / denominator, 4) if denominator else empty_value
