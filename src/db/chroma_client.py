"""
ChromaDB client for vector storage and retrieval.
Uses sentence-transformers for local embedding generation (free, no API key needed).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from src.utils.logger import logger

# ── Constants ────────────────────────────────────────
CHROMA_PATH = DATA_DIR / "chroma"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, small & fast
COLLECTION_JDS = "jds"
COLLECTION_SUGGESTIONS = "suggestions"


class ChromaClientError(Exception):
    """Raised when a ChromaDB operation fails."""


class ChromaClient:
    def __init__(self, persist_dir: Path = CHROMA_PATH):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as e:
            raise ChromaClientError(
                "RAG dependencies are not installed. Install chromadb and "
                "sentence-transformers to enable vector retrieval."
            ) from e

        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedder: Optional[Any] = None
        self._ensure_collections()
        logger.info("ChromaDB initialized: %s", persist_dir)

    # ── Embedding ────────────────────────────────────

    @property
    def embedder(self) -> Any:
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ChromaClientError(
                    "sentence-transformers is required to generate embeddings"
                ) from e
            logger.info("Loading embedding model: %s ...", EMBED_MODEL_NAME)
            self._embedder = SentenceTransformer(EMBED_MODEL_NAME)
        return self._embedder

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        embeddings = self.embedder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        return self.embed([text])[0]

    # ── Collections ──────────────────────────────────

    def _ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = {c.name for c in self._client.list_collections()}
        if COLLECTION_JDS not in existing:
            self._client.create_collection(
                name=COLLECTION_JDS,
                metadata={"description": "Job description embeddings"},
            )
        if COLLECTION_SUGGESTIONS not in existing:
            self._client.create_collection(
                name=COLLECTION_SUGGESTIONS,
                metadata={"description": "Accepted suggestion embeddings"},
            )

    @property
    def jds(self):
        return self._client.get_collection(COLLECTION_JDS)

    @property
    def suggestions(self):
        return self._client.get_collection(COLLECTION_SUGGESTIONS)

    # ── JD Operations ────────────────────────────────

    def add_jd(self, jd_id: int, structured_json: dict) -> str:
        """
        Add a JD to the vector store.
        Returns the ChromaDB document ID.
        """
        # Build a rich searchable text from structured fields
        text = _jd_to_text(structured_json)
        embedding = self.embed_single(text)
        doc_id = f"jd-{jd_id}"

        self.jds.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "jd_id": jd_id,
                "company": (structured_json.get("company") or ""),
                "position": (structured_json.get("position") or ""),
                "level": (structured_json.get("level") or ""),
                "skills": ", ".join(structured_json.get("required_skills") or []),
            }],
        )
        logger.info("Added JD to ChromaDB: jd_id=%d", jd_id)
        return doc_id

    def search_similar_jds(
        self,
        structured_json: dict,
        n_results: int = 3,
    ) -> list[dict]:
        """
        Find similar JDs by embedding the new JD and querying ChromaDB.
        Returns list of {jd_id, company, position, similarity, ...}
        """
        text = _jd_to_text(structured_json)
        embedding = self.embed_single(text)

        try:
            results = self.jds.query(
                query_embeddings=[embedding],
                n_results=n_results,
            )
        except Exception as e:
            logger.warning("ChromaDB query failed (may be empty): %s", e)
            return []

        matches = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][i] if results["distances"] else 0
                sim = max(0.0, 1.0 - dist)  # cosine distance → similarity
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                matches.append({
                    "chroma_id": doc_id,
                    "jd_id": meta.get("jd_id"),
                    "company": meta.get("company", ""),
                    "position": meta.get("position", ""),
                    "skills": meta.get("skills", ""),
                    "similarity": round(sim, 3),
                })

        return matches

    # ── Suggestion Operations ────────────────────────

    def add_accepted_suggestion(
        self,
        suggestion_text: str,
        match_id: int,
        category: str,
        jd_id: int,
    ) -> str:
        """Store an accepted suggestion for future reuse."""
        embedding = self.embed_single(suggestion_text)
        doc_id = f"sug-{uuid.uuid4().hex[:8]}"

        self.suggestions.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[suggestion_text],
            metadatas=[{
                "match_id": match_id,
                "category": category,
                "jd_id": jd_id,
            }],
        )
        return doc_id

    def search_similar_suggestions(
        self,
        jd_text: str,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Search for historically effective suggestions given a JD.
        """
        embedding = self.embed_single(jd_text)

        try:
            results = self.suggestions.query(
                query_embeddings=[embedding],
                n_results=n_results,
            )
        except Exception:
            return []

        matches = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][i] if results["distances"] else 0
                sim = max(0.0, 1.0 - dist)
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                doc = results["documents"][0][i] if results["documents"] else ""
                matches.append({
                    "suggestion_text": doc,
                    "category": meta.get("category", ""),
                    "jd_id": meta.get("jd_id"),
                    "similarity": round(sim, 3),
                })

        return matches

    # ── Count ─────────────────────────────────────────

    def count_jds(self) -> int:
        try:
            return self.jds.count()
        except Exception:
            return 0

    def count_suggestions(self) -> int:
        try:
            return self.suggestions.count()
        except Exception:
            return 0


# ── Singleton ────────────────────────────────────────

_chroma_client: Optional[ChromaClient] = None


def get_chroma() -> ChromaClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaClient()
    return _chroma_client


def reset_chroma() -> None:
    global _chroma_client
    _chroma_client = None


# ── Helpers ──────────────────────────────────────────

def _jd_to_text(jd: dict) -> str:
    """Convert structured JD to a searchable text string."""
    parts = []
    for key in ("company", "position", "team", "location", "education"):
        if jd.get(key):
            parts.append(str(jd[key]))
    for key in ("required_skills", "preferred_skills", "responsibilities", "soft_skills", "culture_signals"):
        vals = jd.get(key, [])
        if vals:
            parts.append(" ".join(vals))
    return " | ".join(parts)
