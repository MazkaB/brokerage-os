# Product Requirements Document (PRD)

## Hierarchical Multi-Agent Brokerage Operating System (Phase 1)

**Version:** 1.0
**Status:** Draft (Industry Grade)
**Target Customer:** Brokerage Firms, Financial Advisors, Wealth Managers, Insurance Brokers, Internal Operations Teams
**Primary Technology:** LangGraph + LLM + Human-in-the-loop
**Interaction:** Messaging First (No Voice)

---

# 1. Executive Summary

The Brokerage Operating System (BOS) is an AI-native platform that coordinates multiple specialized AI agents to automate brokerage operations.

Unlike a chatbot, the platform behaves like an organization.

Each agent owns a specific responsibility:

* Client onboarding
* Research
* Compliance
* Portfolio analysis
* CRM
* Documentation
* Scheduling
* Internal approvals

Instead of every agent talking randomly, LangGraph orchestrates the workflow using a hierarchical architecture.

```
                  CEO Agent
                      │
       ┌──────────────┼──────────────┐
       │              │              │
 Portfolio      Compliance      Operations
   Manager         Manager         Manager
       │              │              │
 ─────────────────────────────────────────
      Specialist Worker Agents
```

The system serves financial advisors through messaging platforms such as Slack, Teams, WhatsApp Business, and internal chat.

---

# 2. Business Problem

Brokerage firms face several operational bottlenecks:

* Advisors spend too much time on paperwork.
* Client requests require coordination across multiple departments.
* Compliance reviews slow response times.
* Information is fragmented across CRM, PDFs, emails, spreadsheets, and market data.
* Junior analysts repeatedly perform the same research tasks.

This results in:

* Slow customer response
* Operational costs
* Compliance risks
* Advisor burnout

---

# 3. Vision

Create an AI workforce capable of autonomously handling 80% of brokerage operational tasks while keeping humans responsible for approvals and high-risk financial decisions.

---

# 4. Goals

### Business Goals

* Reduce advisor operational workload by 60%
* Reduce response time from hours to minutes
* Improve compliance consistency
* Increase advisor productivity

### Technical Goals

* Modular multi-agent architecture
* Human approval checkpoints
* Persistent memory
* Fault-tolerant workflows
* Explainable reasoning

---

# 5. Non-Goals (Phase 1)

Not included:

❌ Voice conversation

❌ Real-time trading execution

❌ Portfolio optimization

❌ Automatic financial advice

❌ Autonomous investment decisions

---

# 6. Users

## Primary

### Financial Advisor

Needs

* answer clients quickly
* generate reports
* retrieve documents
* request compliance review

---

### Operations Staff

Needs

* prepare forms
* update CRM
* generate onboarding documents

---

### Compliance Officer

Needs

* review AI recommendations
* approve documentation
* audit AI reasoning

---

### Manager

Needs

* monitor AI performance
* assign tasks
* approve escalations

---

# 7. Core User Journey

Client sends message

↓

Messaging Gateway

↓

CEO Agent

↓

Intent Classification

↓

Manager Agent

↓

Worker Agents

↓

Human Approval (if needed)

↓

Response Generated

↓

CRM Updated

---

# Example

Client:

> I want to open a retirement investment account.

CEO Agent determines:

```
Intent:
Account Opening
```

Delegates to:

```
Operations Manager
```

Operations Manager creates workflow

↓

Worker Agents execute:

✓ Identity Verification

✓ Required Documents

✓ KYC Checklist

✓ AML Screening

↓

Compliance Review

↓

Advisor Approval

↓

Client receives onboarding instructions.

---

# 8. Functional Requirements

## FR1 Messaging Gateway

Supported channels

* Web Chat
* Slack
* Microsoft Teams
* WhatsApp Business API
* Email

Functions

* receive messages
* authenticate users
* conversation history
* attachments

---

## FR2 CEO Agent

Responsibilities

* Understand request
* Identify workflow
* Allocate manager agents
* Resolve conflicts
* Escalate failures

Inputs

```
conversation

memory

user profile

permissions
```

Outputs

```
workflow

manager assignment
```

---

## FR3 Manager Agents

Manager agents coordinate workers.

Example managers

### Portfolio Manager

Coordinates

* Market Research Agent
* Risk Agent
* Performance Agent

---

### Compliance Manager

Coordinates

* AML Agent
* KYC Agent
* Regulatory Agent

---

### Operations Manager

Coordinates

* CRM Agent
* Document Agent
* Scheduling Agent

---

# FR4 Worker Agents

## Research Agent

Functions

* summarize market news
* analyze securities
* compare funds

---

## Document Agent

Functions

* prepare PDFs
* fill forms
* extract information

---

## CRM Agent

Functions

* create clients
* update contacts
* record conversations

---

## Compliance Agent

Functions

* KYC verification
* AML screening
* policy validation

---

## Calendar Agent

Functions

* schedule meetings
* reminders
* follow-ups

---

## Retrieval Agent

Functions

Retrieve information from

* CRM
* PDFs
* Regulations
* Knowledge Base
* Emails

---

# FR5 Memory

Three memory layers

## Short-term

Current conversation

---

## Long-term

Client profile

Investment preference

Past interactions

---

## Organizational Memory

Policies

Compliance rules

Internal documentation

---

# FR6 Human Approval

Approval required when

Investment recommendation

Compliance exception

Document submission

Account opening

High-risk operation

---

# FR7 Audit Trail

Every action records

```
timestamp

agent

reasoning summary

tools

documents

human approval
```

---

# 9. Hierarchical LangGraph Architecture

```
                   CEO Agent
                        │
        ┌───────────────┼───────────────┐
        │               │               │
 Compliance      Operations      Portfolio
   Manager         Manager         Manager
        │               │               │
 ───────────────────────────────────────────
 AML    CRM   Docs   Calendar   Research
 KYC    Email Forms  Reminder   Risk
```

Communication rules

Workers

↓

Managers

↓

CEO

↓

User

Workers never communicate directly with users.

---

# 10. State Machine

```
Receive Message

↓

Intent Detection

↓

Workflow Planning

↓

Task Delegation

↓

Parallel Worker Execution

↓

Merge Results

↓

Approval?

 ↓ Yes

Human Review

↓

Approved

↓

Generate Response

↓

Persist Memory

↓

End
```

---

# 11. LangGraph Design

Nodes

```
Input Node

CEO Agent

Intent Classifier

Manager Nodes

Worker Nodes

Approval Node

Memory Update

Output Node
```

Edges

Conditional

Parallel

Retry

Error Recovery

Human Interrupt

---

# 12. Tools

Each agent can access different tools.

Research

Bloomberg API

Yahoo Finance

