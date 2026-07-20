"""
Worker agents - the leaf-level specialists.

Each worker returns a `WorkerResult` dict that managers/CEO can merge.
Workers never talk directly to users (PRD section 9).

Workers in Phase 1:
  * CRM Worker        - client data ops
  * Document Worker   - form/document preparation
  * Compliance Worker - KYC/AML/policy validation
  * Research Worker   - market data analysis
  * Calendar Worker   - scheduling
  * Retrieval Worker  - RAG-backed org knowledge lookup
"""
from .crm_worker import crm_worker_node
from .document_worker import document_worker_node
from .compliance_worker import compliance_worker_node
from .research_worker import research_worker_node
from .calendar_worker import calendar_worker_node
from .retrieval_worker import retrieval_worker_node

WORKER_REGISTRY = {
    "crm_worker": crm_worker_node,
    "document_worker": document_worker_node,
    "compliance_worker": compliance_worker_node,
    "research_worker": research_worker_node,
    "calendar_worker": calendar_worker_node,
    "retrieval_worker": retrieval_worker_node,
}

__all__ = [
    "crm_worker_node", "document_worker_node", "compliance_worker_node",
    "research_worker_node", "calendar_worker_node", "retrieval_worker_node",
    "WORKER_REGISTRY",
]
