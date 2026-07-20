"""
Document tool - in-memory template-based document/form filler (Phase 1).

Stands in for DocuSign / PDF Parser / OCR (Phase 2 integrations).
Generates text/PDF placeholders and stores them on disk for retrieval.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import get_settings
from .base import ToolResult

log = logging.getLogger("bos.tools.docs")


# Pre-defined form templates (Phase 1 placeholder). Real PDFs in Phase 2.
_TEMPLATES: Dict[str, str] = {
    "account_opening": (
        "BROKERAGE ACCOUNT OPENING FORM\n"
        "===============================\n"
        "Client Name     : {full_name}\n"
        "Account Type    : {account_type}\n"
        "Risk Profile    : {risk_tolerance}\n"
        "Email           : {email}\n"
        "Phone           : {phone}\n"
        "KYC Status      : {kyc_status}\n"
        "Date            : {date}\n\n"
        "Declaration     : I certify the information above is accurate.\n"
        "Signature       : ______________________\n"
    ),
    "account_transfer": (
        "ACCOUNT TRANSFER FORM (ACATS)\n"
        "=============================\n"
        "Client Name      : {full_name}\n"
        "From Institution : {from_institution}\n"
        "Account Number   : {from_account}\n"
        "Target Account   : {target_account}\n"
        "Assets to Move   : {assets}\n"
        "Date             : {date}\n\n"
        "Signature        : ______________________\n"
    ),
    "kyc_checklist": (
        "KYC VERIFICATION CHECKLIST\n"
        "==========================\n"
        "Client ID       : {client_id}\n"
        "[ ] Government ID copy attached\n"
        "[ ] Address proof attached\n"
        "[ ] SSN/Tax ID verified\n"
        "[ ] Sanctions screening passed\n"
        "[ ] Risk profile assessed\n"
        "Reviewed by     : {reviewer}\n"
        "Date            : {date}\n"
    ),
    "compliance_review": (
        "COMPLIANCE REVIEW MEMO\n"
        "======================\n"
        "Case ID     : {case_id}\n"
        "Intent      : {intent}\n"
        "Client      : {client}\n"
        "Findings    : {findings}\n"
        "Decision    : {decision}\n"
        "Reviewer    : {reviewer}\n"
        "Date        : {date}\n"
    ),
}


class DocumentTool:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.docs_dir = Path(self.settings.project_root) / "app" / "data" / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._index: List[Dict[str, Any]] = self._load_index()

    def _index_path(self) -> Path:
        return self.docs_dir / "_index.json"

    def _load_index(self) -> List[Dict[str, Any]]:
        p = self._index_path()
        if p.exists():
            import json
            with p.open() as f:
                return json.load(f)
        return []

    def _save_index(self) -> None:
        import json
        with self._index_path().open("w") as f:
            json.dump(self._index, f, indent=2)

    # ------------------------------------------------------------------
    def prepare_pdf(self, template: str, fields: Dict[str, Any]) -> ToolResult:
        if template not in _TEMPLATES:
            return ToolResult(ok=False, error=f"unknown template '{template}'")
        # Fill safe fields, leave missing ones blank
        merged = {**fields}
        merged.setdefault("date", time.strftime("%Y-%m-%d"))
        try:
            text = _TEMPLATES[template].format(**{k: v for k, v in merged.items()})
        except KeyError as e:
            return ToolResult(ok=False, error=f"missing field {e}")
        doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        path = self.docs_dir / f"{doc_id}.txt"  # text-only in Phase 1; PDF lib in Phase 2
        path.write_text(text, encoding="utf-8")
        with self._lock:
            self._index.append({
                "doc_id": doc_id,
                "template": template,
                "path": str(path),
                "created_at": time.time(),
                "fields": merged,
            })
            self._save_index()
        log.info("document prepared: %s (%s)", doc_id, template)
        return ToolResult(
            ok=True,
            data={"doc_id": doc_id, "path": str(path), "preview": text[:500]},
            tools_used=["document.prepare_pdf"],
        )

    def fill_form(self, doc_id: str, fields: Dict[str, Any]) -> ToolResult:
        with self._lock:
            entry = next((e for e in self._index if e["doc_id"] == doc_id), None)
        if not entry:
            return ToolResult(ok=False, error=f"document {doc_id} not found")
        return self.prepare_pdf(entry["template"], {**entry["fields"], **fields})

    def extract_info(self, doc_id: str) -> ToolResult:
        with self._lock:
            entry = next((e for e in self._index if e["doc_id"] == doc_id), None)
        if not entry:
            return ToolResult(ok=False, error=f"document {doc_id} not found")
        return ToolResult(
            ok=True,
            data={"fields": entry["fields"], "template": entry["template"]},
            tools_used=["document.extract_info"],
        )

    def list(self, limit: int = 50) -> ToolResult:
        return ToolResult(
            ok=True,
            data={"documents": self._index[-limit:]},
            tools_used=["document.list"],
        )


_singleton: Optional[DocumentTool] = None


def _inst() -> DocumentTool:
    global _singleton
    if _singleton is None:
        _singleton = DocumentTool()
    return _singleton


def doc_prepare_pdf(template: str, fields: Dict[str, Any]) -> ToolResult:
    return _inst().prepare_pdf(template, fields)


def doc_fill_form(doc_id: str, fields: Dict[str, Any]) -> ToolResult:
    return _inst().fill_form(doc_id, fields)


def doc_extract_info(doc_id: str) -> ToolResult:
    return _inst().extract_info(doc_id)


def doc_list(limit: int = 50) -> ToolResult:
    return _inst().list(limit=limit)
