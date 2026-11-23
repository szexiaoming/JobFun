"""Optional, read-only LangChain tool runner for a single requirement."""

from __future__ import annotations

import json
import uuid

import config
from src.ai.prompts.gap_explanation import SYSTEM_PROMPT
from src.services.gap_explanations import lexical_candidates


def propose_gap_action(
    requirement: dict,
    verified: list[dict],
    candidates: list[dict],
    *,
    user_id: int,
    resume_id: int,
) -> dict | None:
    """Return a constrained decision; missing dependencies or model errors fall back."""
    try:
        from langchain.agents import create_agent
        from langchain.tools import tool

        model = _configured_model()
        if model is None:
            return None
        used_tools: set[str] = set()

        @tool
        def read_requirement() -> str:
            """Read the selected requirement and its recorded match state."""
            used_tools.add("requirement")
            return json.dumps(requirement, ensure_ascii=False)

        @tool
        def read_verified_evidence() -> str:
            """Read only evidence already verified against the pinned resume."""
            used_tools.add("evidence")
            return json.dumps(verified[:8], ensure_ascii=False)

        @tool
        def search_resume_candidates(query: str) -> str:
            """Find possible resume passages; results are unverified candidates."""
            used_tools.add("candidates")
            results = _retrieve_candidates(query[:300], candidates, user_id, resume_id)
            return json.dumps(results, ensure_ascii=False)

        agent = create_agent(
            model=model,
            tools=[read_requirement, read_verified_evidence, search_resume_candidates],
            system_prompt=SYSTEM_PROMPT,
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "解释当前岗位要求的差距。先读取要求和已验证证据，再决定是否检索候选段落。"}]},
            config={"recursion_limit": 8},
        )
        if not {"requirement", "evidence"}.issubset(used_tools):
            return None
        messages = result.get("messages", []) if isinstance(result, dict) else []
        raw = getattr(messages[-1], "content", "") if messages else ""
        if not isinstance(raw, str):
            return None
        decision = json.loads(raw)
        if not isinstance(decision, dict) or set(decision) != {"action_kind", "candidate_source_ids"}:
            return None
        if decision["action_kind"] not in {"verify_experience", "prepare_interview", "learn_requirement"}:
            return None
        if not isinstance(decision["candidate_source_ids"], list):
            return None
        if len(decision["candidate_source_ids"]) > 3 or not all(
            isinstance(item, str) for item in decision["candidate_source_ids"]
        ):
            return None
        return decision
    except (ImportError, ValueError, TypeError, KeyError, RuntimeError, OSError, json.JSONDecodeError):
        return None
    except Exception:
        # Provider and framework errors remain private; the deterministic result is safe.
        return None


def _configured_model():
    if config.AI_PROVIDER == "anthropic":
        if not config.ANTHROPIC_API_KEY.strip():
            return None
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config.get_active_model("agent"), api_key=config.ANTHROPIC_API_KEY, temperature=0)
    if config.AI_PROVIDER == "deepseek":
        if not config.DEEPSEEK_API_KEY.strip():
            return None
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.get_active_model("agent"),
            base_url=config.DEEPSEEK_BASE_URL,
            api_key=config.DEEPSEEK_API_KEY,
            temperature=0,
        )
    return None


def _retrieve_candidates(query: str, candidates: list[dict], user_id: int, resume_id: int) -> list[dict]:
    if not candidates:
        return []
    try:
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        collection = Chroma.from_texts(
            texts=[item["text"] for item in candidates],
            embedding=embeddings,
            metadatas=[{
                "user_id": user_id,
                "resume_id": resume_id,
                "source_id": item["source_id"],
            } for item in candidates],
            collection_name=f"gap_{uuid.uuid4().hex}",
        )
        try:
            docs = collection.similarity_search(query, k=min(3, len(candidates)), filter={
                "$and": [{"user_id": user_id}, {"resume_id": resume_id}],
            })
            by_id = {item["source_id"]: item for item in candidates}
            return [by_id[doc.metadata["source_id"]] for doc in docs if doc.metadata.get("source_id") in by_id]
        finally:
            collection.delete_collection()
    except Exception:
        return lexical_candidates(query, candidates)
