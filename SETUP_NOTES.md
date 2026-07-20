# Setup Notes & Manual Actions Required

## ⚠️ Action required from you

### 1. Gemini API Key (CRITICAL)

The Gemini API key shared in the original chat was **auto-revoked by Google**
because shared API keys are detected as "leaked" and disabled automatically.
**The key has been removed from all tracked files.**

**What to do:**
1. Open https://aistudio.google.com/app/apikey
2. Click **Create API key** (use the free tier — it's enough for dev/demo)
3. Put the value **only** in `bos/.env` (which is gitignored):
   ```
   GEMINI_API_KEY=YOUR_NEW_KEY_HERE
   ```
4. **Never** paste a real API key into `.env.example`, README, or chat —
   keep secrets out of version control entirely.

**Good news:** The system is built with **graceful degradation**. Even with
the API key currently dead, the system still:
- Classifies intents (rule-based fallback classifier)
- Plans workers (deterministic fallback planner)
- Runs all 6 worker agents with full tool functionality
- Composes responses from worker data
- Persists audit trail and supports HITL approvals

Once you provide a working key, all those layers upgrade to LLM-driven
quality automatically. No code changes needed.

---

## ✅ What's already done (no action needed)

| Step | Status |
| ---- | ------ |
| Python dependencies installed | ✓ (langgraph 0.2.76, langchain 0.3.30, chromadb 0.5.23, etc.) |
| Database schema initialized | ✓ (SQLite at `bos/app/data/bos.db`) |
| Knowledge base ingested | ✓ (10 chunks across 3 sample docs in ChromaDB) |
| 50 automated tests written & passing | ✓ |
| Web chat UI (`/`) | ✓ |
| Admin dashboard (`/admin`) | ✓ |
| Swagger docs (`/docs`) | ✓ |
| Docker setup | ✓ (Dockerfile + docker-compose.yml) |

---

## 🚀 How to start the system

```bash
cd bos
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open in your browser:
- **Chat UI**: http://localhost:8000
- **Admin**: http://localhost:8000/admin
- **API docs**: http://localhost:8000/docs

The API key used by the UI is pre-filled (`bos-local-dev-key-CHANGE-ME`).
Change `BOS_API_KEY` in `.env` for any non-dev usage.

---

## 📋 Things to try in the UI

### Chat UI
1. Pick a user role from the sidebar (Advisor / Operations / Compliance / Manager / Admin)
2. Try these prompts:
   - "Hi, what can you do?" — general greeting path
   - "Show my recent clients" — Operations → CRM Worker
   - "Summarize AAPL and TSLA" — Portfolio → Research Worker
   - "What are our KYC requirements?" — Compliance → Retrieval + Compliance Workers
   - "Open a new retirement account for Jane Doe" — Operations + Compliance → **HITL interrupt** (you'll get Approve/Reject buttons inline)
3. Notice the workflow trace shown above each response

### Admin Dashboard
- **KPIs** at top: live status, pending approvals, active workflows
- **Approvals tab**: approve/reject pending requests
- **Workflows tab**: every workflow with intent, manager, workers used
- **Audit Trail tab**: every agent event with timestamp + reasoning
- **Knowledge Base tab**: ingest new docs (text/file), test semantic search

---

## 🔧 If Gemini quota hits during use

The free tier has these limits:
- `gemini-2.5-flash`: 20 requests/day on free tier (very low!)
- `gemini-embedding-001`: 1500 requests/day

For real testing, either:
1. Upgrade to a paid tier at https://ai.google.dev/pricing
2. Or rely on the rule-based fallback (it works fine for demo purposes;
   responses will just be less polished)

To verify the fallback is active, check the audit trail — events with
`fallback=True` in metadata used the rule-based path.
