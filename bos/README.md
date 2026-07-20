# Brokerage Operating System (BOS) — Phase 1

A hierarchical, multi-agent brokerage operations platform built on **LangGraph**,
**Gemini**, and a fully **local-first** storage stack.

> Implements the PRD `prd.md` (Hierarchical Multi-Agent Brokerage OS, Phase 1).
> All resources run locally except the Gemini API (LLM + embeddings).

---

## ✨ What's inside

| Area                        | Implementation                                                                 |
| --------------------------- | ----------------------------------------------------------------------------- |
| **Orchestration**           | LangGraph `StateGraph` — CEO → Manager → Worker, conditional routing, retries |
| **Agents**                  | 1 CEO + 3 Managers (Operations / Compliance / Portfolio) + 6 Workers          |
| **LLM**                     | Google Gemini (`gemini-2.5-flash`) via `langchain-google-genai`               |
| **Embeddings**              | `gemini-embedding-001` (768-dim)                                              |
| **Short-term memory**       | LangGraph `SqliteSaver` checkpointer (per-`thread_id`)                        |
| **Long-term memory**        | SQLite-backed `user_profiles` + `user_facts`                                  |
| **Organizational memory**   | ChromaDB (file-based, local) — RAG with citation support                      |
| **HITL approvals**          | LangGraph `interrupt()` + audit-persisted approval records + resume via API   |
| **Messaging gateway**       | FastAPI REST + Server-Sent Events streaming + WebSocket-ready                 |
| **Audit trail**             | Every node event persisted with timestamp, agent, tools, docs, approval       |
| **Security foundation**     | API-key auth, RBAC (5 roles), PII detection + masking, secrets redaction      |
| **Tool policy matrix**      | Per-agent allow/deny lists (PRD §12 / §14)                                    |
| **Failure handling**        | Rule-based fallback classifier + planner when LLM is unavailable              |
| **Admin dashboard**         | Live KPIs, approval queue, audit trail, workflows, CRM, KB ingestion          |
| **Web chat UI**             | Single-page app, Markdown rendering, in-line Approve/Reject buttons           |
| **Tests**                   | 50 tests (tools, security, graph, API) — all pass offline                     |
| **Containerization**        | `Dockerfile` + `docker-compose.yml` with volume persistence                   |

---

## 🚀 Quick start

