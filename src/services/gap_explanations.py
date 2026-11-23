"""Read-only, application-bound gap explanation inputs and safe output."""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.evidence_matcher import extract_job_requirements
from src.core.source_locator import assign_source_ids, bullet_text, find_source_by_id


GAP_STATUSES = {"proven", "partial", "missing", "uncertain", "unassessed"}


def json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def requirement_options(jd_id: int, structured_jd: dict) -> list[dict]:
    """Stable, non-persisted options for both new and historical applications."""
    if not structured_jd:
        return []
    return [
        {
            "key": requirement.normalized_key,
            "text": requirement.text,
            "category": requirement.category,
            "priority": requirement.priority,
        }
        for requirement in extract_job_requirements(jd_id, structured_jd)
    ]


def verified_evidence(evidence_row: dict | None, resume_json: dict) -> tuple[str, list[dict]]:
    """Recheck stored quotes against the pinned resume before public display."""
    if not evidence_row:
        return "unassessed", []
    status = str(evidence_row.get("status") or "uncertain")
    if status not in GAP_STATUSES:
        status = "uncertain"
    if str(evidence_row.get("user_status") or "") == "rejected":
        return "uncertain", []
    source_resume = assign_source_ids(resume_json)
    result: list[dict] = []
    for item in json_list(evidence_row.get("evidence_json")):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        quote = str(item.get("text") or "").strip()
        found = find_source_by_id(source_resume, source_id) if source_id else None
        if not found or not quote:
            continue
        section = found.get("section")
        entry = found.get("entry") if found["kind"] == "bullet" else found.get("node")
        if found["kind"] == "bullet":
            actual_text = bullet_text(found["node"])
            actual_index = found["index"]
        elif found["kind"] == "entry":
            actual_text = str(found["node"].get("header") or "")
            actual_index = None
        else:
            continue
        if not section or not entry:
            continue
        if (
            _normal(quote) not in _normal(actual_text)
            or _normal(item.get("section")) != _normal(section.get("title"))
            or _normal(item.get("entry")) != _normal(entry.get("header"))
            or (item.get("bullet_index") is not None and item.get("bullet_index") != actual_index)
        ):
            continue
        result.append({
            "source_id": source_id,
            "text": quote,
            "section": str(section.get("title") or ""),
            "entry": str(entry.get("header") or ""),
            "bullet_index": actual_index,
        })
    if status in {"proven", "partial"} and not result:
        return "uncertain", []
    if status == "missing":
        return "missing", []
    return status, result


def resume_candidates(resume_json: dict) -> list[dict]:
    """Build a request-local retrieval corpus from one resume version."""
    result = []
    for section in assign_source_ids(resume_json).get("sections", []):
        if not isinstance(section, dict):
            continue
        for entry in section.get("entries", []):
            if not isinstance(entry, dict):
                continue
            for index, bullet in enumerate(entry.get("bullets", [])):
                text = bullet_text(bullet).strip()
                if text and isinstance(bullet, dict) and bullet.get("source_id"):
                    result.append({
                        "source_id": str(bullet["source_id"]),
                        "text": text[:1_000],
                        "section": str(section.get("title") or ""),
                        "entry": str(entry.get("header") or ""),
                        "bullet_index": index,
                    })
                    if len(result) >= 128:
                        return result
    return result


def build_explanation(
    *, application_id: int, requirement: dict, evidence_row: dict | None,
    resume_json: dict, agent_draft: dict | None = None,
) -> dict:
    status, evidence = verified_evidence(evidence_row, resume_json)
    if status == "proven":
        explanation = "已找到与这项要求对应的简历原文，请核对经历范围和个人贡献。"
        next_action = "围绕已引用的真实经历准备项目细节与面试回答。"
    elif status == "partial":
        explanation = "现有简历只有部分相关证据，尚不足以证明完整满足这项要求。"
        next_action = "核实缺少的具体环节；如有真实经历，再由你确认是否补充。"
    elif status == "missing":
        explanation = "当前申请绑定的简历版本未找到这项要求的证据。"
        next_action = "先确认是否有未写入简历的真实经历；没有时将其作为准备方向。"
    else:
        explanation = "当前申请绑定的简历版本尚无可确认的匹配证据。"
        next_action = "先核对简历原文和岗位要求，再决定是否补充真实经历。"
    question = "" if status == "proven" else f"你是否有与“{requirement['text']}”相关、但尚未写入这版简历的真实经历？"
    mode = "baseline"
    candidate_evidence: list[dict] = []
    if isinstance(agent_draft, dict):
        action_kind = agent_draft.get("action_kind")
        if action_kind == "prepare_interview" and evidence:
            next_action = "围绕已引用的真实经历准备项目细节和岗位相关的面试回答。"
        elif action_kind == "learn_requirement" and status in {"missing", "unassessed", "uncertain"}:
            next_action = "当前证据不足；可先学习这项岗位要求，再记录真实完成的练习或项目。"
        candidate_ids = agent_draft.get("candidate_source_ids")
        if isinstance(candidate_ids, list):
            allowed = {item["source_id"]: item for item in resume_candidates(resume_json)}
            seen: set[str] = set()
            for source_id in candidate_ids[:3]:
                if isinstance(source_id, str) and source_id in allowed and source_id not in seen:
                    candidate_evidence.append(allowed[source_id])
                    seen.add(source_id)
        mode = "langchain"
    return {
        "application_id": application_id,
        "requirement": {**requirement, "status": status, "evidence": evidence},
        "status": status,
        "evidence": evidence,
        "candidate_evidence": candidate_evidence,
        "explanation": explanation,
        "clarification_question": question,
        "next_action": next_action,
        "mode": mode,
    }


def lexical_candidates(query: str, candidates: list[dict], limit: int = 3) -> list[dict]:
    terms = set(re.findall(r"[\w+#.-]{2,}", query.casefold()))
    ranked = sorted(
        candidates,
        key=lambda item: sum(term in item["text"].casefold() for term in terms),
        reverse=True,
    )
    return ranked[:limit]


def _normal(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()
