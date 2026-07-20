# BOS Phase 1 — Improvement Analysis

> Dokumen analisis menyeluruh terhadap codebase `bos/` (Brokerage Operating System Phase 1)
> ditinjau terhadap PRD `prd.md`.
>
> Tanggal analisis: 2026-07-19
> Cakupan: 3.758 LOC Python + 662 LOC HTML/JS, 50 unit/integration tests.

---

## Daftar Isi

1. [Apa yang Perlu Di-Improve](#1-apa-yang-perlu-di-improve)
   - [1.1 Code Quality Issues](#11-code-quality-issues)
   - [1.2 Performance Bottlenecks](#12-performance-bottlenecks)
   - [1.3 Architectural Smells](#13-architectural-smells)
   - [1.4 Tech Debt](#14-tech-debt)
   - [1.5 Observability Gaps](#15-observability-gaps)
   - [1.6 Error Handling Gaps](#16-error-handling-gaps)
   - [1.7 Test Coverage Gaps](#17-test-coverage-gaps)
2. [Fitur yang Perlu Dibuat Lagi](#2-fitur-yang-perlu-dibuat-lagi)
3. [Production Readiness Assessment](#3-production-readiness-assessment)
4. [UX/UI Improvements](#4-uxui-improvements)
5. [Prioritas Aksi](#5-prioritas-aksi)

---

## 1. Apa yang Perlu Di-Improve

### 1.1 Code Quality Issues

#### A. Dead Code & Unused Exports (terverifikasi via grep)

| Lokasi | Status | Bukti |
|---|---|---|
| `app/agents/managers/_common.py:130` `merge_worker_outputs()` | Diekspor & diimpor oleh ketiga manager (`operations_manager.py:16`, `compliance_manager.py:16`, `portfolio_manager.py:16`) **tetapi tidak pernah dipanggil**. Manager cuma `pass-through` ke `fan_out_workers`. | `grep merge_worker_outputs app/` hanya menemukan impor + definisi, zero call-site. |
| `app/memory/short_term.py:54` `build_short_term_memory()` dan `:81` `get_conversation_summary()` | Diekspor di `app/memory/__init__.py:6` **tetapi tidak pernah dipanggil** oleh node manapun. | `state.get("short_term_summary")` di `ceo.py:78` selalu `None`. |
| `app/security.py:195` `validate_agent_output()` | Fungsi validasi `contract worker` ada + ada `unit test` (`tests/test_security.py:106-114`) **tetapi tidak pernah dipanggil** oleh `worker` manapun di `runtime`. | `grep validate_agent_output app/` — hanya definisi. |
| `app/security.py:206` `enforce_tool_policy()` | "Tool Permission Matrix" (PRD §12 / §14) ada + ada `unit test` **tetapi tidak di-wire ke `worker execution path`**. `Worker` bisa panggil `tool` apapun. | `grep enforce_tool_policy app/` — hanya definisi & `tests`. |
| `app/audit.py:235` `expire_stale_approvals()` | Method timeout-approval ada **tetapi tidak ada `scheduler/cron` yang memanggilnya**. Approval `pending` bisa menggantung selamanya di DB. | Tidak ada pemanggilan di `app/`. |
| `app/memory/long_term.py:136` `add_fact()` dan `:156` `list_facts()` | Tabel `user_facts` dibuat saat `init` **tetapi tidak ada agent yang menulis `fact`**. Fitur "Long-term Facts" PRD §FR5 tidak berfungsi. | Tidak ada call-site di `app/agents/`. |
| `app/api/chat.py:7` dokumen `WS /api/chat/ws` | Docstring mengklaim `WebSocket endpoint` ada. **Tidak ada `@router.websocket` / `@app.websocket` dimanapun di codebase.** | `grep -rn "websocket" app/` — hanya komentar di docstring. |
| `app/api/chat.py:147` `POST /api/chat/stream` (`SSE`) | `Endpoint` ada & berfungsi **tetapi `web/index.html` hanya memanggil `/api/chat` (`one-shot`)**. `SSE` tidak terpakai. | `grep -rn "chat/stream\|EventSource" web/` — kosong. |

#### B. Duplikasi & Boilerplate

1. **Tiga `manager` pada dasarnya identik** — `operations_manager.py`, `compliance_manager.py`, `portfolio_manager.py` (masing-masing 70-80 baris) hanya memanggil `llm_plan_workers()`, lalu `if w["name"] == "X":` `copy params` ke `state`. Bisa di-refactor menjadi satu `parameterized manager factory`.
2. **"`Fallback template` string" diduplikasi di 5 tempat**: `ceo.py:195-203` (`general`), `ceo.py:218-221` (`clarify`), `composer.py:77-87`, `_common.py:84-127`, `workers/research_worker.py:84`. Tidak ada `central copy`.
3. **`Worker nodes` (`crm`, `document`, `calendar`, `research`, `compliance`, `retrieval`) mengikuti pola yang nyaris identik** (`_trace` → `audit` → `try/except` → `build WorkerResult` → `update worker_outputs`). 90% `boilerplate`, 10% `business logic`.
4. **`SQLite connection` dibuka per operasi** di `audit.py:94-103`, `long_term.py:58-61`, `crm.py:62-65`, `short_term.py:30-34` — pola `context manager` yang sama diulang 4x.

#### C. Tight Coupling & Mutasi State Langsung

1. **`app/agents/base.py:35`** — `_trace()` `memutasikan state secara langsung` ("mutate in place for siblings that share state"). Ini melanggar model `state-delta LangGraph` dan akan menyebabkan `race condition` begitu `worker` jalan paralel via `Send`.
2. **`Manager` mencemari `global state` dengan `key` `worker-spesifik** (`crm_op`, `doc_template`, `cal_when`, `research_symbols`, `comp_op`, dll.). `State` schema di `state.py` bahkan tidak mendeklarasikan `key` ini (`total=False` `mengizinkan apapun`). Jika dua `worker` butuh `key` yang sama → `collision`.
3. **`app/agents/base.py:25-36`** — fungsi `_trace` dipanggil **dua kali** di banyak `node` (`ceo.py:65` di awal method, `ceo.py:121` di `return statement`). Ada `dedup` (`if tr[-1] != node`) tapi rentan `bug`.

#### D. Hardcoded Secrets & Config

1. **`app/config.py:42-44`** — `default value` `api_key`, `jwt_secret`, `encryption_key` adalah `string placeholder` `"bos-local-dev-key-CHANGE-ME"`, `"bos-local-jwt-secret-CHANGE-ME"`, `"bos-local-encryption-key-32bytes"`. Jika env var tidak diset, sistem tetap `boot` dengan kredensial `default` yang diketahui publik.
2. **`app/security.py:73-79`** — direktori 5 user demo (`advisor@bos.local`, dll.) di-`hardcode` di kode Python, bukan di DB atau `config file`. Tidak ada cara `add/edit/delete user` tanpa `code change`.
3. **`.env.example:6`** berisi `API key` Gemini `ASLI` yang sudah `auto-revoked`: `GEMINI_API_KEY=REDACTED_GOOGLE_API_KEY`. Harusnya `placeholder` `your-api-key-here`. Ini `security smell` (kunci pernah `leak`, walau sudah `disabled`).
4. **`web/index.html:128` dan `web/admin.html:91`** — `API key` `default` `bos-local-dev-key-CHANGE-ME` di-`hardcode` di `HTML` `value attribute`.

#### E. PII Handling yang Setengah Jadi

- `detect_pii()` dan `mask_pii()` ada di `security.py:138-158`, **tetapi `detect_pii` tidak pernah dipanggil pada `inbound user message`**. Hanya `summarize_for_audit` yang memanggil `mask_pii` untuk `audit log`. **PII user tetap dikirim mentah ke LLM.**
- `regex` `credit_card` `\b(?:\d[ -]*?){13,16}\b` akan `false-positive` pada nomor telepon 16-digit; `regex` `phone` tidak menangani nomor non-US.

#### F. Lain-Lain

1. **`pyproject.toml:15`** — `packages = ["app"]` saja. `tests/`, `scripts/`, `web/`, `knowledge_base/` tidak di-`package`. `pip install` akan rusak.
2. **`app/main.py:73-79`** — `CORSMiddleware` dengan `allow_origins=["*"]` + `allow_credentials=True`. `Browser` akan `reject` kombinasi ini; jika dilepas `credential`-nya, ini tetap `security hole`.
3. **`app/agents/composer.py:69`** — `payload JSON` di-`truncate` ke 6000 `chars` (`json.dumps(..., default=str)[:6000]`). Bisa `memotong di tengah JSON` → LLM dapat `JSON malformed`.
4. **`app/agents/ceo.py:152-156`** — `Ticker regex` `\b[A-Z]{2,6}\b` akan `match` "HI", "OK", "USA", "PDF" sebagai `ticker`.
5. **`app/tools/documents.py:111`** — `komentar` "PDF lib in Phase 2" tapi `function` dinamai `prepare_pdf`. Menyesatkan; `function` menghasilkan `.txt` bukan `.pdf`.

---

### 1.2 Performance Bottlenecks

#### A. Sync LLM di Endpoint Async

- **`app/api/chat.py:133`** — `chat_endpoint` adalah `def` (sync) yang memanggil `run_bos_turn` → `graph.invoke` (`blocking`, bisa 5-30 detik untuk workflow kompleks). `FastAPI` menjalankan `sync endpoint` di `threadpool` (default 40 `thread`). Pada 40+ `concurrent user`, `request queue` akan `stuck`.
- **PRD §15** menargetkan "100 concurrent workflows". Konfigurasi saat ini **tidak akan mencapainya**.
- `Solusi`: ubah ke `async def` + `graph.ainvoke`, atau `offload` ke `process pool`.

#### B. "Parallel" Workers Sebenarnya Sequential

- **`app/graph.py:58-119`** — `fan_out_workers_node` secara eksplisit **melakukan iterasi worker secara berurutan** dalam satu `for loop` (dijelaskan di `comment` baris 60-69).
- **PRD §15** menargetkan "Up to 50 worker tasks" paralel. Implementasi saat ini: 0 paralelisme.
- `Solusi`: gunakan `Send` API LangGraph untuk `true fan-out`, atau `asyncio.gather` jika `worker` diubah ke `async`.

#### C. SQLite Connection per Operation

- **`app/audit.py:94-103`** — `context manager` `_conn()` membuat `sqlite3.connect()` **baru setiap call**. Setiap `record_event` = `open connection` + `acquire lock` + `INSERT` + `close`. Pada `workflow` dengan 5-10 `audit event`, ini 5-10x `connection setup`.
- **`app/memory/long_term.py:58-61`** dan **`app/tools/crm.py:62-65`** melakukan hal yang sama.
- `Solusi`: `connection pool` atau `singleton connection` dengan `WAL mode`.

#### D. Health Endpoint membakar Kuota Gemini

- **`app/api/admin.py:34`** — `endpoint /api/admin/health` memanggil `ping_gemini()` yang melakukan **invoke LLM + embed query sungguhan** ke Gemini.
- **`web/admin.html:341`** — dashboard `polling` `refreshAll()` **setiap 5 detik**.
- **Akibat**: 12 `request Gemini` per menit hanya untuk `health check`. Kuota `free-tier` Gemini `flash` hanya **20 `request` per hari**. Dashboard akan `menghabiskan kuota` dalam 100 detik.
- `Solusi`: `cache health` 60 detik; atau `pisahkan endpoint` `/live` (`process check`) vs `/ready` (`dependency check`).

#### E. Embedding Sinkron di Async Path

- **`app/api/ingest.py:51`** — `ingest_file` adalah `async def`, **tetapi** di dalamnya memanggil `get_organizational_memory().add_documents()` yang sinkron dan memanggil `embeddings_client.embed_documents(texts)` (`embedding` untuk batch besar bisa 5-30 detik). Memblokir `event loop`.
- `Solusi`: `offload` ke `executor` atau `batch`+`stream`.

#### F. Tidak ada Caching Layer

- **PRD §18** merekomendasikan `Redis` untuk `cache`. **Tidak ada Redis` dependency` (`grep redis requirements.txt` → kosong), tidak ada ` decorator`, tidak ada `response cache`**.
- `Intent classification` untuk pesan yang sama di-`compute` berulang.

---

### 1.3 Architectural Smells

#### A. Empat Singleton untuk Satu File SQLite

`audit.py`, `long_term.py`, `crm.py`, `short_term.py` masing-masing membuka `connection` sendiri ke file `bos.db` yang sama. Tidak ada:
- `Shared SQLAlchemy engine` (`padahal` `requirement` `sqlalchemy>=2.0.36` ada di `requirements.txt:25` — `dependency` tidak terpakai).
- `Migration framework` (`Alembic`).
- `Transaction boundary` yang konsisten (`atomic workflow`).

Akibat: `partial failure` bisa `leave DB` dalam `state` `inkonsisten` (mis. `audit terekam` tapi `CRM update gagal`).

#### B. Tiga Manager = Satu Manager yang Di-parametrisasi

`Operations_manager`, `compliance_manager`, `portfolio_manager` memiliki `shape` yang identik:
```
1. _trace(state, ...)
2. plan = llm_plan_workers(manager=..., allowed_workers=[...], worker_capabilities={...})
3. For w in plan["workers"]: copy w["params"] ke state["<worker>_op"] etc.
4. record_event(...)
5. Return state_updates + trace
```
`~80%` `code` adalah `boilerplate`. Bisa jadi **satu `factory function` + `config dict` per manager**.

#### C. Boundary Layer Tidak Ada (No Service Layer)

`API endpoint` (`admin.py`, `chat.py`, `ingest.py`, `approval.py`) **langsung memanggil `tool`, `audit`, dan `memory`**. Tidak ada:
- `Service layer` / `use-case layer`.
- `Domain model` (no `dataclass` for `Workflow`, `Approval`, `Message`).
- `Repository pattern`.

`Tight coupling`: ganti `transport layer` (mis. ke `gRPC`) = `rewrite endpoint`. Ganti DB (`PostgreSQL`) = `sentuh semua tool`.

#### D. `lru_cache` Mengabaikan Perubahan Settings

- **`app/llm.py:25, 45`** — `@functools.lru_cache()` untuk `get_llm` dan `get_embeddings` hanya men-`cache` berdasarkan argumen `temperature`/`model`. **Jika `GEMINI_API_KEY` berubah saat `runtime** (mis. `test fixture`, `secret rotation`), `client lama` tetap dipakai.
- `Solusi`: `inject Settings instance` sebagai argumen, atau `bust cache` saat `settings change`.

#### E. `interrupt()` Type Ambiguity

- **`app/agents/approval.py:89-101`** — `decision = interrupt(payload)`. `Resume value` diasumsikan `dict` (`decision.get("decision")`), **tetapi**:
  - **`app/api/chat.py:223-228`** mengirim `Command(resume={"decision": ..., "decided_by": ..., "note": ...})` (`dict`). ✔
  - **Tapi tidak ada validasi tipe**. Jika `caller external` mengirim `string "approved"`, akan `crash` di `decision.get(...)`.

#### F. Dua Source of Truth untuk Permissions

- `ROLE_PERMISSIONS` di `app/config.py:66` (declarative mapping).
- `_DEMO_USERS` di `app/security.py:73` (`hardcoded` list dengan `role`).
- `Tool policy matrix` (`enforce_tool_policy`) membutuhkan `policy` `dict` yang **tidak didefinisikan dimanapun** (`worker` memanggilnya dengan `policy={}` atau tidak memanggil sama sekali).

---

### 1.4 Tech Debt

| Item | Lokasi | Dampak |
|---|---|---|
| Python 3.10 minimum, tapi `from typing import List, Dict, Optional` dimana-mana | semua file | Bisa pakai `list[X]`, `dict[K,V]`, `X \| None` sejak 3.10. `Style inkonsisten`. |
| Dua PRD beruntun di `prd.md` (1725 + 1000 baris, duplikatif + catatan reviewer) | `prd.md` | `Source of truth tidak jelas`; `engineer` bingung mana yang `binding`. |
| **Tidak ada CI/CD** padahal README §"Tests" & `Phase 1 deliverables` menyebutnya | repo root | Tidak ada `.github/workflows/`, `GitLab CI`, atau `Jenkinsfile`. `Regression` hanya jalan jika `dev` ingat. |
| **Tidak ada K8s manifests** padahal `Phase 1 deliverables`: "Dubernetes-ready manifests" | repo root | Tidak ada `k8s/`, `helm/`, atau `kustomize/`. README `mengakui Phase 2`. |
| `requirements.txt` mencantumkan `sqlalchemy>=2.0.36`, `aiosqlite>=0.20`, `tenacity>=9.0`, `tiktoken>=0.8` **yang tidak pernah di-import** | semua `app/` | `Dependency bloat`; `install time` lebih lambat, `attack surface` lebih luas. |
| `LangSmith config flag` (`config.py:50`) `langsmith_tracing: bool = False` | `app/config.py:50` | `Flag` ada **tetapi tidak ada `code` yang membaca flag ini** untuk `enable/disable tracing`. |
| `SETUP_NOTES.md:7` mengaku "50 tests passing" | `tests/` | 50 `tests`, **tetapi** `coverage` <40% `business logic`. |
| Manager `merge_worker_outputs` diimpor tapi tidak dipakai | `_common.py:130` | `Dead API design` — `code path` lama yang `abandoned`. |
| `app/tools/documents.py` namanya `prepare_pdf` tapi menghasilkan `.txt` | line 100 | `Nama function` menyesatkan. |
| `index.html` & `admin.html` `inline JS/CSS` (~300+ baris JS per file) | `web/` | Tidak modular, tidak ada `build step`, sulit `test`. |

---

### 1.5 Observability Gaps

PRD §18 mensyaratkan **"`LangSmith + OpenTelemetry + Grafana`"**. Status saat ini:

| Layer | Diharapkan PRD | Aktual |
|---|---|---|
| **Metrics** (`latency`, `token usage`, `cost`, `retry count`, `error rate`) | Wajib | **Tidak ada sama sekali.** Tidak ada `Prometheus`, `StatsD`, atau `metric decorator`. |
| **Tracing** (`LangSmith`, `OpenTelemetry`) | Wajib | `Flag config` ada (`config.py:50`) **tetapi tidak di-wire**. Tidak ada `span` per LLM/tool/graph-node. |
| **Structured logs** | JSON | `structlog` dikonfigurasi di `logging_setup.py` **tetapi semua modul pakai `logging.getLogger()` (`stdlib`) — `structlog config` tidak berdampak.** |
| **Error tracking** (`Sentry`, `Rollbar`) | Tersirat | Tidak ada. |
| **Audit retention policy** | Tersirat (`financial audit`) | `audit_events` table tumbuh tak terbatas. Tidak ada `TTL` / `archival`. |
| **Cost tracking** (`token`/`workflow`) | PRD reviewer note: "Average Cost <$0.15/workflow" | Tidak ada `usage capture`. |
| **Hallucination monitor** | PRD KPI: "<2%" | Tidak ada `evaluator`. |
| **Approval latency metric** | PRD: "<30 sec" | Tidak dihitung. `decided_at - requested_at` tersimpan tetapi tidak di-query. |
| **Fallback rate aggregation** | PRD KPI: "<10%" | `fallback=True` tersimpan di `metadata`, **tetapi tidak ada API untuk agregasi**. |
| **Real-time agent health** | Admin dashboard | Hanya "Gemini ok/down" (`admin.py:34`). Tidak ada per-agent `error rate`, `p95 latency`. |

---

### 1.6 Error Handling Gaps

#### A. Swallowed Exceptions

- **`app/agents/workers/crm_worker.py:84-85`** — `except Exception: pass` tanpa `log`. `CRM conversation` gagal → `silent failure`.
- **`app/agents/workers/calendar_worker.py:57-58`** — `try: cal_reminder(...) except Exception: pass`. `Reminder` gagal → `silent`.
- **`app/api/chat.py:177-178`** — `producer()` di `SSE` menelan `exception` ke `queue`, tetapi jika `queue.put(None)` gagal, `consumer` akan `hang selamanya`.

#### B. Tidak Ada Retry / Circuit Breaker

- PRD reviewer note §6: "Jika `worker` gagal karena error sementara, `supervisor` `retry` maksimal 2 kali".
- PRD reviewer note §9: "`Circuit breaker`: jika `worker` gagal 3x berturut-turut, `nonaktifkan`".
- **Aktual**:
  - `langchain_google_genai` `client` punya `max_retries=3` (`llm.py:39`) tetapi hanya untuk `transport error` (HTTP 429/5xx). **Tidak ada `retry` untuk `quota error` atau `malformed response`.**
  - Tidak ada `retry decorator` di `tool layer`.
  - Tidak ada `circuit breaker`.
  - **`app/graph.py:100-110`** — `worker` `crash` ditangkap, dimasukkan ke `worker_outputs` dengan `status:"failed"`, **workflow lanjut tanpa `retry`**.

#### C. HTTP Exception membocorin Internal Detail

- **`app/api/chat.py:142`** — `raise HTTPException(status_code=500, detail=f"workflow error: {e}")`. `Exception message` (yang mungkin berisi `stack trace` atau `sensitive path`) langsung dikembalikan ke `client`. Bocor `internal info`.

#### D. Tidak Ada Request Timeout

- `graph.invoke()` (`chat.py:101`) tidak punya `timeout`. `Gemini call` yang `hang` (`network issue`) bisa menyebabkan `request` `HTTP` `hang selamanya`. `Browser` mungkin `retry`, `memperparah situasi`.

#### E. Tidak Ada Global Error Handler

- Tidak ada `FastAPI exception_handler` (`@app.exception_handler(Exception)`). `Unhandled exception` = `500` `default FastAPI` dengan `stack trace` ke `console`.

#### F. PII Detection Tidak Mencegah Ingest

- `detect_pii()` ada, **tetapi**:
  - Tidak dipanggil pada `POST /api/chat` (`user message` langsung ke LLM).
  - Tidak dipanggil pada `POST /api/ingest/file` (`PDF` dengan `SSN` akan `masuk Chroma` `mentah`).
  - Tidak dipanggil pada `POST /api/ingest/text`.

---

### 1.7 Test Coverage Gaps

50 `tests` ada. Yang **belum tercakup**:

| Area | File/Endpoint | Status |
|---|---|---|
| `SSE streaming` | `POST /api/chat/stream` (`chat.py:147`) | **Tidak ada `test`.** |
| `HITL resume path` | `POST /api/chat/resume` (`chat.py:200`) | **Tidak ada `test`.** Hanya `interrupt` yang diuji. |
| `File ingestion` | `POST /api/ingest/file` (`ingest.py:50`) | **Tidak ada `test`.** |
| `Seed KB` | `POST /api/ingest/seed` (`ingest.py:89`) | **Tidak ada `test`.** |
| `Search endpoint` | `GET /api/ingest/search` (`ingest.py:130`) | **Tidak ada `test`.** |
| `Approval detail` | `GET /api/approvals/{id}` (`approval.py:33`) | **Tidak ada `test`.** |
| `Real Gemini integration` | `app/llm.py` | **Selalu di-mock.** Tidak ada `integration test` dengan `replay/cassette` (`vcr.py`). |
| `Load/concurrency` | - | **Tidak ada.** PRD `mewajibkan` "100 `concurrent workflows`". |
| `Regression scenarios` | PRD `Phase 1 deliverable` | **Tidak ada `scenario matrix`** (`docs/scenarios.md` tidak ada). |
| `Compliance worker` `approval_required=True` via `intent guardrail` | `compliance_worker.py:68-69` | **Tidak ada `test` yang `memverifikasi` `approval` `trigger` via `APPROVAL_INTENTS`.** |
| `compose_response_node` dengan LLM aktif | `composer.py:73` | Hanya `fallback` yang diuji. |
| `Long-term memory facts` | `add_fact`, `list_facts` (`long_term.py:136,156`) | **Tidak ada `test`.** |
| `Expire stale approvals` | `expire_stale_approvals` (`audit.py:235`) | **Tidak ada `test`.** |
| `Tool policy runtime enforcement` | `enforce_tool_policy` (`security.py:206`) | Hanya `unit test` `direct`. Tidak ada `test` yang `memverifikasi worker` `honor policy`. |
| `Output validation runtime` | `validate_agent_output` (`security.py:195`) | Hanya `unit test` `direct`. |
| `PII masking` `end-to-end` (`user input → LLM`) | - | **Tidak ada.** |
| `Prompt injection` `resistance` | PRD reviewer note §12 | **Tidak ada `test`.** |
| `Circuit breaker` | - | Tidak ada (karena `impl` tidak ada). |
| `Retention/pruning memory` | - | Tidak ada. |
| `Auth negative cases` | salah `role` mencoba `approval`, dll. | `test_security.py` hanya cek `permission flag`, tidak `simulate` `HTTP 403`. |
| `Audit trail` `immutability` | - | Tidak ada. |
| `Module-scoped graph fixture` | `tests/test_graph.py:21` | `@pytest.fixture(scope="module")` → **`state` `leaks` antar `test` via `shared checkpointer`.** |
| `Web UI` (`index.html`, `admin.html`) | - | **Zero UI tests** (`Playwright`/`Cypress`). |

**Estimasi coverage aktual: 30-40%** business logic, 0% UI.

---

## 2. Fitur yang Perlu Dibuat Lagi

Pemetaan PRD → `codebase`. ✅ = `terimplementasi`, ⚠️ = `sebagian`, ❌ = `tidak ada`.

### 2.1 FR1 Messaging Gateway (PRD §8, §19)

| Sub-FR | Status | Bukti / Catatan |
|---|---|---|
| Web Chat | ✅ | `index.html` + `POST /api/chat` |
| **Slack** | ❌ | Tidak ada `adapter`. **Wajib di `Phase 1`** menurut §19: "`Web chat plus one enterprise messaging integration`". |
| **Microsoft Teams** | ❌ | Tidak ada. |
| **WhatsApp Business API** | ❌ | Tidak ada. |
| **Email** | ❌ | Tidak ada `adapter`. |
| Authenticate users | ⚠️ | Hanya `shared API key`; tidak ada `per-user authN`. PRD §14 `Permission matrix` **tidak diterapkan** di `endpoint`. |
| Conversation history | ⚠️ | `thread_id` didukung, **tetapi UI tidak memuat history sebelumnya saat reload**. |
| Attachments | ❌ | `ChatRequest` (`chat.py:40`) hanya menerima `message: str`. **Tidak ada `multipart upload`** di `/api/chat`. |

### 2.2 FR2 CEO Agent

| Sub-FR | Status | Catatan |
|---|---|---|
| Understand request | ✅ | `ceo_classify_node` (`ceo.py:63`) |
| Identify workflow | ✅ | Intent classification |
| Allocate manager | ✅ | `ceo_route` (`ceo.py:166`) |
| **Resolve conflicts** | ❌ | Tidak ada `multi-manager fanout`, tidak ada `conflict resolution`. |
| **Escalate failures** | ❌ | Tidak ada `escalation node`. `Worker` gagal → `workflow` tetap lanjut ke `composer`. |

### 2.3 FR3 Manager Agents

| Manager | Expected Workers (PRD §9) | Aktual | Gap |
|---|---|---|---|
| Portfolio | Market Research, **Risk Agent**, **Performance Agent** | `research_worker`, `retrieval_worker` | ❌ **Risk Agent & Performance Agent tidak ada.** |
| Compliance | **AML Agent**, **KYC Agent**, **Regulatory Agent** | `compliance_worker` (`collapsed`), `retrieval_worker` | ⚠️ `Tiga sub-agent` di-`collapse` jadi satu `worker`. `Granularitas` hilang. |
| Operations | CRM, Document, Scheduling | `crm_worker`, `document_worker`, `calendar_worker` | ✅ Match. |

### 2.4 FR4 Worker Agents

| Worker | Status | Catatan |
|---|---|---|
| Research Agent | ✅ | Mock data feed (`research.py`) |
| Document Agent | ⚠️ | Hanya `template string`. **Tidak ada `PDF generator asli`, tidak ada `OCR`** (`PDF lib Phase 2`). |
| CRM Agent | ✅ (mock) | SQLite `mock`, bukan `Salesforce`/`HubSpot`/`Dynamics` |
| Compliance Agent | ✅ (mock) | Rule-based, bukan `OFAC`/`sanctions` list `asli`. |
| Calendar Agent | ✅ (mock) | In-memory, bukan `Google Calendar`/`Outlook`. **Tidak ada `delivery reminder`** (diakui `calendar.py:82`). |
| Retrieval Agent | ✅ | Real Chroma + Gemini embeddings. **Hanya ini yang fully functional**. |
| **Email Agent** (PRD §9) | ❌ | Tidak ada. |

### 2.5 FR5 Memory

| Layer | Status | Catatan |
|---|---|---|
| Short-term | ✅ | LangGraph `SqliteSaver`. |
| Long-term profile | ✅ | `user_profiles` table. |
| **Long-term facts** | ⚠️ | `user_facts` table + method (`long_term.py:136`) **ada, tetapi tidak ada agent yang write**. Preferensi yang user sebut di chat tidak disimpan. |
| Organizational | ✅ | Chroma RAG. |
| **Memory strategy** (PRD reviewer note §8) | ❌ | Tidak ada `Conversation Memory → Session Summary → Long-term Facts → Semantic Retrieval → KB` pipeline. |
| **Retention policy / TTL / compression / summarization / pruning** | ❌ | Tidak ada. Memory tumbuh tak terbatas. |

### 2.6 FR6 Human Approval

| Sub-FR | Status | Catatan |
|---|---|---|
| `interrupt()` gate | ✅ | `approval.py:89` |
| Approval record persisted | ✅ | `audit.py:185` |
| Resume via API | ✅ | `chat.py:200` |
| UI approve/reject | ✅ | `index.html:268-289`, `admin.html:178-181` |
| **Notification ke compliance officer** (PRD reviewer note §4: "`Slack Block Kit` / `Teams Adaptive Cards`") | ❌ | Approval hanya muncul di dashboard. Tidak ada push notification. |
| **Timeout auto-action** | ❌ | `expire_stale_approvals` ada tetapi **tidak pernah dipanggil**. Tidak ada scheduler. Approval bisa `pending` selamanya. PRD reviewer note §3: "30 menit → auto-tolak". |
| **Configurable per-action threshold** | ⚠️ | Threshold `$1000` di-`hardcode` di `compliance.py:118`. Tidak ada `config UI`/`env`. |
| Multi-approver / quorum | ❌ | Single decider. |

### 2.7 FR7 Audit Trail

| Sub-FR | Status | Catatan |
|---|---|---|
| Records `timestamp`, `agent`, `reason`, `tools`, `docs`, `approval` | ✅ | `audit.py:108` |
| **Immutable / append-only** | ❌ | `UPDATE approvals SET status=...` (`audit.py:226`) — row bisa diubah. |
| **Cryptographic chaining** (financial audit standard) | ❌ | Tidak ada `hash chain`. |
| **Retention/archival policy** | ❌ | Tidak ada. |
| **Audit export** (`CSV`/`JSON` for regulator) | ❌ | Tidak ada `endpoint`. |
| Reasoning quality | ⚠️ | Sering kosong / satu kalimat (`"rule-based match"`, `""`). |

### 2.8 Phase 1 Deliverables (PRD §19) — Scorecard

| Deliverable | Status | Bukti |
|---|---|---|
| Hierarchical LangGraph orchestration | ✅ | `graph.py` |
| Conditional routing + retries | ⚠️ | Conditional routing ✅. **Retries ❌** (PRD §11 "`Edges`: `Retry`"). |
| Messaging-first interface (`+1 enterprise`) | ❌ | Web chat saja. **Slack/Teams tidak ada.** |
| Core specialized agents (CEO, Ops, Compliance, Research, CRM, Document, Retrieval, Calendar) | ✅ | Semua ada. |
| Human-in-the-loop approvals | ✅ | Berfungsi end-to-end. |
| Memory system (`conversation`, `profile`, `org`) | ⚠️ | 3 layers ✅, `facts extraction` ❌, retention ❌ |
| RAG pipeline (`ingest`, `embed`, `search`, `citation`) | ✅ | `Citation support` ada di `tool` (`retrieval.py`) **tetapi UI tidak menampilkannya**. |
| Tool integrations (`CRM`, `calendar`, `email`, `doc`, `market data`) | ⚠️ | `CRM`/`calendar`/`doc`/`market` = mock. **Email adapter ❌.** |
| Audit & observability (`LangSmith`, `OTEL`, `structured logs`) | ❌ | `LangSmith flag` ada, tidak di-wire. **Zero OTEL. Structlog tidak efektif.** |
| Security foundation (`RBAC`, `encryption`, `secrets`, `PII mask`) | ⚠️ | RBAC permissions defined **tetapi tidak enforced di API**. AES-256 ❌ (`diakui Phase 2`). PII detect ❌ (`hanya mask`). |
| Admin dashboard (`workflow monitor`, `agent health`, `approval queue`, `perf metrics`) | ⚠️ | `Approval queue` ✅. `Workflow list` ✅. **Performance metrics ❌. Agent health basic.** |
| Automated testing (`unit`, `integration`, `regression`) | ⚠️ | Unit + integration ✅. **Regression scenarios ❌.** Load test ❌. UI test ❌. |
| Deployment (`Docker`, `CI/CD`, `K8s manifests`) | ⚠️ | Docker ✅. **CI/CD ❌. K8s ❌.** |

**Score: ~7/13 deliverables fully met (54%).**

### 2.9 Fitur Setengah-setengah (Partial / Lying)

| Fitur | Klaim | Aktual |
|---|---|---|
| `WebSocket` | `chat.py:7` docstring "WS `/api/chat/ws`" | **Tidak ada endpoint**. |
| `SSE streaming` | `chat.py:147` endpoint ada | **Frontend tidak pakai** (`index.html` pakai `/api/chat` one-shot). |
| `LangSmith tracing` | `config.py:50` `flag` | **Tidak ada code yang baca flag** untuk `enable tracing`. |
| `Tool policy matrix` | `security.py:206` + `unit test` | **Tidak di-wire** ke `worker execution`. |
| `Output validation` | `security.py:195` + `unit test` | **Tidak di-wire**. |
| `expire_stale_approvals` | `audit.py:235` | **Tidak ada scheduler** yang panggil. |
| `Long-term facts` | `long_term.py:136,156` | **Tidak ada agent yang write.** |
| `prepare_pdf` | `documents.py:100` | Menghasilkan `.txt`, bukan `.pdf`. |
| "`structured logs`" (PRD §18) | `logging_setup.py` `configure structlog` | **Semua modul pakai `stdlib logging`, structlog config sia-sia.** |
| "`CI/CD`" (README §319) | - | **Tidak ada `.github/workflows/`.** |
| "`Kubernetes-ready`" (PRD §19) | - | **Tidak ada `k8s/`.** |

---

## 3. Production Readiness Assessment

### 3.1 Skor Keseluruhan: **~35-40% Production-Ready**

| Dimensi | Skor | Catatan |
|---|---|---|
| **Functional completeness** | 60% | Core happy path bekerja. Slack/Teams/Email adapter missing. |
| **Reliability** | 25% | No retry, no circuit breaker, no timeout, no fallback for non-LLM failures. |
| **Scalability** | 20% | SQLite + sync endpoints + sequential workers. Tidak akan handle 100 concurrent workflows. |
| **Security** | 30% | Shared API key, no RBAC enforcement, no encryption at rest, PII bocor ke LLM. |
| **Observability** | 15% | No metrics, no tracing, structlog not used. |
| **Maintainability** | 50% | Code readable tetapi 3 manager duplikatif, dead code banyak, no service layer. |
| **Testability** | 40% | 50 tests, tetapi coverage business logic ~30-40%, UI 0%, regression 0%. |
| **Deployability** | 35% | Docker image works. No CI/CD, no K8s, no blue-green. |

### 3.2 Blocker Terbesar Menuju Production

**Critical blockers (P0 - must fix before any prod traffic):**

1. **Auth model broken** — single shared API key = semua user adalah admin. Tidak ada multi-tenant isolation. (`app/security.py:48-68`, `app/api/deps.py:12-36`).
2. **RBAC tidak diterapkan di API** — `ROLE_PERMISSIONS` di config, `has_permission()` di AuthContext, tetapi **tidak ada dependency FastAPI** yang `check permission` per `endpoint`. (`grep require_permission app/api` → kosong).
3. **PII bocor ke LLM** — `detect_pii` ada tetapi tidak dipanggil di inbound path. (`app/api/chat.py` tidak panggil `mask_pii`).
4. **No encryption at rest** — SQLite plaintext di volume. PRD §15 "`AES-256 at rest`".
5. **CORS broken** — `allow_origins=["*"]` + `allow_credentials=True`. (`app/main.py:73-79`).
6. **Health endpoint membakar kuota Gemini** — bisa `menghabiskan` `free-tier` dalam 2 menit. (`admin.py:34`, `admin.html:341` polling 5s).
7. **No request timeout** — slow Gemini call = hung request forever. (`chat.py:101`).
8. **SQLite single-file** — tidak akan scale past 1 instance. PRD §15: "99.9% availability" impossible.
9. **No retry/circuit breaker** — single transient Gemini 429 = workflow failure.
10. **Hardcoded secrets** di `config defaults` & `demo user directory`.

**High-priority gaps (P1):**

11. Slack/Teams integration missing (PRD Phase 1 explicit deliverable).
12. No metrics/tracing — can't meet PRD §18 observability.
13. No CI/CD pipeline.
14. Approval timeout tidak enforced.
15. Structlog not actually used.
16. Audit table mutable.
17. No prompt injection defense.

### 3.3 Yang Harus Dikerjakan untuk Phase 2

Diurutkan berdasarkan dampak:

#### Wave 1 — Production Hardening (1-2 bulan)
1. **PostgreSQL migration** — replace SQLite (`audit`, `long_term`, `crm`, `short_term` checkpointer). Tambah Alembic.
2. **Real auth** — OAuth2/OIDC via Keycloak/Auth0. JWT dengan refresh token. Hapus shared API key.
3. **RBAC enforcement** — FastAPI dependency `require_permission("approval.approve")` di setiap endpoint.
4. **PII blocking** — panggil `mask_pii` di `ChatRequest` sebelum masuk graph. Opsi: structured output + NER model.
5. **AES-256 at rest** — field-level encryption untuk PII columns (Fernet / KMS).
6. **Retry & circuit breaker** — `tenacity` decorator di LLM call & tool call. Circuit breaker state di Redis.
7. **Request timeout** — `httpx.Timeout` + `asyncio.wait_for(graph.ainvoke, timeout=30)`.
8. **Approval timeout scheduler** — background task yang calling `expire_stale_approvals()` tiap menit.
9. **CORS config yang aman** — explicit origin whitelist.
10. **CI/CD** — GitHub Actions: lint, test, build, scan (Trivy/Snyk), deploy staging.

#### Wave 2 — Scalability (2-3 bulan)
11. **True worker parallelism** — ubah `fan_out_workers_node` pakai `Send` API LangGraph.
12. **Async endpoint** — `chat_endpoint` → `async def`, `graph.ainvoke`.
13. **Redis cache** — intent classification cache, Gemini response cache.
14. **Message queue** — Celery / Temporal untuk long-running workflows.
15. **Kubernetes manifests** — Deployment, Service, HPA, Ingress, SecretProvider.
16. **Connection pool** — SQLAlchemy async engine.

#### Wave 3 — Feature Completion (2-3 bulan)
17. **Slack adapter** — Slack Bolt, Block Kit untuk approval card.
18. **Teams adapter** — bot framework, Adaptive Cards.
19. **Email gateway** — IMAP/SMTP atau SendGrid.
20. **Real CRM** — Salesforce/HubSpot connector.
21. **Real market data** — Yahoo Finance / Alpha Vantage / Bloomberg.
22. **Real document tools** — DocuSign + PDF generator (`reportlab`) + OCR (Tesseract).
23. **Memory facts extraction** — agent yang extract user preferences → `add_fact`.
24. **Session summarization** — setiap N message, summarize → `short_term_summary`.

#### Wave 4 — Observability & Quality (ongoing)
25. **OpenTelemetry** — instrument FastAPI, LangGraph, langchain, Chroma, SQLite.
26. **LangSmith** wiring (config flag already exists).
27. **Prometheus metrics** — `bos_workflow_latency_seconds`, `bos_llm_tokens_total`, `bos_approval_pending_count`.
28. **Grafana dashboards** — workflow latency p50/p95/p99, error rate, token cost.
29. **Hallucination evaluator** — LLM-as-judge on composer output.
30. **Regression test suite** — 10-20 scenario end-to-end (`docs/scenarios.md`).
31. **Load test** — k6/locust: 100 concurrent workflows, 50 worker tasks.
32. **Prompt injection defense** — input sanitizer, system prompt hardening.
33. **Audit trail immutability** — append-only table + hash chain.
34. **Data retention policy** — audit archive after 7 years (FINRA), conversation prune after 90 days.

---

## 4. UX/UI Improvements

### 4.1 `web/index.html` (Chat UI)

#### Critical UX Issues

1. **Tidak ada streaming response** — backend sudah punya `/api/chat/stream` (`SSE`), frontend hanya pakai `/api/chat` one-shot. User menunggu 5-30 detik tanpa feedback. **PRD §3.1 eksplisit**: "streaming response (token-by-token) untuk meningkatkan UX".
2. **Conversation history hilang saat reload** — `thread_id` ditampilkan, tetapi refresh browser = blank slate. Tidak ada persistence di frontend.
3. **Tidak ada multi-conversation sidebar** — satu thread per session. User tidak bisa switch antara beberapa klien/topik.
4. **Tidak ada attachment upload** — PRD §FR1 "attachments". Chat hanya menerima text.
5. **Citations tidak dirender** — backend return `citations: list[str]` (`ChatResponse`), UI abaikan. User tidak bisa klik source.
6. **Worker outputs tidak divisualisasikan** — `worker_outputs` berisi status, summary, confidence per worker. UI hanya tampilkan trace string (`trace.join(" → ")`). Padahal ini adalah **core differentiator** multi-agent system.
7. **Approval card minim konteks** — hanya tampilkan `summary`. Compliance officer butuh: risk score, KYC status, client profile, policies referenced, amount, documents.
8. **Tidak ada role-aware feedback** — user pilih role "Advisor" lalu minta "approve this" → error generik, bukan "Permission denied: compliance role required".
9. **API key plaintext di DOM** — `<input id="apiKey" value="bos-local-dev-key-CHANGE-ME">`. Visible di DevTools, terpersist jika "remember" ditambahkan.

#### Functional UX Gaps

10. **Markdown renderer tidak handle tabel** — `renderMarkdown` (`index.html:193`) handle heading/list/code/bold/italic. Composer emit tabel → render sebagai text pecah.
11. **Tidak ada copy-to-clipboard** untuk response asisten.
12. **Tidak ada regenerate / retry button**.
13. **Tidak ada stop button** untuk cancel request yang lama.
14. **Tidak ada typing indicator** real (cuma `spinner` generik).
15. **Suggestion chips static** — tidak adaptif berdasarkan riwayat user.
16. **Tidak ada empty state CTA yang bermakna** (onboarding pertama kali).
17. **Tidak ada keyboard shortcut** (`Cmd+K` for new chat, `Cmd+/` for help).
18. **Mobile responsiveness** — sidebar fixed 280px, break di viewport <600px. Tidak ada hamburger menu.
19. **Tidak ada dark/light theme toggle** (minor, sekarang dark-only).
20. **Tidak ada accessibility** — `aria-label`, keyboard nav, screen reader support minim.

#### UI Polish

21. **Toast notifications** untuk error/success.
22. **Markdown editor** dengan preview (bukan plain textarea).
23. **Slash command** (`/schedule`, `/research`, `/compliance`).
24. **Quick action buttons** per role (Advisor lihat "Open Account"; Compliance lihat "Pending Approvals").

### 4.2 `web/admin.html` (Dashboard)

#### Critical UX Issues

1. **Polling 5 detik membakar Gemini quota** — `setInterval(refreshAll, 5000)` (`admin.html:341`) hit `/api/admin/health` yang panggil `ping_gemini()`. **Bakar 12 Gemini req/menit**. Fix: WebSocket push atau long-polling atau cached health 60s.
2. **Approval decision pakai `prompt()` browser** (`admin.html:300`) — UX terrible. Tidak ada validasi bahwa decider benar-benar punya permission `approval.approve`. Bisa input `advisor@bos.local` → backend accept.
3. **Tidak ada filtering/search** di audit trail, workflows, clients. Audit table bisa ribuan rows, user scroll manual.
4. **Tidak ada pagination** — `limit=100/200` hardcode di API, tidak ada "Load more" atau page navigation.
5. **Tidak ada charts** — KPI section cuma 4 angka static. Tidak ada trend line (workflows/day, approval latency over time, error rate).

#### Missing Views

6. **Tidak ada approval detail modal** — list table, klik row → nothing. Compliance butuh drawer/modal yang menampilkan: full worker outputs, referenced policies, audit timeline, client context, risk breakdown.
7. **Tidak ada document preview/download** — `Generated Documents` tab list path `.txt`, tidak bisa klik untuk preview/download.
8. **Tidak ada client detail/edit view** — clients read-only list. PRD: "Operations: Update CRM" → tidak ada UI.
9. **Tidak ada event creation UI** — calendar tool support `cal_schedule`, tapi admin UI tidak expose formnya.
10. **Tidak ada KB chunk browser** — `/api/admin/kb/stats` hanya tampilkan `chunks` count. Tidak bisa browse chunk, tidak bisa delete chunk, tidak bisa lihat doc_type breakdown.
11. **Tidak ada user management** — admin only view demo directory. Tidak bisa add/edit/disable user, tidak bisa assign role.
12. **Tidak ada config management** — PRD §14: "Admin: Configure agents". Tidak ada UI untuk toggle `APPROVAL_INTENTS`, edit thresholds, edit RBAC matrix, edit tool policy.
13. **Tidak ada audit event detail** — klik row audit → nothing. Reasoning, metadata, tools/documents disembunyikan.
14. **Tidak ada export** — CSV/JSON export audit/workflows untuk compliance review.

#### UX Polish

15. **Realtime updates** via WebSocket (currently polling).
16. **Search dengan filter** (intent, status, agent, date range).
17. **Date range picker** untuk semua table.
18. **Skeleton loader** (currently "Loading..." text).
19. **Dark/light theme toggle**.
20. **Bread crumb / nav history** (sekarang hanya tab switching).
21. **Notification badge** di tab Approvals ketika ada pending baru.
22. **Bulk action** (approve/reject multiple approvals).
23. **Mobile layout** untuk on-call compliance officer.
24. **API key management UI** — generate, rotate, revoke key (currently hardcoded).
25. **Cost/usage dashboard** — token usage per workflow, Gemini API spend tracking.

---

## 5. Prioritas Aksi

### Quick Wins (≤ 1 hari kerja)

| # | Item | File | Dampak |
|---|---|---|---|
| 1 | Hapus API key Gemini dari `.env.example` → ganti `placeholder` | `.env.example:6` | Security |
| 2 | Health endpoint: cache 60s, jangan ping Gemini setiap call | `app/api/admin.py:34` | Hemat kuota Gemini 99% |
| 3 | Dashboard: ubah `setInterval` dari 5s ke 30s | `web/admin.html:341` | Hemat kuota |
| 4 | Fix CORS: ganti `allow_origins=["*"]` jadi whitelist | `app/main.py:75` | Security |
| 5 | Tambah `request timeout` di `graph.invoke` (`asyncio.wait_for 30s`) | `app/api/chat.py:101` | Reliability |
| 6 | Ubah `chat_endpoint` ke `async def` + `await loop.run_in_executor` | `app/api/chat.py:133` | Concurrency |
| 7 | Wire `enforce_tool_policy` di `fan_out_workers_node` | `app/graph.py:91-99` | Security |
| 8 | Hapus dokumen `WebSocket` dari docstring atau implement | `app/api/chat.py:7` | Truth-in-advertising |
| 9 | Schedule `expire_stale_approvals()` via FastAPI startup task | `app/main.py:43` | Approval hygiene |
| 10 | Hapus unused dependencies (`sqlalchemy`, `aiosqlite`, `tenacity`, `tiktoken`) atau gunakan | `requirements.txt` | Cleaner install |

### Medium Wins (1-2 minggu)

| # | Item | Dampak |
|---|---|---|
| 11 | Refactor 3 manager → 1 parameterized manager factory | -200 LOC, easier maintenance |
| 12 | Hapus dead code (`merge_worker_outputs`, `validate_agent_output`, unused memory helpers) atau wire mereka | Code clarity |
| 13 | Tambahkan `structlog.get_logger()` di semua modul (replace stdlib `logging.getLogger`) | Observability |
| 14 | Add LangSmith wiring saat `langsmith_tracing=True` | Tracing |
| 15 | Add retry decorator (`tenacity`) di LLM call | Reliability |
| 16 | Add SSE client di `index.html` (use `/api/chat/stream`) | UX |
| 17 | Render worker outputs + citations di chat UI | UX, transparency |
| 18 | Add tests untuk `/api/chat/stream`, `/api/chat/resume`, `/api/ingest/file` | Coverage |
| 19 | Switch SQLite → PostgreSQL (`audit`, `long_term`, `crm`) | Scalability |
| 20 | Add CI/CD GitHub Actions (lint, test, build) | Deployability |

### Big Bets (Phase 2, 1-3 bulan)

| # | Item | Dampak |
|---|---|---|
| 21 | Real authN (Keycloak/Auth0/OIDC) + per-user API key + JWT | Multi-tenant ready |
| 22 | RBAC enforcement dependency per endpoint | Compliance |
| 23 | AES-256 at rest + KMS-managed keys | Security compliance |
| 24 | Slack/Teams/Email adapters (Phase 1 deliverable!) | PRD compliance |
| 25 | Real CRM (Salesforce), market data (Yahoo Finance), DocuSign, Google Calendar | PRD compliance |
| 26 | Redis cache + Celery/Temporal queue | Scalability to 100 concurrent workflows |
| 27 | True parallel fan-out via LangGraph `Send` | Performance |
| 28 | K8s manifests + HPA + Ingress | Deployability |
| 29 | OpenTelemetry + Prometheus + Grafana stack | Observability |
| 30 | Memory facts extraction + session summarization + retention | PRD FR5 complete |

---

## Lampiran: File Reference Cepat

| Area | File penting |
|---|---|
| Graph topology | `app/graph.py` |
| State schema | `app/state.py` |
| CEO agent | `app/agents/ceo.py` |
| Manager base | `app/agents/managers/_common.py` |
| Approval gate | `app/agents/approval.py` |
| Composer | `app/agents/composer.py` |
| Chat API | `app/api/chat.py` |
| Admin API | `app/api/admin.py` |
| Auth deps | `app/api/deps.py` |
| Security layer | `app/security.py` |
| Audit trail | `app/audit.py` |
| Memory (3 layer) | `app/memory/{short_term,long_term,organizational}.py` |
| Tools (6) | `app/tools/{crm,documents,calendar,compliance,research,retrieval}.py` |
| Workers (6) | `app/agents/workers/*_worker.py` |
| Chat UI | `web/index.html` |
| Admin UI | `web/admin.html` |
| Tests | `tests/{conftest,test_tools,test_security,test_graph,test_api}.py` |
| Docker | `Dockerfile`, `docker-compose.yml` |

---

**Dokumen ini dibuat berdasarkan inspeksi langsung codebase per 2026-07-19.**
**Tidak ada file yang dimodifikasi dalam pembuatan analisis ini.**
