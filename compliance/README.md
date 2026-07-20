# BOS Compliance Documentation

This directory maps BOS Phase 2 controls to standard regulatory frameworks.
**BOS is not certified** — these documents describe *which* controls are
implemented and where, so a future audit/QSA can verify them.

| Framework | Document | Status |
|-----------|----------|--------|
| SOC 2 Type II | `SOC2.md` | Control mappings documented |
| FINRA | `FINRA.md` | Rule-by-rule compliance map |
| SEC | `SEC.md` | Rule 17a-4 + Rule 15c2-1 mapping |

## Summary of in-product controls

- **Access control (CC6.1)**: API-key auth + RBAC (5 roles)
- **Audit logging (CC7.2)**: every agent/node event recorded with 6 PRD fields
- **Encryption in transit**: TLS via reverse proxy (recommended Caddy/nginx)
- **Encryption at rest**: AES-256 envelope encryption (`app/crypto.py`)
- **PII detection**: regex-based masking in audit logs
- **Change management**: CI/CD pipeline gates releases on test pass
- **Vulnerability management**: `pip-audit` runs in CI
- **Incident response**: structured logs exportable to SIEM via OpenTelemetry
- **Data retention**: configurable TTL (`app/memory/pruning.py`)
- **Backup**: persistent volumes for SQLite/ChromaDB; Postgres backup is the
  operator's responsibility (BOS does not perform DB backups itself)
