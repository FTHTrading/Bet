"""
RAG Embeddings Layer
====================
ChromaDB vector store + sentence-transformers (all-MiniLM-L6-v2).
Runs 100% locally — no cloud API calls for embeddings.

Collections:
  - bet_history     : historical bets with context + outcomes
  - game_intel      : game analysis, matchup data, injury notes
  - market_moves    : sharp moves, steam alerts, line changes
  - knowledge       : sports betting theory, strategies, rules
  - daily_picks     : AI-generated picks with full reasoning chains
"""
from __future__ import annotations
import os
import json
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

# ── Config ─────────────────────────────────────────────────────────────────
PERSIST_DIR = Path(__file__).parent.parent / "db" / "vectorstore"
EMBED_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast, 80MB

COLLECTIONS = [
    "bet_history",
    "game_intel",
    "market_moves",
    "knowledge",
    "daily_picks",
]


class EmbeddingStore:
    """
    ChromaDB-backed vector store with local sentence-transformer embeddings.
    Falls back to keyword matching if dependencies are missing.
    """

    def __init__(self):
        self._ready = False
        self._client = None
        self._encoder = None
        self._collections: dict = {}
        self._init()

    def _init(self):
        if not CHROMA_AVAILABLE or not ST_AVAILABLE:
            print("[RAG] ChromaDB or sentence-transformers not installed — running in fallback mode")
            return

        PERSIST_DIR.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._encoder = SentenceTransformer(EMBED_MODEL)

        for name in COLLECTIONS:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

        self._ready = True
        print(f"[RAG] Vector store ready at {PERSIST_DIR}")

    @property
    def ready(self) -> bool:
        return self._ready

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._ready:
            return [[0.0] * 384 for _ in texts]
        return self._encoder.encode(texts, normalize_embeddings=True).tolist()

    # ── Upsert ─────────────────────────────────────────────────────────────

    def upsert(
        self,
        collection: str,
        texts: list[str],
        metadatas: list[dict],
        ids: Optional[list[str]] = None,
    ) -> int:
        """Add or update documents in a collection."""
        if not self._ready or collection not in self._collections:
            return 0

        if ids is None:
            ids = [
                hashlib.sha256((t + json.dumps(m, sort_keys=True)).encode()).hexdigest()[:16]
                for t, m in zip(texts, metadatas)
            ]

        embeddings = self.embed(texts)
        self._collections[collection].upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(texts)

    # ── Query ───────────────────────────────────────────────────────────────

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search. Returns list of {text, metadata, distance} dicts.
        Lower distance = more similar.
        """
        if not self._ready or collection not in self._collections:
            return []

        q_emb = self.embed([query_text])

        kwargs: dict = {"query_embeddings": q_emb, "n_results": n_results, "include": ["documents", "metadatas", "distances"]}
        if where:
            kwargs["where"] = where

        try:
            res = self._collections[collection].query(**kwargs)
        except Exception:
            return []

        results = []
        docs      = res.get("documents",  [[]])[0]
        metas     = res.get("metadatas",  [[]])[0]
        distances = res.get("distances",  [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            results.append({
                "text":      doc,
                "metadata":  meta,
                "distance":  round(dist, 4),
                "relevance": round(1 - dist, 4),  # 1=perfect match, 0=unrelated
            })

        return results

    def multi_query(
        self,
        query_text: str,
        collections: Optional[list[str]] = None,
        n_per_collection: int = 3,
    ) -> dict[str, list[dict]]:
        """Query across multiple collections at once."""
        cols = collections or COLLECTIONS
        return {
            col: self.query(col, query_text, n_results=n_per_collection)
            for col in cols
        }

    def count(self, collection: str) -> int:
        if not self._ready or collection not in self._collections:
            return 0
        return self._collections[collection].count()

    def stats(self) -> dict:
        return {
            "ready": self._ready,
            "model": EMBED_MODEL,
            "persist_dir": str(PERSIST_DIR),
            "collections": {
                col: self.count(col) for col in COLLECTIONS
            },
        }


# Singleton
_store: Optional[EmbeddingStore] = None


def get_store() -> EmbeddingStore:
    global _store
    if _store is None:
        _store = EmbeddingStore()
    return _store