SEC Filings

News APIs

CRM

Salesforce

HubSpot

Dynamics

Documents

DocuSign

PDF Parser

OCR

Communication

Slack

Email

WhatsApp

Calendar

Google Calendar

Outlook

Database

PostgreSQL

Vector DB

Redis

---

# 13. Knowledge Base

Sources

Compliance manuals

Investment guidelines

Market research

Company SOPs

Client agreements

Internal wiki

Embedding pipeline

```
PDF

↓

Chunking

↓

Embedding

↓

Vector Store

↓

Retriever
```

---

# 14. Permissions

Advisor

* Read client
* Send messages

Operations

* Update CRM

Compliance

* Approve

Manager

* Override

Admin

* Configure agents

---

# 15. Non-Functional Requirements

Availability

99.9%

---

Average response

<5 sec

---

Parallel execution

Up to 50 worker tasks

---

Security

AES-256 encryption

TLS

RBAC

Audit logging

PII masking

---

Scalability

10,000 conversations/day

100 concurrent workflows

---

# 16. Success Metrics

Business KPIs

Advisor response time ↓70%

Manual paperwork ↓60%

Compliance processing ↓50%

Customer satisfaction >4.7/5

---

AI KPIs

Intent accuracy >95%

Task completion >90%

Tool success >98%

Hallucination <2%

Average workflow latency <15 sec

---

# 17. Example Workflow

## Client Message

> "Can you help me transfer my retirement account?"

CEO Agent

↓

Intent

```
Account Transfer
```

↓

Operations Manager

↓

Parallel Tasks

```
CRM Agent

Document Agent

Compliance Agent

Calendar Agent
```

↓

Compliance approves

↓

Advisor reviews

↓

Client receives:

* Required forms
* Next steps
* Timeline
* Scheduled meeting

---

# 18. Recommended Tech Stack

| Layer               | Technology                                        |
| ------------------- | ------------------------------------------------- |
| Agent Orchestration | LangGraph                                         |
| LLM                 | GPT-5.5 / Claude 4 / Gemini 2.5 Pro               |
| Agent Framework     | LangChain                                         |
| Memory              | LangGraph Memory + PostgreSQL                     |
| Vector DB           | pgvector, Pinecone, or Weaviate                   |
| Database            | PostgreSQL                                        |
| Cache               | Redis                                             |
| Messaging           | Slack API, Microsoft Teams, WhatsApp Business API |
| Authentication      | Auth0 / Keycloak / OAuth2                         |
| Monitoring          | LangSmith + OpenTelemetry + Grafana               |
| Workflow Queue      | Celery / Temporal / Kafka                         |
| Deployment          | Docker + Kubernetes                               |
| Cloud               | AWS / GCP / Azure                                 |

---

# 19. Phase 1 Deliverables

| Deliverable                          | Description                                                               |
| ------------------------------------ | ------------------------------------------------------------------------- |
| Hierarchical LangGraph orchestration | CEO → Manager → Worker architecture with conditional routing and retries  |
| Messaging-first interface            | Web chat plus one enterprise messaging integration (Slack or Teams)       |
| Core specialized agents              | CEO, Operations, Compliance, Research, CRM, Document, Retrieval, Calendar |
| Human-in-the-loop approvals          | Configurable approval gates for compliance-sensitive actions              |
| Memory system                        | Conversation memory, user profiles, and organizational knowledge          |
| RAG pipeline                         | Document ingestion, embeddings, vector search, citation support           |
| Tool integrations                    | CRM, calendar, email, document generation, market data connectors         |
| Audit & observability                | Agent traces, workflow history, LangSmith integration, structured logs    |
| Security foundation                  | RBAC, encryption, secrets management, PII masking                         |
| Admin dashboard                      | Workflow monitoring, agent health, approval queue, performance metrics    |
| Automated testing                    | Agent unit tests, workflow integration tests, regression scenarios        |
| Deployment                           | Dockerized services with CI/CD and Kubernetes-ready manifests             |

This PRD is structured to reflect an enterprise-grade, production-ready multi-agent system that aligns with how large financial institutions design AI orchestration platforms: clear separation of responsibilities, hierarchical coordination, human oversight, auditability, and scalable LangGraph-based execution.


# Product Requirements Document (PRD)

## Hierarchical Multi-Agent Brokerage Operating System (Phase 1)

**Version:** 1.0
**Status:** Draft (Industry Grade)
**Target Customer:** Brokerage Firms, Financial Advisors, Wealth Managers, Insurance Brokers, Internal Operations Teams
**Primary Technology:** LangGraph + LLM + Human-in-the-loop
**Interaction:** Messaging First (No Voice)

---

# 1. Executive Summary

The Brokerage Operating System (BOS) is an AI-native platform that coordinates multiple specialized AI agents to automate brokerage operations.

Unlike a chatbot, the platform behaves like an organization.

Each agent owns a specific responsibility:

* Client onboarding
* Research
* Compliance
* Portfolio analysis
* CRM
* Documentation
* Scheduling
* Internal approvals

Instead of every agent talking randomly, LangGraph orchestrates the workflow using a hierarchical architecture.

```
                  CEO Agent
                      │
       ┌──────────────┼──────────────┐
       │              │              │
 Portfolio      Compliance      Operations
   Manager         Manager         Manager
       │              │              │
 ─────────────────────────────────────────
      Specialist Worker Agents
```

The system serves financial advisors through messaging platforms such as Slack, Teams, WhatsApp Business, and internal chat.

---

# 2. Business Problem

Brokerage firms face several operational bottlenecks:

* Advisors spend too much time on paperwork.
* Client requests require coordination across multiple departments.
* Compliance reviews slow response times.
* Information is fragmented across CRM, PDFs, emails, spreadsheets, and market data.
* Junior analysts repeatedly perform the same research tasks.

This results in:

* Slow customer response
* Operational costs
* Compliance risks
* Advisor burnout

---

# 3. Vision

Create an AI workforce capable of autonomously handling 80% of brokerage operational tasks while keeping humans responsible for approvals and high-risk financial decisions.

---

# 4. Goals

### Business Goals

* Reduce advisor operational workload by 60%
* Reduce response time from hours to minutes
* Improve compliance consistency
* Increase advisor productivity

### Technical Goals

* Modular multi-agent architecture
* Human approval checkpoints
* Persistent memory
* Fault-tolerant workflows
* Explainable reasoning

---

# 5. Non-Goals (Phase 1)

Not included:

❌ Voice conversation

❌ Real-time trading execution

❌ Portfolio optimization

❌ Automatic financial advice

❌ Autonomous investment decisions

---

# 6. Users

## Primary

### Financial Advisor

Needs

