# FINRA Compliance Map

**Document type:** Rule mapping (not a regulatory filing)
**Last updated:** 2026-07-20

---

## Rule 3110 — Supervision

| Requirement | BOS Control | Where |
|-------------|-------------|-------|
| Written supervisory procedures | Stored as policy docs in the KB; retrievable via Retrieval Worker | `knowledge_base/operations_sop.md` |
| Review of correspondence | All inbound/outbound messages recorded in `crm_conversations` table | `app/tools/crm.py` |
| Escalation of exceptions | Workflow errors and policy violations are flagged in audit trail with `policy_violation: true` | `app/graph.py:fan_out_workers` |

## Rule 4511 — General Recordkeeping

| Requirement | BOS Control | Where |
|-------------|-------------|-------|
| Records preserved for 6 years (minimum) | `archive_audit_events` table with 7-year retention default | `app/memory/pruning.py:ARCHIVE_RETENTION_DAYS` |
| Records in non-rewriteable, non-erasable format | Recommended: enable Postgres `pg_repack` + WORM storage at operator | (operator) |

## Rule 2010 — Standards of Commercial Honor

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Just and equitable principles | Composer prompt forbids personalized investment advice | `app/agents/composer.py:COMPOSE_SYSTEM_PROMPT` |
| Misleading statements | Research Worker pulls data from tools (not LLM generation); hallucination rate measured by eval harness | `bos/eval/runner.py` |

## Rule 2111 — Suitability

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Document client risk profile | `user_profiles.risk_tolerance` field, surfaced in `user_profile` state | `app/memory/long_term.py` |
| Reasonable-basis suitability | Composer includes risk profile in response payload | `app/agents/composer.py` |

## Rule 3210 — Outside Accounts

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Account transfer tracking | `account_transfer` intent + ACATS document template | `app/config.py:APPROVAL_INTENTS`, `app/tools/documents.py:_TEMPLATES` |

## Rule 3310 — AML Compliance Program

| Requirement | BOS Control | Where |
|-----------|-------------|-------|
| Written AML program | Stored in KB; `compliance_manual.md` section 2 | `knowledge_base/compliance_manual.md` |
| Customer Identification Program | KYC Worker enforces required fields (gov_id, address_proof, dob) | `app/tools/compliance.py:run_kyc` |
| Suspicious Activity Reports | Flagged when AML risk score ≥ 0.5 | `app/tools/compliance.py:run_aml` |

---

## Ongoing Obligations

- Annual AML training (out of BOS scope; operator)
- Quarterly review of compliance audit trail via admin dashboard
- Annual penetration test (out of BOS scope; operator)

## What BOS Does NOT Provide

- Fingerprinting / background checks of associated persons
- U4/U5 filing with CRD
- SmartIVR / phone call recording with automated supervision
- Direct integration with FINRA gateway

These are operator responsibilities that BOS can support via audit log export.
