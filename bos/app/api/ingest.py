"""
Knowledge-base ingestion API.

Endpoints:
  POST /api/ingest/text       - ingest a raw text document
  POST /api/ingest/file       - upload a .txt / .md / .pdf file
  POST /api/ingest/seed       - (re)seed the KB from /knowledge_base folder
  GET  /api/ingest/search     - test query (debug)
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..chunking import chunk_text as _chunk_text
from ..config import get_settings
from ..memory.organizational import get_organizational_memory
from ..tools.retrieval import retrieval_search
from .deps import require_api_key

log = logging.getLogger("bos.api.ingest")
router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class TextIngest(BaseModel):
    source: str
    doc_type: str = "policy"
    text: str


@router.post("/text")
def ingest_text(payload: TextIngest, _=Depends(require_api_key)):
    chunks_raw = _chunk_text(payload.text)
    chunks = [
        {"id": f"{payload.source}_{i}", "text": c, "metadata": {"position": i}}
        for i, c in enumerate(chunks_raw)
    ]
    n = get_organizational_memory().add_documents(
        chunks, source=payload.source, doc_type=payload.doc_type
    )
    return {"ingested": n, "source": payload.source}


@router.post("/file")
async def ingest_file(
    file: UploadFile = File(...),
    doc_type: str = Form("policy"),
    _: None = Depends(require_api_key),
):
    name = file.filename or "uploaded"
    suffix = Path(name).suffix.lower()

    # FIX audit H3 (partial): enforce size cap to prevent OOM via huge uploads.
    # Stream in 64KB chunks; reject if total exceeds 10MB.
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"file too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)",
            )
    raw = bytes(buf)

    text = ""
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            for page in reader.pages:
                text += page.extract_text() + "\n"
        except Exception as e:
            # FIX audit H6: do not leak internal pypdf traceback to client
            log.warning("PDF parse failed for upload '%s': %s", name, e)
            raise HTTPException(status_code=400, detail="PDF parse failed")
    elif suffix in (".txt", ".md"):
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception as e:
            log.warning("decode failed for upload '%s': %s", name, e)
            raise HTTPException(status_code=400, detail="file decode failed")
    else:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}")

    # FIX audit H3: sanitize filename for use as Chroma doc_id
    safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).stem)[:64]

    if not text.strip():
        raise HTTPException(status_code=400, detail="no extractable text")

    chunks_raw = _chunk_text(text)
    chunks = [
        # FIX audit H3: use sanitized stem + uuid suffix for doc_id to
        # prevent path traversal / ID collision attacks.
        {"id": f"{safe_stem}_{uuid.uuid4().hex[:6]}_{i}", "text": c, "metadata": {"position": i}}
        for i, c in enumerate(chunks_raw)
    ]
    n = get_organizational_memory().add_documents(chunks, source=name, doc_type=doc_type)
    return {"ingested": n, "source": name}


@router.post("/seed")
def seed_kb(_=Depends(require_api_key)):
    """Walk the /knowledge_base directory and ingest every .md / .txt / .pdf."""
    settings = get_settings()
    kb_dir = Path(settings.kb_path)
    if not kb_dir.exists():
        # FIX audit H6: do not leak absolute server path to client
        raise HTTPException(status_code=404, detail="knowledge base directory not configured")

    total = 0
    files: list[dict] = []
    for path in sorted(kb_dir.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".md", ".txt", ".pdf"):
            continue
        try:
            if suffix == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
            chunks_raw = _chunk_text(text)
            chunks = [
                {"id": f"{path.name}_{i}", "text": c, "metadata": {"position": i}}
                for i, c in enumerate(chunks_raw)
            ]
            doc_type = "policy" if "compliance" in path.name.lower() or "policy" in path.name.lower() \
                else "sop" if "sop" in path.name.lower() \
                else "knowledge"
            n = get_organizational_memory().add_documents(
                chunks, source=path.name, doc_type=doc_type
            )
            total += n
            files.append({"file": path.name, "chunks": n, "doc_type": doc_type})
        except Exception as e:
            files.append({"file": path.name, "error": str(e)})
    return {"ingested_total": total, "files": files}


@router.get("/search")
def search(
    q: str = Query(..., min_length=2),
    k: int = Query(default=5, le=20),
    doc_type: Optional[str] = None,
    _: None = Depends(require_api_key),
):
    r = retrieval_search(q, k=k, doc_type=doc_type)
    return r.to_dict()