* answer clients quickly
* generate reports
* retrieve documents
* request compliance review

---

### Operations Staff

Needs

* prepare forms
* update CRM
* generate onboarding documents

---

### Compliance Officer

Needs

* review AI recommendations
* approve documentation
* audit AI reasoning

---

### Manager

Needs

* monitor AI performance
* assign tasks
* approve escalations

---

# 7. Core User Journey

Client sends message

↓

Messaging Gateway

↓

CEO Agent

↓

Intent Classification

↓

Manager Agent

↓

Worker Agents

↓

Human Approval (if needed)

↓

Response Generated

↓

CRM Updated

---

# Example

Client:

> I want to open a retirement investment account.

CEO Agent determines:

```
Intent:
Account Opening
```

Delegates to:

```
Operations Manager
```

Operations Manager creates workflow

↓

Worker Agents execute:

✓ Identity Verification

✓ Required Documents

✓ KYC Checklist

✓ AML Screening

↓

Compliance Review

↓

Advisor Approval

↓

Client receives onboarding instructions.

---

# 8. Functional Requirements

## FR1 Messaging Gateway

Supported channels

* Web Chat
* Slack
* Microsoft Teams
* WhatsApp Business API
* Email

Functions

* receive messages
* authenticate users
* conversation history
* attachments

---

## FR2 CEO Agent

Responsibilities

* Understand request
* Identify workflow
* Allocate manager agents
* Resolve conflicts
* Escalate failures

Inputs

```
conversation

memory

user profile

permissions
```

Outputs

```
workflow

manager assignment
```

---

## FR3 Manager Agents

Manager agents coordinate workers.

Example managers

### Portfolio Manager

Coordinates

* Market Research Agent
* Risk Agent
* Performance Agent

---

### Compliance Manager

Coordinates

* AML Agent
* KYC Agent
* Regulatory Agent

---

### Operations Manager

Coordinates

* CRM Agent
* Document Agent
* Scheduling Agent

---

# FR4 Worker Agents

## Research Agent

Functions

* summarize market news
* analyze securities
* compare funds

---

## Document Agent

Functions

* prepare PDFs
* fill forms
* extract information

---

## CRM Agent

Functions

* create clients
* update contacts
* record conversations

---

## Compliance Agent

Functions

* KYC verification
* AML screening
* policy validation

---

## Calendar Agent

Functions

* schedule meetings
* reminders
* follow-ups

---

## Retrieval Agent

Functions

Retrieve information from

* CRM
* PDFs
* Regulations
* Knowledge Base
* Emails

---

# FR5 Memory

Three memory layers

## Short-term

Current conversation

---

## Long-term

Client profile

Investment preference

Past interactions

---

## Organizational Memory

Policies

Compliance rules

Internal documentation

---

# FR6 Human Approval

Approval required when

Investment recommendation

Compliance exception

Document submission

Account opening

High-risk operation

---

# FR7 Audit Trail

Every action records

```
timestamp

agent

reasoning summary

tools

documents

human approval
```

---

# 9. Hierarchical LangGraph Architecture

```
                   CEO Agent
                        │
        ┌───────────────┼───────────────┐
        │               │               │
 Compliance      Operations      Portfolio
   Manager         Manager         Manager
        │               │               │
 ───────────────────────────────────────────
 AML    CRM   Docs   Calendar   Research
 KYC    Email Forms  Reminder   Risk
```

Communication rules

Workers

↓

Managers

↓

CEO

↓

User

Workers never communicate directly with users.

---

# 10. State Machine

```
Receive Message

↓

Intent Detection

↓

Workflow Planning

↓

Task Delegation

↓

Parallel Worker Execution

↓

Merge Results

↓

Approval?

 ↓ Yes

Human Review

↓

Approved

↓

Generate Response

↓

Persist Memory

↓

End
```

---

# 11. LangGraph Design

Nodes

```
Input Node

CEO Agent

Intent Classifier

Manager Nodes

Worker Nodes

Approval Node

Memory Update

Output Node
```

Edges

Conditional

Parallel

Retry

Error Recovery

Human Interrupt

---

# 12. Tools

Each agent can access different tools.

Research

Bloomberg API

Yahoo Finance

SEC Filings

News APIs

CRM

Salesforce

HubSpot

Dynamics

Documents

DocuSign

PDF Parser

OCR

Communication

Slack

Email

WhatsApp

Calendar

Google Calendar

Outlook

Database

PostgreSQL

Vector DB

Redis

---

# 13. Knowledge Base

Sources

Compliance manuals

Investment guidelines

Market research

Company SOPs

Client agreements

Internal wiki

Embedding pipeline

```
PDF

↓

Chunking

↓

Embedding

↓

Vector Store

↓

Retriever
```

---

# 14. Permissions

Advisor

* Read client
* Send messages

Operations

* Update CRM

Compliance

* Approve

Manager

* Override

Admin

* Configure agents

---

# 15. Non-Functional Requirements

Availability

99.9%

---

Average response

<5 sec

---

Parallel execution

Up to 50 worker tasks

---

Security

AES-256 encryption

TLS

RBAC

Audit logging

PII masking

---

Scalability

10,000 conversations/day

100 concurrent workflows

---

# 16. Success Metrics

Business KPIs

Advisor response time ↓70%

Manual paperwork ↓60%

Compliance processing ↓50%

Customer satisfaction >4.7/5

---

AI KPIs

Intent accuracy >95%

Task completion >90%

Tool success >98%

Hallucination <2%

Average workflow latency <15 sec

---

# 17. Example Workflow

## Client Message

> "Can you help me transfer my retirement account?"

CEO Agent

↓

Intent

```
Account Transfer
```

↓

Operations Manager

↓

Parallel Tasks

```
CRM Agent

Document Agent

Compliance Agent

Calendar Agent
```

↓

Compliance approves

↓

Advisor reviews

↓

Client receives:

* Required forms
* Next steps
* Timeline
* Scheduled meeting

---

# 18. Recommended Tech Stack

| Layer               | Technology                                        |
| ------------------- | ------------------------------------------------- |
| Agent Orchestration | LangGraph                                         |
| LLM                 | GPT-5.5 / Claude 4 / Gemini 2.5 Pro               |
| Agent Framework     | LangChain                                         |
| Memory              | LangGraph Memory + PostgreSQL                     |
| Vector DB           | pgvector, Pinecone, or Weaviate                   |
| Database            | PostgreSQL                                        |
| Cache               | Redis                                             |
| Messaging           | Slack API, Microsoft Teams, WhatsApp Business API |
| Authentication      | Auth0 / Keycloak / OAuth2                         |
| Monitoring          | LangSmith + OpenTelemetry + Grafana               |
| Workflow Queue      | Celery / Temporal / Kafka                         |
| Deployment          | Docker + Kubernetes                               |
| Cloud               | AWS / GCP / Azure                                 |

