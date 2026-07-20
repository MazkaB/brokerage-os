"""
Ingest the knowledge_base/ folder into the ChromaDB vector store.

Usage:
    python scripts/ingest_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.logging_setup import configure_logging
from app.memory.organizational import get_organizational_memory
from app.api.ingest import _chunk_text

configure_logging()


def main() -> None:
    s = get_settings()
    kb_dir = Path(s.kb_path)
    if not kb_dir.exists():
        print(f"KB directory not found: {kb_dir}")
        return

    om = get_organizational_memory()
    total = 0
    for path in sorted(kb_dir.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
            except Exception as e:
                print(f"  ! failed to parse {path.name}: {e}")
                continue
        elif suffix in (".md", ".txt"):
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            continue

        chunks = _chunk_text(text)
        payload = [
            {"id": f"{path.name}_{i}", "text": c, "metadata": {"position": i}}
            for i, c in enumerate(chunks)
        ]
        doc_type = "policy" if "compliance" in path.name.lower() \
            else "sop" if "sop" in path.name.lower() \
            else "knowledge"
        n = om.add_documents(payload, source=path.name, doc_type=doc_type)
        total += n
        print(f"  ingested {n:>3} chunks from {path.name}  ({doc_type})")

    stats = om.stats()
    print(f"\nTotal ingested this run: {total}")
    print(f"Collection '{stats.get('name')}' now has {stats.get('chunks')} chunks.")


if __name__ == "__main__":
    main()
