"""
Chat API.

Two transports:
  * POST /api/chat                 - one-shot JSON request/response
  * POST /api/chat/stream          - Server-Sent Events (token-like deltas)
  * WS   /api/chat/ws              - WebSocket variant for richer UIs

All three share the same underlying `run_bos_turn` helper that drives the
LangGraph and handles the HITL interrupt-resume cycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..agents.base import _trace  # noqa: F401  (re-exported for completeness)
from ..audit import get_audit
from ..config import get_settings
from ..graph import get_bos_graph
from ..memory.long_term import get_long_term_memory
from ..security import AuthContext, authenticate_user
from .deps import require_api_key

log = logging.getLogger("bos.api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    thread_id: Optional[str] = None
    # Local dashboard sends a demo username to impersonate one of the seeded
    # demo users. The `role` is looked up server-side from `_DEMO_USERS` and
    # CANNOT be overridden by the client (fixes audit C2 - privilege escalation).
    username: Optional[str] = None
    # Optional list of attachments (uploaded via /api/chat/upload first).
    # Each entry: {"doc_id": "...", "filename": "...", "ingested_chunks": N}
    attachments: Optional[list] = None


class ChatResponse(BaseModel):
    thread_id: str
    final_response: Optional[str]
    intent: Optional[str]
    manager: Optional[str]
    trace: list[str]
    worker_outputs: Dict[str, Any]
    needs_approval: bool = False
    approval: Optional[Dict[str, Any]] = None
    citations: list[str] = []


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------
def _resolve_auth(req: ChatRequest, api_ctx: AuthContext):
    """If the caller passed a demo username, impersonate that user.

    SECURITY (fixes audit C2): we no longer accept a `role` field from the
    client. `authenticate_user` looks up the role server-side from the
    configured demo directory and ignores any client-supplied role override.
    """
    if req.username:
        return authenticate_user(req.username)
    return api_ctx


def _initial_state(req: ChatRequest, ctx: AuthContext, thread_id: str) -> Dict[str, Any]:
    ltm = get_long_term_memory()
    profile = ltm.get_profile(ctx.user_id) or {}
    # If attachments were uploaded, surface them in the user message so the
    # retrieval worker can pick them up via the KB (already auto-ingested).
    attachments = req.attachments or []
    user_message = req.message
    if attachments:
        names = ", ".join(a.get("filename", "?") for a in attachments)
        user_message = f"{req.message}\n\n[User attached: {names}]"
    return {
        "thread_id": thread_id,
        "user_message": user_message,
        "messages": [HumanMessage(content=user_message)],
        "user_id": ctx.user_id,
        "username": ctx.username,
        "role": ctx.role,
        "permissions": list(ctx.permissions),
        "user_profile": profile,
    }


def run_bos_turn(req: ChatRequest, ctx: AuthContext) -> Dict[str, Any]:
    """Drive one full CEO->...->composer turn. Returns the final state.

    If the graph interrupts on `request_approval`, the returned dict will
    include `needs_approval=True` and the interrupt payload under `approval`.
    The caller can later POST /api/approval/{id}/decision and then call
    /api/chat/resume to continue.
    """
    thread_id = req.thread_id or f"t-{uuid.uuid4().hex[:10]}"
    graph = get_bos_graph()
    state = _initial_state(req, ctx, thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    result = graph.invoke(state, config=config)

    snapshot = graph.get_state(config)
    needs_approval = (
        snapshot.next
        and "request_approval" in snapshot.next
        and any(getattr(t, "interrupts", None) for t in snapshot.tasks)
    )

    approval: Optional[Dict[str, Any]] = None
    if needs_approval:
        for t in snapshot.tasks:
            for i in (getattr(t, "interrupts", None) or []):
                approval = i.value if isinstance(i.value, dict) else {"value": i.value}
                break

    return {
        "thread_id": thread_id,
        "final_response": result.get("final_response"),
        "intent": result.get("intent"),
        "manager": result.get("manager"),
        "trace": result.get("trace") or [],
        "worker_outputs": result.get("worker_outputs") or {},
        "needs_approval": bool(needs_approval),
        "approval": approval,
        "citations": result.get("citations") or [],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    ctx: AuthContext = Depends(require_api_key),
):
    eff_ctx = _resolve_auth(payload, ctx)
    try:
        out = run_bos_turn(payload, eff_ctx)
    except Exception as e:
        # FIX audit H6: log full traceback server-side, return generic message
        # with correlation id to client (no internal paths / class names leaked)
        import uuid as _uuid
        corr_id = _uuid.uuid4().hex[:8]
        log.exception("workflow error [corr=%s]", corr_id)
        raise HTTPException(
            status_code=500,
            detail=f"internal workflow error (correlation_id={corr_id})",
        )
    return ChatResponse(**out)


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    ctx: AuthContext = Depends(require_api_key),
):
    """SSE stream that emits one event per significant step.

    Phase 1 streams coarse-grained events (node-entered, worker-done,
    approval-needed, final-response). Per-token streaming of the composer's
    output would require moving the composer to astream_events - planned
    for Phase 2.
    """
    eff_ctx = _resolve_auth(payload, ctx)
    queue: asyncio.Queue = asyncio.Queue()

    async def producer():
        try:
            # Run the blocking invoke in a worker thread
            loop = asyncio.get_running_loop()
            out = await loop.run_in_executor(None, run_bos_turn, payload, eff_ctx)
            await queue.put({"event": "trace", "data": json.dumps({"trace": out["trace"]})})
            await queue.put({"event": "intent", "data": json.dumps({"intent": out["intent"], "manager": out["manager"]})})
            for name, wo in out["worker_outputs"].items():
                await queue.put({"event": "worker", "data": json.dumps({"name": name, "summary": wo.get("summary"), "status": wo.get("status")})})
            if out["needs_approval"]:
                await queue.put({"event": "approval_needed", "data": json.dumps(out["approval"])})
            await queue.put({"event": "final", "data": json.dumps({
                "thread_id": out["thread_id"],
                "final_response": out["final_response"],
                "citations": out["citations"],
            })})
        except Exception as e:
            await queue.put({"event": "error", "data": json.dumps({"error": str(e)})})
        await queue.put(None)

    asyncio.create_task(producer())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# File attachment upload (auto-ingests into KB so retrieval can use it).
# Returns doc_id + chunk count; pass these back in ChatRequest.attachments.
# ---------------------------------------------------------------------------
@router.post("/chat/upload")
async def chat_upload(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_api_key),
):
    """Upload a document attached to a chat message. Auto-ingests it into the
    organizational KB so the retrieval worker can cite it in the response.
    """
    import re as _re
    import uuid as _uuid
    from pathlib import Path as _Path
    from ..chunking import chunk_text as _chunk
    from ..memory.organizational import get_organizational_memory

    name = file.filename or "uploaded"
    suffix = _Path(name).suffix.lower()
    MAX_BYTES = 10 * 1024 * 1024
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise HTTPException(413, "file too large (max 10 MB)")
    raw = bytes(buf)

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            log.warning("PDF parse failed: %s", e)
            raise HTTPException(400, "PDF parse failed")
    elif suffix in (".txt", ".md"):
        text = raw.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(400, f"unsupported file type: {suffix}")

    if not text.strip():
        raise HTTPException(400, "no extractable text")

    safe_stem = _re.sub(r"[^A-Za-z0-9._-]", "_", _Path(name).stem)[:64]
    chunks_raw = _chunk(text)
    chunks = [
        {"id": f"{safe_stem}_{_uuid.uuid4().hex[:6]}_{i}", "text": c, "metadata": {"position": i}}
        for i, c in enumerate(chunks_raw)
    ]
    n = get_organizational_memory().add_documents(chunks, source=name, doc_type="attachment")
    return {
        "doc_id": safe_stem,
        "filename": name,
        "ingested_chunks": n,
    }
# Auth via `api_key` query param; messages: {"message": "...", "username": "..."}
# Server pushes {"type": "trace"|"worker"|"final"|"approval_needed"|"error"}.
# ---------------------------------------------------------------------------
@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        # Auth handshake: first message must contain api_key
        hello = await websocket.receive_json()
        api_key = hello.get("api_key", "")
        from ..security import authenticate_api_key
        ctx = authenticate_api_key(api_key)
        if not ctx.is_authenticated:
            await websocket.send_json({"type": "error", "detail": "invalid api_key"})
            await websocket.close()
            return
        await websocket.send_json({"type": "ready"})

        while True:
            msg = await websocket.receive_json()
            text = (msg.get("message") or "").strip()
            if not text:
                continue
            req = ChatRequest(
                message=text,
                thread_id=msg.get("thread_id"),
                username=msg.get("username"),
            )
            eff_ctx = _resolve_auth(req, ctx)
            await websocket.send_json({"type": "status", "detail": "working"})
            try:
                loop = asyncio.get_running_loop()
                out = await loop.run_in_executor(None, run_bos_turn, req, eff_ctx)
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
                continue
            await websocket.send_json({"type": "trace", "trace": out["trace"]})
            await websocket.send_json({"type": "intent",
                                        "intent": out["intent"], "manager": out["manager"]})
            for name, wo in out["worker_outputs"].items():
                await websocket.send_json({"type": "worker", "name": name,
                                            "summary": wo.get("summary"),
                                            "status": wo.get("status")})
            if out["needs_approval"]:
                await websocket.send_json({"type": "approval_needed", "approval": out["approval"]})
            await websocket.send_json({
                "type": "final",
                "thread_id": out["thread_id"],
                "final_response": out["final_response"],
                "citations": out["citations"],
            })
    except WebSocketDisconnect:
        log.info("websocket client disconnected")
    except Exception as e:
        log.warning("websocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass


class ResumeRequest(BaseModel):
    thread_id: str
    decision: str  # 'approved' | 'rejected'
    # NOTE: `decided_by` is intentionally removed - sourced from ctx.user_id.
    note: Optional[str] = None


@router.post("/chat/resume", response_model=ChatResponse)
def chat_resume_endpoint(
    payload: ResumeRequest,
    ctx: AuthContext = Depends(require_api_key),
):
    """Resume a workflow that was interrupted at the approval gate.

    SECURITY (fixes audit H4): the caller must own the thread (or hold the
    `workflow.assign` permission). The decider identity is taken from the
    auth context, not from the request body.
    """
    if payload.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")

    # RBAC: approvers need approval.approve, rejecters need approval.reject
    required_perm = "approval.approve" if payload.decision == "approved" else "approval.reject"
    if not ctx.has_permission(required_perm):
        raise HTTPException(
            status_code=403,
            detail=f"role '{ctx.role}' lacks '{required_perm}' permission",
        )

    audit = get_audit()

    # Thread ownership check (fixes audit H4)
    wf = audit.get_workflow(payload.thread_id)
    if not wf:
        raise HTTPException(status_code=404, detail="thread not found")
    wf_owner = wf.get("user_id")
    if wf_owner and wf_owner != ctx.user_id and not ctx.has_permission("workflow.assign"):
        raise HTTPException(status_code=403, detail="thread not owned by caller")

    graph = get_bos_graph()
    config = {"configurable": {"thread_id": payload.thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="thread is not awaiting resume")

    # Update the audit-side approval record (if any) for consistency.
    # Identity sourced from ctx.user_id (fixes audit C3 / H6 forgery).
    pending = audit.list_approvals(status="pending")
    for ap in pending:
        if ap.get("thread_id") == payload.thread_id:
            audit.decide_approval(ap["id"], payload.decision, ctx.user_id, payload.note)
            break

    try:
        result = graph.invoke(
            Command(resume={
                "decision": payload.decision,
                "decided_by": ctx.user_id,
                "note": payload.note,
            }),
            config=config,
        )
    except Exception as e:
        import uuid as _uuid
        corr_id = _uuid.uuid4().hex[:8]
        log.exception("resume error [corr=%s]", corr_id)
        raise HTTPException(
            status_code=500,
            detail=f"internal resume error (correlation_id={corr_id})",
        )
    return ChatResponse(
        thread_id=payload.thread_id,
        final_response=result.get("final_response"),
        intent=result.get("intent"),
        manager=result.get("manager"),
        trace=result.get("trace") or [],
        worker_outputs=result.get("worker_outputs") or {},
        needs_approval=False,
        approval=result.get("approval"),
        citations=result.get("citations") or [],
    )
