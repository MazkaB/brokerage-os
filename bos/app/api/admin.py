"""
Admin API.

Exposes read-only data for the admin dashboard:
  * /api/admin/health          - service health + Gemini ping
  * /api/admin/workflows       - recent workflows
  * /api/admin/audit           - recent audit events
  * /api/admin/agents          - agent registry & topology
  * /api/admin/clients         - CRM clients
  * /api/admin/documents       - generated documents
  * /api/admin/events          - calendar events
  * /api/admin/users           - demo user directory
  * /api/admin/profiles        - long-term user profiles
  * /api/admin/kb/stats        - KB stats
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..audit import get_audit
from ..llm import ping_gemini
from ..memory.long_term import get_long_term_memory
from ..memory.organizational import get_organizational_memory
from ..metrics import get_metrics
from ..security import list_demo_users
from ..tools.calendar import cal_list_events
from ..tools.crm import crm_list_clients
from ..tools.documents import doc_list
from .deps import require_api_key

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health")
def health(_=Depends(require_api_key)):
    return {
        "status": "ok",
        "gemini": ping_gemini(),
        "kb": get_organizational_memory().stats(),
    }


@router.get("/workflows")
def workflows(status: str | None = None, _=Depends(require_api_key)):
    return {"workflows": get_audit().list_workflows(status=status)}


@router.get("/audit")
def audit_events(
    thread_id: str | None = None,
    agent: str | None = None,
    limit: int = Query(default=100, le=500),
    _=Depends(require_api_key),
):
    return {"events": get_audit().list_events(thread_id=thread_id, agent=agent, limit=limit)}


@router.get("/agents")
def agents(_=Depends(require_api_key)):
    return {
        "topology": {
            "ceo": ["operations", "compliance", "portfolio", "clarify", "general"],
            "operations": ["crm_worker", "document_worker", "calendar_worker"],
            "compliance": ["compliance_worker", "retrieval_worker"],
            "portfolio": ["research_worker", "retrieval_worker"],
        },
        "workers": [
            "crm_worker", "document_worker", "compliance_worker",
            "research_worker", "calendar_worker", "retrieval_worker",
        ],
        "managers": ["operations", "compliance", "portfolio"],
    }


@router.get("/clients")
def clients(_=Depends(require_api_key)):
    r = crm_list_clients()
    return {"clients": r.data.get("clients", [])}


@router.get("/documents")
def documents(_=Depends(require_api_key)):
    r = doc_list()
    return {"documents": r.data.get("documents", [])}


@router.get("/events")
def events(_=Depends(require_api_key)):
    r = cal_list_events()
    return {"events": r.data.get("events", [])}


@router.get("/users")
def users(_=Depends(require_api_key)):
    return {"users": list_demo_users()}


@router.get("/profiles")
def profiles(_=Depends(require_api_key)):
    return {"profiles": get_long_term_memory().list_profiles()}


@router.get("/kb/stats")
def kb_stats(_=Depends(require_api_key)):
    return get_organizational_memory().stats()


@router.get("/metrics")
def metrics_summary(_=Depends(require_api_key)):
    """LLM token / cost / latency metrics for the dashboard charts."""
    m = get_metrics()
    return {
        "last_1h": m.summary(since_seconds=3600),
        "last_24h": m.summary(since_seconds=86400),
        "last_7d": m.summary(since_seconds=7 * 86400),
        "timeseries_1h": m.timeseries(since_seconds=3600, bucket_seconds=300),
    }
