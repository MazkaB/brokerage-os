# SOC 2 Type II — Control Mapping

**Document type:** Readiness assessment (not certification)
**Last updated:** 2026-07-20
**Auditor target:** AICPA-aligned CPA firm (e.g. Schellman, Prescient)

---

## Trust Service Criteria

### CC1 — Control Environment

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC1.1 Board / mgmt establishes integrity | Out of scope for software vendor | Operator |
| CC1.5 Accountability | Every agent action recorded with `agent` field in `audit_events` | `app/audit.py` |
| CC1.6 HR / personnel | Out of scope | Operator |

### CC2 — Communication and Information

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC2.1 Internal communication | Structured JSON logs (`structlog`) + OpenTelemetry traces | `app/logging_setup.py`, `app/otel.py` |
| CC2.2 External communication | API responses (JSON), WebSocket events, Slack messages | `app/api/*` |
| CC2.3 System reports | Admin dashboard + `/api/admin/metrics` endpoint | `web/admin.html` |

### CC3 — Risk Assessment

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC3.1 Risk identification | Documented in `SECURITY_AUDIT.md` (22 findings) | repo root |
| CC3.4 Risk mitigation | Critical findings patched, regression tests | `tests/test_security_fixes.py` |

### CC4 — Monitoring Activities

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC4.1 Ongoing evaluation | Background approval-expiry loop, memory pruning loop | `app/main.py`, `app/memory/pruning.py` |
| CC4.2 Deficiencies evaluated | Workflow errors counted via OpenTelemetry counters | `app/otel.py` |

### CC5 — Control Activities

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC5.1 Technology controls | Worker retry, circuit-breaker-ready, rule-based LLM fallback | `app/graph.py`, `app/agents/base.py` |
| CC5.2 Policy deployment | Tool permission matrix, RBAC enforced at API layer | `app/config.py`, `app/security.py` |
| CC5.3 segregation of duties | Roles: advisor (read), operations (write), compliance (approve), manager (override), admin | `app/security.py:ROLE_PERMISSIONS` |

### CC6 — Logical and Physical Access

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC6.1 Logical access | API-key auth, `hmac.compare_digest` (timing-safe) | `app/security.py:authenticate_api_key` |
| CC6.2 User auth | OAuth2/JWT recommended at operator gateway; BOS supports API-key for service-to-service | `app/security.py` |
| CC6.3 Role restrictions | 5-role RBAC matrix, per-endpoint permission checks | `app/security.py`, `app/api/*` |
| CC6.6 Physical access | Out of scope | Operator / cloud provider |

### CC7 — System Operations

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC7.1 Infrastructure mgmt | Dockerfile, docker-compose, K8s manifests | `Dockerfile`, `deploy/k8s/` |
| CC7.2 Incident detection | Structured logs, OTel traces, error rate dashboards | `deploy/grafana/bos-dashboard.json` |
| CC7.3 Incident response | OpenTelemetry export to SIEM (Datadog/Honeycomb) | `app/otel.py` |
| CC7.4 Recovery | LangGraph checkpointer + archive tables (7-year retention) | `app/memory/pruning.py` |

### CC8 — Change Management

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC8.1 Change authorization | GitHub Actions CI gates on test pass | `.github/workflows/ci.yml` |

### CC9 — Risk Mitigation

| Criterion | BOS Control | Where |
|-----------|-------------|-------|
| CC9.1 Vendor mgmt | Dependency manifest (`requirements.txt`) + `pip-audit` in CI | CI workflow |
| CC9.2 Business continuity | Persistent volumes + archive tables; multi-region dep. planned | `deploy/k8s/` |

---

## Additional Criteria

### Availability

- 99.9% target (operator SLA)
- HPA auto-scales on CPU
- Stateless FastAPI workers + shared state in Postgres / Chroma

### Confidentiality

- AES-256 at rest (`app/crypto.py`) with KMS-wrapped envelope keys
- TLS in transit via operator reverse proxy
- PII masking applied to every audit log entry

### Processing Integrity

- Every workflow has deterministic fallback paths (LLM-down → rule-based)
- Token/cost metrics auditable per call
- Approval gates block high-risk actions

### Privacy

- PII detection: email, SSN, phone, IBAN, credit card, IP, account number
- Data retention: configurable TTL per data type
- Right to erasure: `DELETE FROM user_profiles WHERE user_id=?` + cascade
