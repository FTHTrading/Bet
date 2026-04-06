"""
RAG Retriever
=============
High-level interface for context-augmented AI queries.
Assembles relevant context from all collections and formats
it as a structured prompt injection for the LLM brain.
"""
from __future__ import annotations
from typing import Optional
from .embeddings import get_store


class KalishiRetriever:
    """
    Main RAG retriever.  Given a query string, pulls relevant context
    from all knowledge bases and formats it for LLM consumption.
    """

    def __init__(self):
        self._store = get_store()

    def retrieve(
        self,
        query: str,
        collections: Optional[list[str]] = None,
        n_per_collection: int = 3,
        min_relevance: float = 0.30,
    ) -> str:
        """
        Retrieve and format context for a query.
        Returns a formatted string ready for LLM injection.
        """
        if not self._store.ready:
            return ""

        results = self._store.multi_query(
            query,
            collections=collections,
            n_per_collection=n_per_collection,
        )

        sections: list[str] = []

        label_map = {
            "knowledge":    "Betting Knowledge",
            "bet_history":  "Historical Bets",
            "game_intel":   "Game Intelligence",
            "market_moves": "Market Moves / Sharp Action",
            "daily_picks":  "Previous AI Picks",
        }

        for col, hits in results.items():
            hits = [h for h in hits if h["relevance"] >= min_relevance]
            if not hits:
                continue
            label = label_map.get(col, col.replace("_", " ").title())
            items = "\n".join(f"  • {h['text']}" for h in hits)
            sections.append(f"[{label}]\n{items}")

        if not sections:
            return ""

        return "RELEVANT CONTEXT FROM KNOWLEDGE BASE:\n" + "\n\n".join(sections)

    def retrieve_for_pick(self, sport: str, event: str, market: str) -> str:
        """Specialized retrieval for pick generation."""
        query = f"{sport} betting strategy {event} {market} edge analysis"
        return self.retrieve(
            query,
            collections=["knowledge", "game_intel", "market_moves", "daily_picks"],
            n_per_collection=4,
        )

    def retrieve_for_chat(self, user_message: str) -> str:
        """Retrieve context for an arbitrary user chat message."""
        return self.retrieve(
            user_message,
            n_per_collection=3,
            min_relevance=0.25,
        )

    def retrieve_similar_bets(self, sport: str, market: str, edge_pct: float) -> str:
        """Find historically similar bets for context."""
        query = f"{sport} {market} edge {edge_pct:.1f}% similar bets historical"
        return self.retrieve(
            query,
            collections=["bet_history", "daily_picks"],
            n_per_collection=5,
        )
