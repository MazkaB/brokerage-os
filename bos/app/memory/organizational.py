"""
Organizational memory: RAG over local policy / SOP / knowledge docs.

Uses ChromaDB (file-based, fully local) and Gemini embeddings.
No external vector DB service is required.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..llm import get_embeddings

log = logging.getLogger("bos.memory.org")

COLLECTION = "bos_kb"


class OrganizationalMemory:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.chroma_path = Path(self.settings.chroma_path)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._client = None
        self._collection = None

    # ------------------------------------------------------------------
    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        with self._lock:
            if self._collection is None:
                import chromadb
                # Use PersistentClient for local file storage. No server required.
                self._client = chromadb.PersistentClient(path=str(self.chroma_path))
                try:
                    self._collection = self._client.get_or_create_collection(
                        name=COLLECTION,
                        metadata={"hnsw:space": "cosine"},
                    )
                except Exception as e:
                    log.error("Failed to create chroma collection: %s", e)
                    raise
        return self._collection

    # ------------------------------------------------------------------
    def add_documents(
        self,
        chunks: List[Dict[str, Any]],
        *,
        source: str,
        doc_type: str = "policy",
    ) -> int:
        """Add pre-chunked text documents to the KB.

        Each chunk: {"id": str, "text": str, "metadata": dict}
        """
        if not chunks:
            return 0
        coll = self._ensure_collection()
        embeddings_client = get_embeddings()

        texts = [c["text"] for c in chunks]
        embs = embeddings_client.embed_documents(texts)

        ids = [c.get("id") or f"{source}_{i}" for i, c in enumerate(chunks)]
        metadatas = [
            {**(c.get("metadata") or {}), "source": source, "doc_type": doc_type}
            for c in chunks
        ]
        with self._lock:
            coll.upsert(ids=ids, embeddings=embs, documents=texts, metadatas=metadatas)
        log.info("Ingested %d chunks from %s", len(chunks), source)
        return len(chunks)

    def search(
        self,
        query: str,
        k: int = 5,
        doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over the organizational KB."""
        try:
            coll = self._ensure_collection()
            emb = get_embeddings().embed_query(query)
            where = {"doc_type": doc_type} if doc_type else None
            res = coll.query(query_embeddings=[emb], n_results=k, where=where)
            out = []
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                out.append({
                    "text": doc,
                    "source": meta.get("source"),
                    "doc_type": meta.get("doc_type"),
                    "metadata": meta,
                    "score": 1.0 - float(dist),  # cosine distance -> similarity
                })
            return out
        except Exception as e:
            log.warning("KB search failed: %s", e)
            return []

    def stats(self) -> Dict[str, Any]:
        try:
            coll = self._ensure_collection()
            return {"chunks": coll.count(), "name": coll.name}
        except Exception as e:
            return {"error": str(e)}


_singleton: Optional[OrganizationalMemory] = None


def get_organizational_memory() -> OrganizationalMemory:
    global _singleton
    if _singleton is None:
        _singleton = OrganizationalMemory()
    return _singleton