---

# 19. Phase 1 Deliverables

| Deliverable                          | Description                                                               |
| ------------------------------------ | ------------------------------------------------------------------------- |
| Hierarchical LangGraph orchestration | CEO → Manager → Worker architecture with conditional routing and retries  |
| Messaging-first interface            | Web chat plus one enterprise messaging integration (Slack or Teams)       |
| Core specialized agents              | CEO, Operations, Compliance, Research, CRM, Document, Retrieval, Calendar |
| Human-in-the-loop approvals          | Configurable approval gates for compliance-sensitive actions              |
| Memory system                        | Conversation memory, user profiles, and organizational knowledge          |
| RAG pipeline                         | Document ingestion, embeddings, vector search, citation support           |
| Tool integrations                    | CRM, calendar, email, document generation, market data connectors         |
| Audit & observability                | Agent traces, workflow history, LangSmith integration, structured logs    |
| Security foundation                  | RBAC, encryption, secrets management, PII masking                         |
| Admin dashboard                      | Workflow monitoring, agent health, approval queue, performance metrics    |
| Automated testing                    | Agent unit tests, workflow integration tests, regression scenarios        |
| Deployment                           | Dockerized services with CI/CD and Kubernetes-ready manifests             |

This PRD is structured to reflect an enterprise-grade, production-ready multi-agent system that aligns with how large financial institutions design AI orchestration platforms: clear separation of responsibilities, hierarchical coordination, human oversight, auditability, and scalable LangGraph-based execution.

Berikut adalah **Product Requirement Document (PRD)** yang detail dan terstruktur untuk pengembangan **Phase 1: Hierarchical Multi-Agent Brokerage OS** menggunakan LangGraph.

Dokumen ini dirancang untuk menjembatani visi bisnis dengan implementasi teknis tingkat tinggi yang dibutuhkan oleh seorang *Senior Agentic AI Engineer*.

---

# Product Requirement Document (PRD)

## Project: Hierarchical Multi-Agent Brokerage OS (Phase 1)

**Version:** 1.0

**Status:** Approved for Development (Phase 1)

**Interface Paradigm:** Messaging-First (Strictly No Voice)

---

## 1. Executive Summary & Objective

Proyek ini bertujuan untuk membangun fondasi (Phase 1) dari **Brokerage Operating System (OS)** masa depan yang digerakkan oleh AI. Sistem ini menggunakan arsitektur *hierarchical multi-agent* berbasis **LangGraph** untuk mengotomatisasi, menganalisis, dan mengeksekusi alur kerja operasional broker (seperti manajemen klien, analisis pasar dasar, dan routing transaksi).

Fokus utama Phase 1 adalah menciptakan arsitektur *stateful* yang stabil, sistem *routing* pesan yang cerdas antar-agen, dan antarmuka berbasis teks (messaging-first) yang responsif tanpa kapabilitas suara (*voice*).

---

## 2. Arsitektur Agen & Hierarki (LangGraph Design)

Sistem akan mengadopsi pola **Supervisor-Worker Topology** menggunakan LangGraph untuk mengelola *state* global dan membagi tugas secara otonom.

```
                  [ User Message ]
                         │
                         ▼
             ┌───────────────────────┐
             │   Supervisor Agent    │◄─── (State Graph)
             └───────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
 ┌──────────────┐┌──────────────┐┌──────────────┐
 │ Worker 1:    ││ Worker 2:    ││ Worker 3:    │
 │ Client/KYC   ││ Market Data  ││ Execution    │
 └──────────────┘└──────────────┘└──────────────┘

```

### 2.1. Agent Roles & Responsibilities

| Nama Agen | Level | Peran / Deskripsi |
| --- | --- | --- |
| **Supervisor Agent** | Router / Manager | Agen utama yang menerima *input* pengguna, menganalisis intensi (*intent*), mendelegasikan tugas ke *Worker Agent* yang sesuai, dan menggabungkan hasil akhir kembali ke pengguna. |
| **Client Intake & KYC Agent** | Worker | Mengelola pengumpulan data profil pengguna, verifikasi dokumen dasar berbasis teks, dan kepatuhan (*compliance*) awal. |
| **Market Data Analyst Agent** | Worker | Mengambil, merangkum, dan menyajikan data pasar, tren, atau status portofolio berdasarkan *query* pengguna. |
| **Order & Execution Agent** | Worker | Menangani simulasi eksekusi transaksi (beli/jual/batal), validasi saldo, dan pencatatan *ledger* internal. |

---

## 3. Fitur Utama & Kebutuhan Fungsional (Functional Requirements)

### 3.1. Messaging-First Interface (Asynchronous & Text-Based)

* **Kebutuhan:** Sistem hanya menerima dan merespons dalam format teks/pesan (Markdown supported).
* **Spesifikasi:**
* Integrasi API berbasis REST/WebSocket untuk mendukung *chat interface*.
* Mendukung *streaming response* (token-by-token) untuk meningkatkan *User Experience* (UX).
* **Strict Constraint:** Sama sekali tidak ada pemrosesan audio/suara (*speech-to-text* atau *text-to-speech*) di Phase 1.



### 3.2. LangGraph State & Memory Management

* **Kebutuhan:** Sistem harus mengingat konteks percakapan lintas agen dan sesi.
* **Spesifikasi:**
* Menggunakan `StateGraph` untuk mendefinisikan transisi antar agen berdasarkan *conditional edges*.
* Implementasi **Short-term Memory** (dalam satu sesi *chat* menggunakan LangGraph Checkpointers seperti PostgreSQL atau Redis).
* Implementasi **Long-term Memory** untuk menyimpan preferensi pengguna yang persisten di database utama.



### 3.3. Human-in-the-Loop (HITL) Triggers

* **Kebutuhan:** Transaksi finansial atau tindakan berisiko tinggi membutuhkan persetujuan manusia.
* **Spesifikasi:**
* LangGraph harus melakukan `interrupt` sebelum *Execution Agent* benar-benar memproses perintah transaksi penting.
* Menyediakan *state* khusus (`awaiting_human_approval`) yang menangguhkan jalannya graf hingga ada *input* konfirmasi dari broker/admin manusia.



---

## 4. Kebutuhan Non-Fungsional (Non-Functional Requirements)

