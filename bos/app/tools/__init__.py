"""
Tool package.

Phase 1 implements all tools as in-process Python functions backed by
SQLite (CRM), in-memory templates (Documents), in-memory queues
(Calendar), static rule sets (Compliance), and a mock market-data feed
(Research). Retrieval is RAG-backed and real (Chroma + Gemini embeddings).

Each tool follows a uniform signature:
   def tool_name(*, user_id, **kwargs) -> ToolResult
"""
from .crm import (
    CRMTool, crm_get_client, crm_create_client, crm_update_client,
    crm_record_conversation, crm_list_clients,
)
from .documents import (
    DocumentTool, doc_prepare_pdf, doc_fill_form, doc_extract_info, doc_list,
)
from .calendar import (
    CalendarTool, cal_schedule, cal_list_events, cal_reminder,
)
from .compliance import (
    ComplianceTool, comp_run_kyc, comp_run_aml, comp_validate_policy,
)
from .research import (
    ResearchTool, research_market_news, research_security, research_compare_funds,
)
from .retrieval import RetrievalTool, retrieval_search

__all__ = [
    # CRM
    "CRMTool", "crm_get_client", "crm_create_client", "crm_update_client",
    "crm_record_conversation", "crm_list_clients",
    # Documents
    "DocumentTool", "doc_prepare_pdf", "doc_fill_form", "doc_extract_info", "doc_list",
    # Calendar
    "CalendarTool", "cal_schedule", "cal_list_events", "cal_reminder",
    # Compliance
    "ComplianceTool", "comp_run_kyc", "comp_run_aml", "comp_validate_policy",
    # Research
    "ResearchTool", "research_market_news", "research_security", "research_compare_funds",
    # Retrieval
    "RetrievalTool", "retrieval_search",
]
