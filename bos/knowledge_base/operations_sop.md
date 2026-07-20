# Operations Standard Operating Procedure (Phase 1 - Sample)

> Source: BOS Organizational Knowledge Base. Referenced by the Operations
> Manager and CRM/Document/Calendar Workers.

## 1. New Client Onboarding Workflow

1. **Intake**: Capture prospect details (full name, email, phone, target account type)
2. **KYC**: Submit prospect info to Compliance Worker for KYC verification
3. **AML**: Submit prospect info to Compliance Worker for AML screening
4. **Document preparation**: Generate the appropriate account opening form
5. **Compliance approval**: Wait for human Compliance Officer approval
6. **CRM activation**: Once approved, set client status to `active`
7. **Welcome**: Send welcome packet and schedule kickoff meeting

## 2. Account Transfer Workflow

1. Capture source institution name and account number
2. Capture target account (existing client or new)
3. Capture list of assets to transfer
4. Generate ACATS form
5. Submit to Compliance for approval
6. On approval, log transfer request with expected settlement in 5-7 business days

## 3. Meeting Scheduling Rules

- Default meeting length: 30 minutes
- Default reminder: 24 hours before
- All meetings require at least one internal attendee
- Client-facing meetings must be scheduled during business hours (09:00-17:00 client local time)

## 4. Client Communication Standards

- All responses to clients go through the CEO agent
- Workers never communicate directly with clients
- All client-facing text must be PII-masked in audit logs but full text in delivery
- Sensitive financial advice must include the disclaimer: "This is general information, not personalized financial advice."

## 5. Document Templates

Available document templates in Phase 1:
- `account_opening` - new brokerage account form
- `account_transfer` - ACATS transfer form
- `kyc_checklist` - KYC verification checklist
- `compliance_review` - compliance review memo

## 6. Escalation Policy

- Worker failure → retry once → escalate to manager
- Manager failure → escalate to CEO
- CEO failure → respond with apology + offer human handoff
- All escalations are logged to the audit trail