### Prerequisites
- Python **3.10+**
- A Google Gemini API key (https://aistudio.google.com/app/apikey)

### 1. Install
```bash
cd bos
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env and paste your Gemini API key
```

### 3. Initialize database & seed demo data
```bash
python scripts/init_db.py
```

### 4. Ingest the sample knowledge base
```bash
python scripts/ingest_docs.py
```

### 5. Run the server
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open the UI
- **Chat UI:** http://localhost:8000
- **Admin dashboard:** http://localhost:8000/admin
- **API docs (Swagger):** http://localhost:8000/docs

---

## 🧠 Architecture

```
                   User (web chat / REST API)
                              │
                              ▼
                    Messaging Gateway (FastAPI)
                              │
                              ▼
                       ┌─────────────┐
                       │  CEO Agent  │  (intent classification, routing)
                       └─────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        Operations        Compliance       Portfolio
         Manager           Manager          Manager
              │               │               │
              └───────────────┴───────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  fan_out_workers      │  ← guardrail: append
                  │  (parallel workers)   │    compliance_worker for
                  └───────────────────────┘    approval-gated intents
                              │
                              ▼
                  ┌───────────────────────┐
                  │  approval_router      │  → request_approval [INTERRUPT]
                  │                       │  → resume on human decision
                  └───────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  compose_response     │  (Gemini final answer)
                  └───────────────────────┘
                              │
                              ▼
                          END / user
```

### Worker registry

| Manager     | Workers                                              |
| ----------- | ---------------------------------------------------- |
| Operations  | `crm_worker`, `document_worker`, `calendar_worker`   |
| Compliance  | `compliance_worker`, `retrieval_worker`              |
| Portfolio   | `research_worker`, `retrieval_worker`                |

---

## 🛠️ The state schema

The whole graph threads one `BrokerState` (see `app/state.py`):

```python
class BrokerState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], add_messages]
    user_message: str
    thread_id: str
    user_id: str
    username: str
    role: str
    permissions: List[str]

    # CEO layer
    intent: Optional[str]
    intent_confidence: float
    manager: Optional[str]                  # 'operations' | 'compliance' | 'portfolio' | 'clarify' | 'general'

    # Manager layer
    worker_plan: List[str]
    active_manager: Optional[str]

    # Worker layer
    worker_outputs: Dict[str, WorkerResult]
    worker_errors: Dict[str, str]

    # Approval / HITL
    approval_required: bool
    approval: Optional[ApprovalRecord]

    # Memory / context
    user_profile: Dict[str, Any]
    relevant_policies: List[Dict[str, Any]]

    # Output
    final_response: Optional[str]
    citations: List[str]
    trace: List[str]
```

---

## 🔐 Security (Phase 1 foundation)

| Control              | Where                                  |
| -------------------- | -------------------------------------- |
| API-key auth         | `app/api/deps.py` (`require_api_key`)  |
| RBAC (5 roles)       | `app/config.py` (`ROLE_PERMISSIONS`)   |
| PII detection+mask   | `app/security.py` (`detect_pii`, `mask_pii`) |
| Secrets redaction    | `app/security.py` (`redact`, `safe_dict`)     |
| Tool policy matrix   | `app/security.py` (`enforce_tool_policy`)     |
| Output validation    | `app/security.py` (`validate_agent_output`)   |
| Audit trail          | `app/audit.py` (every node event persisted)   |

Demo users (`app/security.py`):
- `advisor@bos.local`  — read-only client access
- `ops@bos.local`      — CRM write
- `compliance@bos.local` — approvals + audit
- `manager@bos.local`  — override + approve
- `admin@bos.local`    — wildcard (everything)

---

## 🧪 Human-in-the-Loop approvals

Approval gates (PRD §6 / FR6) fire automatically for these intents
(`app/config.py → APPROVAL_INTENTS`):
- `account_opening`, `account_transfer`
- `investment_recommendation`, `compliance_exception`
- `document_submission`, `trade_execution`
- `high_risk_operation`

The flow:

1. CEO classifies intent → if intent ∈ APPROVAL_INTENTS, `fan_out_workers`
   guardrail **forces** `compliance_worker` to run.
2. `compliance_worker` calls `validate_policy()` → sets `approval_required=True`.
3. `approval_router` routes to `request_approval` node.
4. Node calls LangGraph `interrupt(payload)` → graph pauses.
5. Approval record persisted to `approvals` table.
6. Admin dashboard shows it under **Approvals** → click Approve/Reject.
7. Frontend calls `POST /api/chat/resume` with the decision.
8. Graph resumes → `compose_response` produces the final answer.

API example:
```bash
# 1. Trigger workflow that needs approval
curl -X POST http://localhost:8000/api/chat \
  -H "X-API-Key: $BOS_API_KEY" -H "Content-Type: application/json" \
  -d '{"message": "Open a new retirement account for Jane Doe"}'

# 2. Inspect pending approvals
curl -H "X-API-Key: $BOS_API_KEY" http://localhost:8000/api/approvals

# 3. Approve
curl -X POST http://localhost:8000/api/approvals/<id>/decision \
  -H "X-API-Key: $BOS_API_KEY" -H "Content-Type: application/json" \
  -d '{"decision": "approved", "decided_by": "compliance@bos.local"}'

# 4. Resume the workflow
curl -X POST http://localhost:8000/api/chat/resume \
  -H "X-API-Key: $BOS_API_KEY" -H "Content-Type: application/json" \
  -d '{"thread_id": "<thread>", "decision": "approved", "decided_by": "compliance@bos.local"}'
```

---

## 📚 RAG / Knowledge base

- Documents in `/knowledge_base` (`*.md`, `*.txt`, `*.pdf` supported)
- Chunked with sliding window (800 chars, 100 overlap) — `app/chunking.py`
- Embedded with Gemini `gemini-embedding-001`
- Stored in ChromaDB (local, file-based) at `app/data/chroma`
- Queried by `retrieval_worker` and exposed via `/api/ingest/search`

Ingest more docs anytime:
```bash
# Re-seed from disk
curl -X POST -H "X-API-Key: $BOS_API_KEY" http://localhost:8000/api/ingest/seed

# Or upload a single file
curl -X POST -H "X-API-Key: $BOS_API_KEY" \
     -F "file=@mypolicy.pdf" -F "doc_type=policy" \
     http://localhost:8000/api/ingest/file

# Or text inline
curl -X POST -H "X-API-Key: $BOS_API_KEY" -H "Content-Type: application/json" \
     -d '{"source":"note1","doc_type":"knowledge","text":"..."}' \
     http://localhost:8000/api/ingest/text
```

---

## 🌐 API reference

Interactive Swagger UI at `/docs`. Highlights:

| Method | Path                              | Description                          |
| ------ | --------------------------------- | ------------------------------------ |
| POST   | `/api/chat`                       | Run one BOS turn (JSON)              |
| POST   | `/api/chat/stream`                | Run one BOS turn (SSE)               |
| POST   | `/api/chat/resume`                | Resume an interrupted workflow       |
| GET    | `/api/approvals`                  | List approval requests               |
| POST   | `/api/approvals/{id}/decision`    | Approve / reject                     |
| GET    | `/api/admin/health`               | Liveness + Gemini + KB stats         |
| GET    | `/api/admin/workflows`            | Workflow history                     |
| GET    | `/api/admin/audit`                | Audit trail (last N events)          |
| GET    | `/api/admin/agents`               | Topology / agent registry            |
| GET    | `/api/admin/clients`              | CRM clients                          |
| GET    | `/api/admin/documents`            | Generated documents                  |
| GET    | `/api/admin/events`               | Calendar events                      |
| GET    | `/api/admin/users`                | Demo user directory                  |
| GET    | `/api/admin/profiles`             | Long-term user profiles              |
| POST   | `/api/ingest/text`                | Ingest raw text                      |
| POST   | `/api/ingest/file`                | Ingest .txt/.md/.pdf                 |
| POST   | `/api/ingest/seed`                | Re-ingest /knowledge_base folder     |
| GET    | `/api/ingest/search?q=...`        | Semantic search                      |

---

## ✅ Tests

```bash
pytest tests/ -v
```

50 tests across:
- `tests/test_tools.py` — CRM, documents, calendar, compliance, research (deterministic)
- `tests/test_security.py` — auth, RBAC, PII masking, tool policy, output validation
- `tests/test_graph.py` — graph topology, routing, rule-based fallback, HITL interrupt
- `tests/test_api.py` — FastAPI endpoints (TestClient)

All tests run **fully offline** (LLM calls are mocked).

---

## 🐳 Docker

```bash
# Build & run with docker-compose
export GEMINI_API_KEY=your-key
docker compose up --build

# Or with plain docker
docker build -t brokerage-os:1.0.0 .
docker run -p 8000:8000 -e GEMINI_API_KEY=your-key -v bos-data:/app/app/data brokerage-os:1.0.0
```

Persistent data lives in the `bos-data` named volume (SQLite + Chroma).

---

## 📁 Project layout

```
bos/
├── app/
│   ├── agents/                # CEO, managers (3), workers (6), composer, approval
│   ├── api/                   # FastAPI routers: chat, approval, admin, ingest
│   ├── memory/                # short_term, long_term, organizational (RAG)
│   ├── tools/                 # crm, documents, calendar, compliance, research, retrieval
│   ├── audit.py               # Audit trail (SQLite)
│   ├── chunking.py            # RAG chunker
│   ├── config.py              # Settings + RBAC permissions + APPROVAL_INTENTS
│   ├── graph.py               # Main LangGraph definition
│   ├── llm.py                 # Gemini LLM + embeddings
│   ├── logging_setup.py       # structlog JSON logging
│   ├── main.py                # FastAPI app factory
│   ├── security.py            # Auth, PII, secrets, tool policy
│   └── state.py               # BrokerState schema
├── knowledge_base/            # Sample policy / SOP / guidelines
├── scripts/                   # init_db.py, ingest_docs.py
├── tests/                     # 50 tests
├── web/                       # index.html (chat), admin.html (dashboard)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md (this file)
```

---

## 🛡️ Failure handling & graceful degradation

The system stays operational even when the LLM is unreachable (quota, network,
auth) thanks to deterministic fallbacks:

| Layer        | Primary (LLM)                       | Fallback (deterministic)                |
| ------------ | ----------------------------------- | --------------------------------------- |
| CEO classify | Gemini JSON intent                  | `_rule_based_classify()` keyword rules  |
| Manager plan | Gemini JSON worker plan             | `_rule_based_plan()` per-manager default |
| Composer     | Gemini natural-language summary     | Worker-summary bullet list              |
| Worker       | Gemini summary (research)           | Raw tool-data summary                   |
| Approval gate| Gemini-driven policy validation     | Hardcoded `APPROVAL_INTENTS` guardrail  |

Every fallback is logged to the audit trail with `fallback=True`.

---

## 🗺️ Roadmap (Phase 2+)

The PRD lists several items intentionally deferred from Phase 1:

- Voice / telephony
- Real broker / market-data integrations (Bloomberg, Salesforce, DocuSign…)
- Real Slack / Teams / WhatsApp Business adapters (currently web-chat only)
- AES-256 at rest + KMS-managed keys (Phase 1 uses env-var secrets)
- Full SOC2 / FINRA / SEC compliance packaging
- Kubernetes manifests + horizontal scaling
- LangSmith deep-integration observability dashboard

The Phase 1 architecture is intentionally shaped so each of these can be
added without restructuring the graph or state schema.

---

## 📝 License

Proprietary — Phase 1 reference implementation.