* **Keamanan & Kepatuhan:** Semua data percakapan dan data broker harus dienkripsi (AES-256 saat diam, TLS 1.3 saat transit).
* **Skalabilitas:** Arsitektur LangGraph harus di-deploy secara *stateless* di lingkungan kontainer (Docker/Kubernetes), dengan *state layer* yang dipisahkan ke database eksternal.
* **Determinisme Cerdas:** Meskipun menggunakan LLM untuk penalaran (*reasoning*), transisi antar-agen (routing) harus didukung oleh aturan yang ketat (*hardcoded guardrails*) jika LLM mengalami halusinasi.
* **Latency:** Waktu respons dari *Supervisor Agent* untuk menentukan langkah pertama tidak boleh lebih dari **1.5 detik**.

---

## 5. Cakupan Phase 1 (Scope of Phase 1)

### Termasuk dalam Cakupan (In Scope)

1. Perancangan dan implementasi `StateGraph` dasar dengan 1 Supervisor dan minimal 3 Worker Agents.
2. Implementasi mekanisme *Checkpointing* untuk persistensi sesi *chat*.
3. Pembuatan API Endpoints untuk integrasi ke *frontend chat* pihak ketiga.
4. *Mocking* data pasar dan eksekusi transaksi (belum integrasi ke *live broker backend*).

### Di Luar Cakupan (Out of Scope for Phase 1)

1. Fitur suara, telepon, atau VoIP (*Voice capabilities*).
2. Integrasi ke *live liquidity provider* atau bursa riil.
3. Fitur manajemen dokumen berbasis gambar kompleks (OCR tingkat lanjut).

---

## 6. Alur Pengguna & Transisi Agen (User Flow Example)

> **Skenario:** Pengguna ingin memeriksa portofolio dan membeli saham fiktif ABC.

1. **User:** "Berapa sisa saldo saya, dan tolong belikan saham ABC senilai $1000."
2. **Supervisor Agent:** Menganalisis pesan -> Mendeteksi dua *intent* (Cek Saldo & Eksekusi Transaksi).
3. **Transition 1:** Supervisor mengarahkan *state* ke **Market Data Analyst Agent** untuk menarik data saldo pengguna.
4. **Transition 2:** Setelah saldo kembali ke *state*, Supervisor memeriksa kelayakan dan mengarahkan ke **Order & Execution Agent**.
5. **HITL Interrupt:** Sistem mendeteksi perintah transaksi -> Grafik berhenti (`interrupt`) dan mengirim pesan konfirmasi ke user: *"Apakah Anda yakin ingin membeli saham ABC senilai $1000?"*
6. **User:** "Ya, silakan."
7. **Resume Graph:** Grafik dilanjutkan, transaksi disimulasikan, dan Supervisor memberikan ringkasan akhir berformat teks.

---

## 7. Metrik Keberhasilan (Success Metrics / KPIs)

* **Task Completion Rate (TCR):** $\ge 85\%$ tugas diselesaikan oleh kombinasi agen tanpa kegagalan grafik (*graph crash*).
* **Fallback Rate:** $< 10\%$ pesan pengguna memicu respons *"Maaf, saya tidak mengerti"* dari Supervisor.
* **State Recovery:** $100\%$ sesi *chat* yang terputus di tengah jalan dapat dilanjutkan dari titik *checkpoint* terakhir tanpa kehilangan data konteks.

Secara keseluruhan PRD ini sudah cukup baik untuk level interview, namun jika targetnya adalah **Senior Agentic AI Engineer** (terutama perusahaan yang benar-benar membangun platform multi-agent dengan LangGraph), masih ada beberapa kekurangan penting. PRD saat ini masih sangat **feature-centric**, sedangkan engineer senior biasanya ingin melihat **system design, execution model, orchestration, observability, failure handling, dan evaluation**. Dokumen saat ini mencakup arsitektur dasar dan ruang lingkup proyek dengan baik. 

Berikut saran yang saya rekomendasikan.

---

# 1. Tambahkan Product Scope yang Lebih Jelas

Saat ini PRD belum menjelaskan apa yang dilakukan Phase 1 dibanding Phase 2 dan Phase 3.

Misalnya:

| Phase   | Scope                                          |
| ------- | ---------------------------------------------- |
| Phase 1 | Messaging orchestration + Multi-agent workflow |
| Phase 2 | CRM integration + Portfolio automation         |
| Phase 3 | Autonomous brokerage workflows + Analytics     |

Hal ini membantu engineer memahami prioritas.

---

# 2. Tambahkan System Architecture

Saat ini hanya ada hierarchy agent.

Yang lebih penting justru architecture diagram.

Contoh:

```text
                   User

                     │

          Slack / Teams / Web

                     │

            Messaging Gateway

                     │

             LangGraph Runtime

                     │

      ┌──────────────┴───────────────┐

      │                              │

 State Store                 Memory Service

      │                              │

      └──────────────┬───────────────┘

                     │

             CEO Supervisor

                     │

      ┌──────────────┼───────────────┐

 Portfolio      Compliance      Operations

                     │

             Worker Agents

                     │

          Tool Execution Layer

                     │

 CRM | Email | Calendar | RAG | APIs
```

Ini biasanya yang dicari interviewer.

---

# 3. Tambahkan State Schema

LangGraph selalu memiliki state.

Contoh:

```python
BrokerState

conversation_history

current_user

intent

workflow

active_manager

worker_outputs

tool_calls

approval_status

memory

next_node

errors

retry_count
```

Engineer akan langsung tahu bagaimana graph bekerja.

---

# 4. Tambahkan Graph Execution Rules

Misalnya

```
CEO Agent

↓

Select Manager

↓

Manager

↓

Parallel Workers

↓

Merge

↓

Validation

↓

Human Approval

↓

Persist Memory

↓

Respond
```

Kemudian tambahkan rule.

Misalnya

```
If worker timeout

↓

Retry

↓

Fallback Worker

↓

Escalate

↓

Human
```

---

# 5. Tambahkan Conditional Routing

Misalnya

```text
Intent == Portfolio

↓

Portfolio Manager

Intent == Compliance

↓

Compliance Manager

Intent == Document

↓

Operations Manager
```

Lalu

```
confidence < 0.8

↓

Clarification Agent
```

Ini penting pada LangGraph.

---

# 6. Tambahkan Failure Handling

Saat ini tidak ada.

Padahal production agent wajib punya.

Misalnya

Worker timeout

↓

retry

↓

fallback LLM

↓

cached answer

↓

human escalation

---

LLM hallucination

↓

validator

↓

retry

↓

reject

---

Tool failure

↓

retry

↓

backup API

↓

human

---

Memory corruption

↓

reload checkpoint

---

Supervisor failure

↓

resume graph

---

# 7. Tambahkan Tool Policy

Misalnya

Research Agent

Allowed

✓ Yahoo Finance

✓ Bloomberg

Forbidden

✗ CRM

