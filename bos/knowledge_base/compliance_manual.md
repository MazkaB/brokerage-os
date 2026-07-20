# Compliance Manual (Phase 1 - Sample)

> Source: BOS Organizational Knowledge Base. Used by the Retrieval Worker
> to ground compliance answers in real policy text (RAG).

## 1. KYC (Know Your Customer)

Every new brokerage client must complete KYC verification before any of
the following actions can be performed:

- Opening a new account
- Transferring assets between institutions
- Executing the first trade on a new account

### Required documents
1. Government-issued photo ID (passport, driver's license, or national ID)
2. Proof of address (utility bill, bank statement, lease agreement) dated within the last 90 days
3. Tax Identification Number (SSN, ITIN, or EIN for entities)
4. Source-of-funds declaration for any deposit > $10,000

### KYC decision matrix
- All four items present and valid → **approved**
- Missing or expired documents → **pending**, request resubmission
- Documents flagged as fraudulent → **rejected**, escalate to AML

## 2. AML (Anti-Money Laundering)

The AML screening pipeline performs the following checks in order:

1. **Sanctions screening** against OFAC SDN, EU consolidated, and UN lists
2. **PEP (Politically Exposed Person)** screening
3. **Country risk** scoring using the firm's high-risk jurisdiction list
4. **Transaction pattern** analysis for structuring / layering indicators

### Risk score interpretation
- **0.00 - 0.24**: Low risk → proceed with standard onboarding
- **0.25 - 0.49**: Medium risk → enhanced due diligence (EDD) required
- **0.50 - 0.79**: High risk → senior compliance officer review required
- **0.80 - 1.00**: Critical → reject onboarding and file SAR

## 3. Account Opening Policy

All new accounts require human approval from a Compliance Officer before
the account is activated, regardless of KYC/AML outcomes. This is a
hard rule and cannot be overridden by the AI workforce.

Approval timeout: 30 minutes. After timeout, the workflow expires and
must be re-initiated.

## 4. Account Transfer Policy (ACATS)

Account transfers follow the same KYC and AML requirements as account
opening. In addition:

- The delivering firm must be a valid DTC participant
- Partial transfers require explicit asset list
- Full transfers require written authorization with wet signature

## 5. Trade Execution Policy

Automated trade execution is **disabled** in Phase 1. The Order &
Execution Worker is read-only and may only simulate execution.

For Phase 2, automated trades will be permitted under these conditions:
- Client has signed the discretionary trading agreement
- Trade amount ≤ $1,000 → no human approval needed
- Trade amount > $1,000 → human approval required
- Trade amount > $50,000 → senior officer + risk committee approval

## 6. Record-keeping

All client interactions, compliance decisions, and workflow traces are
retained for **7 years** per SEC Rule 17a-4 and FINRA Rule 4511.
