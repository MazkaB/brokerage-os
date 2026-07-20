"""
Approval API (HITL).

Endpoints:
  GET    /api/approvals                  - list approvals (optional ?status=)
  GET    /api/approvals/{id}             - get one approval
  POST   /api/approvals/{id}/decision    - approve / reject  (RBAC enforced)

SECURITY (audit C3): every decision endpoint now checks that the caller's
role has the appropriate permission (`approval.approve` or `approval.reject`).
The `decided_by` field is sourced from the authenticated user context, NOT
trusted from the request payload, so the audit trail cannot be forged.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..security import AuthContext
from .deps import require_api_key

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    # `decided_by` is intentionally NOT accepted from the client anymore.
    # It is sourced from the authenticated user context in the handler.
    note: Optional[str] = None


@router.get("")
def list_approvals(status: Optional[str] = None, ctx: AuthContext = Depends(require_api_key)):
    if not ctx.has_permission("audit.read") and not ctx.has_permission("approval.approve"):
        raise HTTPException(status_code=403, detail="insufficient role to view approvals")
    return {"approvals": get_audit().list_approvals(status=status)}


@router.get("/{approval_id}")
def get_approval(approval_id: str, ctx: AuthContext = Depends(require_api_key)):
    if not ctx.has_permission("audit.read") and not ctx.has_permission("approval.approve"):
        raise HTTPException(status_code=403, detail="insufficient role to view approvals")
    ap = get_audit().get_approval(approval_id)
    if not ap:
        raise HTTPException(status_code=404, detail="approval not found")
    return ap


@router.post("/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    payload: DecisionRequest,
    ctx: AuthContext = Depends(require_api_key),
):
    # RBAC enforcement (fixes audit C3)
    required_perm = "approval.approve" if payload.decision == "approved" else "approval.reject"
    if not ctx.has_permission(required_perm):
        raise HTTPException(
            status_code=403,
            detail=f"role '{ctx.role}' lacks '{required_perm}' permission",
        )
    # Trust ctx.user_id, NOT the client-supplied identity (fixes audit-trail forgery)
    result = get_audit().decide_approval(
        approval_id, payload.decision, ctx.user_id, payload.note
    )
    if not result:
        raise HTTPException(status_code=404, detail="approval not found")
    return result
