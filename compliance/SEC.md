# SEC Compliance Map

**Document type:** Rule mapping (not a regulatory filing)
**Last updated:** 2026-07-20

---

## Rule 17a-3 — Records to Be Made by Certain Exchange Members, Brokers and Dealers

| Required record | BOS Control | Where |
|-----------------|-------------|-------|
| (a)(4) Customer account info | `user_profiles` table;KYC verification via Compliance Worker | `app/memory/long_term.py`, `app/tools/compliance.py` |
| (a)(5) Ledger | Recommended at operator via accounting system; BOS exports account_opening events | `app/audit.py` |
| (a)(6) Order ticket | Phase 2 Order & Execution Worker is read-only (no live trading in Phase 1) | PRD §5 |

## Rule 17a-4 — Preservation of Records

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Retention period: 3-6 years (depending on record type) | Default retention: 365 days live + 7 years archive | `app/memory/pruning.py` |
| Non-rewriteable / non-erasable (WORM) | Recommended at operator: WORM storage (AWS S3 Object Lock, GCP Bucket Lock) | (operator) |
| Reproducible format | All BOS data is text/JSON, fully searchable via SQL + RAG | `app/audit.py`, ChromaDB |

## Rule 15c3-3 — Customer Protection Rule

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| segregation of customer funds | Out of scope — handled by custodian bank (operator integration) | (operator) |

## Rule 15c3-4 — Written Supervisory Procedures (TCP)

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Documented procedures | Stored in KB: `knowledge_base/operations_sop.md` | repo |
| Annual review | Out of BOS scope | (operator) |

## Rule 17a-14 — Annual Risk Assessment

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Documented risks | `SECURITY_AUDIT.md` covers 22 issues, severity-ranked | repo root |
| Mitigation plan | Per-finding remediation section | same |

## Regulation S-P — Privacy of Consumer Financial Information

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Privacy notices | Out of scope (operator legal team) | — |
| Safeguards against unauthorized access | RBAC, API-key auth, AES-256 at rest, PII masking | `app/security.py`, `app/crypto.py` |
| Opt-out mechanism | Out of BOS scope | — |

## Regulation S-ID — Identity Theft Red Flags

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Identity verification | KYC Worker enforces gov_id + address_proof + dob | `app/tools/compliance.py` |
| Suspicious activity detection | AML risk scoring flags high-risk clients | `app/tools/compliance.py` |
| Change of address follow-up | Out of scope (operator workflow) | — |

---

## What BOS Provides

- Audit trail: every workflow, every approval decision, every worker output
- Encrypted storage of sensitive fields via envelope encryption
- Configurable retention windows
- Structured logging for SIEM ingestion
- Tool-permission matrix to prevent unauthorized data access by agents

## What BOS Does NOT Provide

- Real trading execution (Phase 1 non-goal)
- Direct EDGAR / CRD filing
- Direct SEC correspondence tracking
- Fingerprinting of associated persons

These are operator responsibilities; BOS can support them via export.
