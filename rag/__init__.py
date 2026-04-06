"""
KALISHI EDGE — RAG (Retrieval-Augmented Generation) System
==========================================================
Local vector store backed by ChromaDB + sentence-transformers.
No cloud calls, no latency, no cost per query.
"""
from .retriever import KalishiRetriever
from .knowledge_base import KnowledgeBase

__all__ = ["KalishiRetriever", "KnowledgeBase"]