✗ Calendar

---

CRM Agent

Allowed

✓ Salesforce

✓ Hubspot

Forbidden

✗ Financial Advice

---

Compliance Agent

Allowed

✓ Regulations

✓ AML Database

Forbidden

✗ Investment Recommendation

Ini disebut Tool Permission Matrix.

---

# 8. Tambahkan Memory Strategy

Saat ini hanya

Short

Long

Organization

Masih terlalu abstrak.

Lebih bagus

```
Conversation Memory

↓

Session Summary

↓

Long-term Facts

↓

Semantic Retrieval

↓

Knowledge Base
```

Lalu

Retention policy

TTL

Compression

Summarization

Memory pruning

---

# 9. Tambahkan Evaluation Framework

Ini hampir selalu ditanyakan.

Misalnya

### Intent Accuracy

> 95%

---

Workflow Success

> 92%

---

Tool Success

> 98%

---

Average Cost

<$0.15/workflow

---

Average Tokens

<8000

---

Human Escalation

<5%

---

Approval latency

<30 sec

---

Hallucination

<1%

---

# 10. Tambahkan Agent Contracts

Misalnya

Research Agent

Input

```
query

risk_profile
```

Output

```
summary

citations

confidence

sources
```

---

Compliance

Input

```
documents

user
```

Output

```
approved

reasons

risk

next_step
```

Semua worker sebaiknya punya schema.

---

# 11. Tambahkan Observability

Senior engineer akan langsung mencari ini.

Misalnya

Metrics

* Graph latency
* Agent latency
* Tool latency
* Token usage
* Cost
* Retry count
* Error rate

Tracing

* LangSmith
* OpenTelemetry

Logging

* Structured JSON

---

# 12. Tambahkan Security Section

Saat ini terlalu pendek.

Tambahkan

RBAC

Audit Trail

PII Detection

Secrets Manager

Encryption

Prompt Injection Detection

Tool Sandbox

Output Validation

Compliance

SOC2

GDPR

FINRA

SEC

---

# 13. Tambahkan Sequence Diagram

Misalnya

```text
User

↓

Gateway

↓

Supervisor

↓

Portfolio Manager

↓

Research Agent

↓

Market API

↓

Research Agent

↓

Portfolio Manager

↓

Supervisor

↓

User
```

Ini jauh lebih mudah dipahami.

---

# 14. Tambahkan LangGraph Concepts

Karena pekerjaan secara spesifik meminta LangGraph.

Contoh:

* StateGraph
* Command
* Send
* Interrupt
* Resume
* Checkpointer
* Conditional Edge
* Parallel Branch
* Subgraph
* Human Interrupt
* Durable Execution
* Streaming
* Persistence

Saat ini PRD baru menyebut LangGraph secara umum tanpa menjelaskan fitur-fitur yang akan digunakan. 

---

# 15. Tambahkan Acceptance Criteria

Contoh:

**FR-01 Messaging Gateway**

Acceptance Criteria

* Mendukung minimal 100 concurrent conversations.
* Mendukung streaming response dengan latency awal < 2 detik.
* Semua pesan tersimpan ke state store.
* Attachment PDF hingga 20 MB dapat diproses.

**FR-06 Human Approval**

Acceptance Criteria

* Workflow berhenti pada node `interrupt`.
* Approval dapat dilakukan melalui UI.
* Workflow dapat di-`resume` tanpa kehilangan state.

---

## Penilaian Keseluruhan

Saya akan memberi penilaian sebagai berikut:

| Aspek                          |  Nilai |
| ------------------------------ | -----: |
| Product Thinking               | 9.0/10 |
| Functional Requirements        | 8.5/10 |
| Multi-Agent Design             | 8.5/10 |
| LangGraph Specificity          | 6.5/10 |
| System Design                  | 6.5/10 |
| Production Readiness           | 6.5/10 |
| Reliability & Failure Handling | 5.5/10 |
| Observability                  | 5.0/10 |
| Evaluation Framework           | 5.0/10 |

**Skor keseluruhan: 7.4/10**.

Dengan menambahkan poin-poin di atas—terutama **State Schema**, **Conditional Routing**, **Failure Handling**, **Observability**, **Agent Contracts**, dan **Acceptance Criteria**—dokumen ini dapat meningkat menjadi sekitar **9.5–10/10** untuk konteks interview **Senior Agentic AI Engineer**, karena akan lebih mencerminkan bagaimana sistem LangGraph dibangun dan dioperasikan di lingkungan produksi.
Secara keseluruhan, draf PRD yang Anda bagikan sudah memiliki fondasi bisnis yang kuat. Namun, terdapat **diskrepansi (celah) yang cukup besar** antara draf versi bahasa Inggris (yang sangat detail dan berskala *enterprise*) dengan draf ringkasan versi bahasa Indonesia.

Sebagai sesama kolaborator AI, saya melihat versi bahasa Indonesia terlalu menyederhanakan arsitektur system. Untuk skala *Senior Agentic AI Engineer*, insinyur Anda akan membutuhkan spesifikasi graf dan *state* yang lebih rigid agar tidak salah bangun.

Berikut adalah feedback perbaikan terstruktur untuk meningkatkan kualitas PRD Anda menjadi **Industry-Grade**:

---

## 1. Sinkronisasi Topologi Graf (Hierarchical Architecture)

* **Masalah:** Draf Inggris menyebutkan struktur 3-tier (**CEO Agent $\rightarrow$ Manager Agents $\rightarrow$ Workers**), sedangkan versi Indonesia memotongnya menjadi 2-tier (**Supervisor $\rightarrow$ Workers**).
* **Perbaikan:** Kembalikan ke arsitektur 3-tier jika ini memang untuk sistem *brokerage operating system* yang kompleks. Tentukan dengan jelas di bagian *State Graph* bagaimana token/pesan dioper dari CEO ke Manager (Portfolio/Compliance/Operations) sebelum turun ke Specialist Workers.
* **Rekomendasi Tambahan:** Definisikan *routing rule*-nya. Apakah menggunakan `Conditional Edges` berbasis LLM *Structured Output* (Pydantic) ataukah kombinasi *hardcoded routing* untuk efisiensi biaya dan latensi?

## 2. Spesifikasi "State" LangGraph yang Belum Jelas

* **Masalah:** LangGraph adalah tentang *State Management*. PRD Anda belum mendefinisikan apa saja komponen yang ada di dalam `State` global percakapan.
* **Perbaikan:** Tambahkan sub-bab **Global State Schema**. Seorang engineer harus tahu apakah *state* hanya berisi `messages: Annotated[list, add_messages]` atau memiliki *key* khusus seperti:
* `current_workflow: str`
* `compliance_status: bool`
* `user_permissions: list`
* `pending_approval_data: dict`



