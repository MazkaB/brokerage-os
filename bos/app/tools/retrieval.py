"""
Retrieval tool - RAG-backed real semantic search (Phase 1).

This is the one tool that is fully functional end-to-end in Phase 1,
backed by ChromaDB and Gemini embeddings (both local or local+API).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..memory.organizational import get_organizational_memory
from .base import ToolResult

log = logging.getLogger("bos.tools.retrieval")


class RetrievalTool:
    def search(self, query: str, k: int = 5, doc_type: Optional[str] = None) -> ToolResult:
        mem = get_organizational_memory()
        results = mem.search(query, k=k, doc_type=doc_type)
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "results": results,
                "count": len(results),
            },
            tools_used=["retrieval.search"],
            citations=[r["source"] for r in results if r.get("source")],
        )


_singleton: Optional[RetrievalTool] = None


def _inst() -> RetrievalTool:
    global _singleton
    if _singleton is None:
        _singleton = RetrievalTool()
    return _singleton


def retrieval_search(query: str, k: int = 5, doc_type: Optional[str] = None) -> ToolResult:
    return _inst().search(query, k=k, doc_type=doc_type)
