"""Text chunking utilities for the RAG pipeline."""
from __future__ import annotations

from typing import List


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Simple sliding-window chunker with overlap.

    Keeps the dependency surface tiny (no external text-splitter needed)
    while giving good retrieval granularity for Phase 1.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
        if i + chunk_size >= len(text):
            break
        i += chunk_size - overlap
    return chunks