## 3. Detail RAG Pipeline & Data Ingestion

* **Masalah:** Sebagai Brokerage OS, sistem akan sering membaca regulasi, dokumen SOP internal, dan data pasar. Di versi Indonesia, komponen **Retrieval Agent** dan skema *Vector Database* (pgvector/Pinecone) malah hilang.
* **Perbaikan:** Masukkan kembali komponen *Knowledge Base* dan jelaskan bagaimana *Retrieval Agent* bekerja (apakah menggunakan teknik *Self-RAG* atau *Corrective RAG* untuk menekan angka halusinasi di bawah **2%** seperti target KPI Anda).

## 4. Perjelas Mekanisme Human-in-the-Loop (HITL)

* **Masalah:** Kebutuhan HITL sudah disebutkan, tetapi cara kerjanya belum dieksplisitkan dari sudut pandang interaksi *messaging-first*.
* **Perbaikan:** Jelaskan *state transition* saat terjadi `interrupt`.
> **Contoh:** Ketika *Execution Agent* terpicu, graf akan melakukan *compile* dengan `checkpointer` dan masuk ke kondisi `interrupt()`. Sistem harus mengirimkan kartu notifikasi (misal via Slack Block Kit atau Teams Adaptive Cards) ke **Compliance Officer** untuk tombol *Approve/Reject*. Setelah diklik, graf baru melakukan `resume`.



## 5. Lengkapi Tech Stack & Matriks Granular

* **Masalah:** Tabel rekomendasi *tech stack* (seperti penggunaan LangSmith untuk observabilitas, Temporal/Celery untuk antrean alur kerja, dan Redis untuk *caching*) yang ada di draf Inggris sangat krusial namun hilang di versi Indonesia.
* **Perbaikan:** Masukkan kembali tabel *Tech Stack* tersebut karena ini menentukan *environment* kerja sang *engineer* (misalnya kepastian memakai ekosistem Python/TypeScript).

---

## Ringkasan Struktur PRD yang Direkomendasikan (Merged & Upgraded)

Jika Anda ingin menyatukannya, susunlah dokumen dengan urutan berikut:

1. **Executive Summary & Business Problem**
2. **System Architecture (CEO $\rightarrow$ Manager $\rightarrow$ Worker Topology Diagram)**
3. **Agent & Tools Specifications** (Definisikan 8 Agen inti beserta API yang diakses seperti Bloomberg, Salesforce, dll.)
4. **LangGraph State & Flow Design** (Termasuk skema *State*, *Short/Long-term Memory*, dan *HITL Interrupt Gates*)
5. **Functional Requirements** (Messaging Gateway, RAG Pipeline, Audit Trail)
6. **Non-Functional Requirements & Security** (RBAC, Latensi $<5$ detik, PII Masking)
7. **Tech Stack & Phase 1 Deliverables**

---
Berikut adalah saran perbaikan untuk **PRD Phase 1 Hierarchical Multi-Agent Brokerage OS** yang Anda susun. Saran ini difokuskan agar PRD lebih tajam, konsisten, dan langsung bisa dieksekusi oleh seorang **Senior Agentic AI Engineer** yang menggunakan LangGraph.

---

### 1. **Konsistensi Arsitektur & Lingkup Phase 1**
**Masalah:**  
PRD menggambarkan tiga lapis agen (CEO → Manager → Worker) dengan banyak spesialisasi, tetapi tabel agen untuk Phase 1 hanya menyebutkan Supervisor + 3 worker (Client/KYC, Market Data, Execution). Ada ketidakselarasan antara visi penuh dan apa yang benar‑benar akan dibangun.

**Saran Perbaikan:**
- **Tegaskan arsitektur target Phase 1:** 1 Supervisor Agent + 3 specialist worker agents (bukan manager agents). Hilangkan referensi ke Compliance Manager, Operations Manager, dll. di bagian yang membahas implementasi detail.
- **Jika ingin mempertahankan visi penuh,** pisahkan bagian “Visi Jangka Panjang” dengan jelas dari “Ruang Lingkup Phase 1”. Gunakan label seperti *(Future Phase)* pada arsitektur bertingkat CEO-Manager-Worker.

---

### 2. **Desain LangGraph yang Lebih Konkret**
**Masalah:**  
Deskripsi State Machine dan “LangGraph Design” masih abstrak. Tidak ada spesifikasi *state schema*, *node*, atau *conditional edges* yang cukup untuk langsung dimplementasikan.

**Saran Perbaikan:**
- **Definisikan `TypedDict` state untuk Supervisor dan tiap worker.** Contoh untuk Supervisor:
  ```python
  class SupervisorState(TypedDict):
      messages: List[BaseMessage]
      intent: Optional[str]
      task_plan: List[SubTask]
      worker_results: Dict[str, Any]  # key: worker_id
      final_response: Optional[str]
      approval_status: Literal["pending", "approved", "rejected"]
  ```
- **Buat diagram transisi spesifik:**  
  - Node: `parse_intent`, `route_to_worker`, `collect_results`, `evaluate_approval`, `finalize`.  
  - Conditional edge: setelah `route_to_worker`, jika semua worker selesai → `collect_results`. Jika ada HITL trigger → `await_approval`.
- **Jelaskan bagaimana worker dipanggil:** Apakah sebagai sub‑graph LangGraph (`StateGraph` terpisah yang dikomposisikan) atau sebagai *tools* yang dipanggil oleh supervisor. Rekomendasikan sub‑graph agar state lebih terisolasi dan mudah diuji.

---

### 3. **Mekanisme Human‑in‑the‑Loop (HITL) yang Rinci**
**Masalah:**  
HITL hanya disebutkan dengan `interrupt` dan state `awaiting_human_approval`, tetapi tidak ada detail tentang bagaimana *interrupt* dipicu, bagaimana user memberikan persetujuan, dan bagaimana graph melanjutkan setelahnya.

**Saran Perbaikan:**
- **Spesifikasikan trigger persetujuan:** Setiap kali *Execution Agent* akan menjalankan transaksi > threshold tertentu (misal $1000), Supervisor mengeset flag `needs_approval=True` dan transisi ke node khusus `request_human_approval`.
- **Definisikan mekanisme resume:** Gunakan LangGraph `interrupt()` lalu simpan `thread_id`. API eksternal (mis. REST) harus bisa menerima `thread_id` dan aksi (`approve`/`reject`) untuk melanjutkan graph via `graph.astream(..., config={"configurable": {"thread_id": ...}})`.
- **Timeout & fallback:** Jika tidak ada respons manusia dalam 30 menit, graph otomatis melanjutkan dengan kebijakan default (misal tolak transaksi) dan mencatat peristiwa tersebut.

