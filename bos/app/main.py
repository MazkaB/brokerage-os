"""
BOS FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Serves:
  * /api/*            - JSON API (see app/api/*.py)
  * /                 - web chat UI
  * /admin            - admin dashboard
  * /openapi.json     - OpenAPI schema
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .api.admin import router as admin_router
from .api.approval import router as approval_router
from .api.chat import router as chat_router
from .api.ingest import router as ingest_router
from .api.slack import router as slack_router
from .api.voice import router as voice_router
from .audit import get_audit
from .config import get_settings
from .logging_setup import configure_logging
from .memory.long_term import get_long_term_memory
from .memory.pruning import start_background_loop as start_pruning_loop
from .otel import setup_otel

log = logging.getLogger("bos.main")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP rate limiter for POST endpoints.

    Buckets: 60 req/min per IP for read endpoints (admin, approvals),
    20 req/min per IP for /api/chat (the expensive LLM-driven path).
    """

    def __init__(self, app, chat_limit: int = 20, default_limit: int = 60):
        super().__init__(app)
        self.chat_limit = chat_limit
        self.default_limit = default_limit
        self.buckets: dict = defaultdict(list)

    def _prune(self, key: str, now: float, window: int = 60) -> list:
        self.buckets[key] = [t for t in self.buckets[key] if now - t < window]
        return self.buckets[key]

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        path = request.url.path
        limit = self.chat_limit if path == "/api/chat" else self.default_limit
        key = f"{client}:{path}"
        now = time.time()
        hits = self._prune(key, now)
        if len(hits) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"rate limit exceeded ({limit}/min for {path})"},
            )
        hits.append(now)
        return await call_next(request)


async def _approval_expiry_loop():
    """Background task that expires stale approval records every 60 seconds.

    Implements PRD HITL requirement: "if no human response in N minutes,
    graph continues with default policy + log event".
    """
    audit = get_audit()
    while True:
        try:
            n = audit.expire_stale_approvals()
            if n:
                log.info("Expired %d stale approval(s)", n)
        except Exception as e:
            log.warning("approval expiry loop error: %s", e)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    s = get_settings()
    log.info("BOS starting up (db=%s, chroma=%s)", s.db_path, s.chroma_path)

    # LangSmith tracing - only enabled when explicitly turned on.
    if s.langsmith_tracing:
        import os
        os.environ["LANGSMITH_TRACING"] = "true"
        # LANGSMITH_API_KEY / LANGSMITH_PROJECT must be set by the operator.
        log.info("LangSmith tracing ENABLED (project=%s)",
                 os.environ.get("LANGSMITH_PROJECT", "default"))
    else:
        log.info("LangSmith tracing disabled (set LANGSMITH_TRACING=true to enable)")

    # Initialize singletons (forces schema creation)
    get_audit()
    get_long_term_memory()
    # Seed the demo advisor profile if not present
    ltm = get_long_term_memory()
    if not ltm.get_profile("u_advisor"):
        ltm.upsert_profile({
            "user_id": "u_advisor",
            "username": "advisor",
            "role": "advisor",
            "display_name": "Demo Advisor",
            "risk_tolerance": "moderate",
            "preferred_markets": ["US-EQ"],
            "kyc_status": "verified",
            "account_type": "Individual",
        })
    # Start background scheduler for approval expiry
    expiry_task = asyncio.create_task(_approval_expiry_loop())
    log.info("Background approval-expiry task started")

    # Start memory retention / pruning loop (Phase 2)
    try:
        pruning_task = start_pruning_loop()
        log.info("Background memory-pruning task started")
    except Exception as e:
        log.warning("Pruning loop start failed: %s", e)
        pruning_task = None

    yield
    expiry_task.cancel()
    if pruning_task and not pruning_task.done():
        pruning_task.cancel()
    log.info("BOS shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Brokerage OS",
        version="1.0.0",
        description=(
            "Hierarchical Multi-Agent Brokerage Operating System (Phase 1). "
            "LangGraph-based supervisor/manager/worker orchestration with "
            "human-in-the-loop approvals, RAG over local Chroma, and Vertex AI."
        ),
        lifespan=lifespan,
    )

    # Rate limiter (custom middleware - simpler than slowapi for our needs)
    app.add_middleware(RateLimitMiddleware)

    # OpenTelemetry instrumentation (opt-in via env)
    try:
        setup_otel(app)
    except Exception as e:
        log.warning("OTel setup failed: %s", e)

    app.add_middleware(
        CORSMiddleware,
        # FIX audit C4: CORS `*` + credentials is an insecure combination.
        # API-key auth does not use cookies, so credentials are unnecessary.
        # Restrict to localhost dev origins; configurable via env in Phase 2.
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    # API routers
    app.include_router(chat_router)
    app.include_router(approval_router)
    app.include_router(admin_router)
    app.include_router(ingest_router)
    app.include_router(slack_router)
    app.include_router(voice_router)

    # Static assets (web/ folder)
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        path = web_dir / "index.html"
        if path.exists():
            return FileResponse(path)
        return HTMLResponse("<h1>Brokerage OS</h1><p>web/ folder not found</p>")

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page():
        path = web_dir / "admin.html"
        if path.exists():
            return FileResponse(path)
        return HTMLResponse("<h1>BOS Admin</h1><p>web/admin.html not found</p>")

    @app.get("/voice", response_class=HTMLResponse, include_in_schema=False)
    async def voice_page():
        path = web_dir / "voice.html"
        if path.exists():
            return FileResponse(path)
        return HTMLResponse("<h1>BOS Voice</h1><p>web/voice.html not found</p>")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        log_level=s.log_level.lower(),
        reload=False,
    )