---

### 4. **Memory & State Persistence – Detail Implementasi**
**Masalah:**  
Disebutkan short‑term pakai Checkpointer (PostgreSQL/Redis) dan long‑term untuk preferensi, tetapi tidak ada skema konkret atau pemisahan yang jelas.

**Saran Perbaikan:**
- **Short‑term (Conversation):** Gunakan LangGraph `SqliteSaver` (untuk dev) atau `PostgresSaver` (untuk production). Simpan seluruh `SupervisorState` serialized per `thread_id`.
- **Long‑term (User Profile):** Definisikan tabel `user_profile` dengan kolom: `user_id`, `risk_tolerance`, `preferred_markets`, `kyc_status`. Supervisor membaca ini di awal percakapan dan memperbarui setelah ada perubahan.
- **Organizational Memory (RAG):** Sederhana saja di Phase 1 – gunakan FAISS atau Chroma untuk menyimpan potongan teks kebijakan. Worker *Retrieval* akan mengaksesnya via tool `search_knowledge_base`.

---

### 5. **Strategi Pengujian (Testing)**
**Masalah:**  
PRD hanya menyebutkan “automated testing” tanpa spesifikasi. LangGraph memerlukan pengujian node, transisi, dan integrasi.

**Saran Perbaikan:**
- **Unit Test:** Uji setiap *node* secara terisolasi (mis. `parse_intent` dengan berbagai input) menggunakan mock LLM call.
- **Integration Test:** Jalankan seluruh graph dengan LangGraph `test_mode` dan periksa state akhir. Contoh: input “Beli saham ABC”, periksa state `approval_status == "pending"`.
- **Regression Scenarios:** Definisikan 10 skenario inti (seperti di bagian contoh alur) dan pastikan semuanya lulus sebelum rilis.

---

### 6. **Keamanan & Kepatuhan di Phase 1 – Batasi dengan Jelas**
**Masalah:**  
Mencantumkan enkripsi AES‑256, RBAC, PII masking, dan berbagai standar tanpa konteks bahwa ini adalah phase awal dengan data simulasi. Ini bisa menghabiskan waktu dan sumber daya.

**Saran Perbaikan:**
- **Batasi keamanan menjadi “security foundation” saja:** Gunakan API key sederhana untuk endpoint, HTTPS, dan pastikan tidak ada data asli yang digunakan. Masking PII bisa disimulasikan.
- **Catat dengan jelas** bahwa implementasi RBAC penuh, audit trail lengkap, dan enkripsi data at‑rest akan dilakukan di Phase 2 ketika sudah terhubung ke data klien riil.

---

### 7. **Kinerja & Metrik – Penyesuaian Realistis**
**Masalah:**  
Target latensi bervariasi: di satu bagian <1.5 detik untuk langkah pertama supervisor, di lain <5 detik rata‑rata, dan <15 detik untuk workflow kompleks. Tidak jelas mana yang diukur di Phase 1.

**Saran Perbaikan:**
- **Tetapkan KPI Phase 1 yang tunggal:**  
  - *Time‑to‑First‑Response (TTFR):* < 2 detik (dari pesan user sampai supervisor mengidentifikasi intent dan mengirimkan acknowledgement).  
  - *Workflow Completion Time (WCT):* < 8 detik untuk skenario sederhana tanpa HITL (contoh: cek saldo).  
- Tambahkan catatan bahwa angka ini dengan asumsi LLM latency ~500‑800 ms dan tanpa beban tinggi. Uji dengan 10 percakapan konkuren.

---

### 8. **Tools & Integrasi – Bedakan Real vs. Mock**
**Masalah:**  
Daftar tools sangat panjang (Bloomberg, Salesforce, DocuSign, dll.) dan akan memberi kesan bahwa semuanya harus terintegrasi di Phase 1.

**Saran Perbaikan:**
- **Buat tabel terpisah:**  
  - **Phase 1 – Simulated Tools:** Market Data (mock API), CRM (dictionary in‑memory), Document (string templates).  
  - **Future Integration Targets:** Bloomberg, Salesforce, dll. (cukup disebut sebagai rencana).  
- Dengan ini, engineer bisa fokus pada orkestrasi agen, bukan integrasi eksternal yang kompleks.

---

### 9. **Error Handling & Fallback – Perkuat Ketahanan Graph**
**Masalah:**  
Fallback rate <10% disebut, tetapi tidak ada mekanisme untuk menangani kegagalan worker, LLM error, atau timeout.

**Saran Perbaikan:**
- **Definisikan *retry policy*:** Jika worker gagal karena error sementara (misal LLM rate limit), supervisor node melakukan `retry` maksimal 2 kali sebelum menyatakan task gagal.
- **Supervisor fallback node:** Jika seluruh task plan gagal atau intent tidak terdeteksi, graph mengarahkan ke node `fallback_response` yang memberikan pesan sopan dan menawarkan bantuan manusia.
- **Circuit breaker:** Jika worker tertentu gagal 3 kali berturut‑turut, nonaktifkan sementara dan catat di log.

---

### 10. **Dokumentasi & Asumsi Teknis**
**Masalah:**  
PRD tidak mencantumkan asumsi kunci (mis. versi LangGraph, model LLM yang dipakai, dependensi eksternal). Seorang engineer senior butuh ini untuk memulai.

**Saran Perbaikan:**
- **Tambahkan bagian “Asumsi & Dependensi Teknis”** di akhir PRD, mencakup:
  - LangGraph versi 0.2.x dengan Python 3.11+
  - LLM default: GPT-4o mini (untuk cost efficiency) atau Claude 3.5 Sonnet
  - Message broker opsional (jika worker berkomunikasi async via message queue, sebutkan NATS/Redis)
  - Checkpointer: PostgreSQL (dev: SQLite)
- **Sebutkan bahwa semua komunikasi antar agen dilakukan melalui LangGraph state channel (shared state), bukan message broker terpisah**, kecuali jika diperlukan untuk decoupling penuh.

---

### Ringkasan Prioritas Perbaikan
1. **Perjelas arsitektur aktual Phase 1** dengan 1 supervisor + 3 worker.
2. **Buat spesifikasi state dan transisi LangGraph** dalam bentuk skema dan diagram.
3. **Rincikan HITL** dengan trigger, resume, dan timeout.
4. **Pisahkan alat simulasi** dari target integrasi nyata.
5. **Tetapkan metrik kinerja yang konsisten** dan uji beban.
6. **Perkuat penanganan error** agar graph tidak crash.
7. **Tambahkan asumsi teknis** agar engineer bisa langsung memulai.