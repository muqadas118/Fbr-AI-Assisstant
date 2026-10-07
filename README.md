# FBR AI Tax & Compliance Assistant

A production-grade, **RAG-powered AI assistant** for Pakistan's Federal Board of Revenue (FBR) tax and compliance work. It answers tax queries with grounded, cited answers drawn from the official FBR law corpus, runs 11 tax calculators, analyzes FBR notices, tracks filing deadlines, verifies NTNs/CNICs, analyzes documents and invoices, and gives every user a Personal or Business compliance workspace.

Built for tax professionals, accountants, businesses and individual taxpayers who need *evidence-led* answers — not generic chat.

---

## Table of Contents

- [What this project does](#what-this-project-does)
- [Key features](#key-features)
- [How it works — RAG + agent routing](#how-it-works--rag--agent-routing)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Auth, email confirmation & workspaces](#auth-email-confirmation--workspaces)
- [API overview](#api-overview)
- [The FBR knowledge corpus](#the-fbr-knowledge-corpus)
- [Testing](#testing)
- [Deployment](#deployment)
- [Known limitations](#known-limitations)

---

## What this project does

The platform ingests official FBR source documents (laws, ordinances, rules, SROs, FAQs), chunks and embeds them into a hybrid retrieval index, and routes every user question through **9 specialized domain agents**. Each agent retrieves relevant law, produces an answer with **section-level citations**, and runs a **verification layer** that rejects answers that are not grounded in source evidence.

Beyond Q&A it is a full compliance tool:

- **11 tax calculators** — deterministic local math (no LLM, no latency, no API cost).
- **Notice analyzer** — understands 30+ FBR notice types, deadlines, action plans, appeals.
- **Compliance calendar** — FY 2024–27 filing deadlines with reminders and a compliance score.
- **Tax health engine** — score, risk analysis, penalty estimation, recommendations.
- **Document & invoice intelligence** — classify, extract, validate, reconcile.
- **Verification center** — NTN, CNIC, filer status, Active Taxpayer List (ATL), vendor checks.
- **FBR monitor** — notice events with inbox, acknowledge/resolve workflows.
- **Business reports** — generated overviews (markdown, downloadable).
- **Workspaces** — Personal and Business, allocated via a signup questionnaire.

---

## Key features

### 1. Grounded Q&A (RAG)
- Hybrid retrieval: **semantic embeddings (sentence-transformers `all-MiniLM-L6-v2` → FAISS)** + **BM25 keyword search**, fused and re-ranked.
- Every answer carries `sources` with document, section reference, page, law tag and scores.
- **Verification panel**: answer-size, section-consistency, grounding and speculation checks; ungrounded queries get a clear refusal instead of hallucinated law.

### 2. 9-agent domain routing
Single-domain question → exactly one agent. Multi-domain question → every routed domain runs, and per-domain answers are concatenated (never invented or merged). The response reports `grounded: true` only when **every** routed domain is grounded.

| Domain agent | Handles |
|---|---|
| `income_tax` | Income Tax Ordinance 2001, salary/business income, deductions |
| `sales_tax` | Sales Tax Act 1990, registration, returns, ITC |
| `federal_excise` | Federal Excise Act 2005, rates, registration |
| `customs` | Customs Act 1969, valuation, duties, procedures |
| `registration` | NTN / STRN registration, activation, deactivation |
| `return_filing` | Returns, deadlines, late-filing consequences |
| `calculation` | Runs the deterministic calculation engine behind answers |
| `notice_appeal` | FBR notices, appeals, timelines, forums |
| `research` | General FBR law research and cross-references |

### 3. Tax calculation engine (11 modules)
Deterministic, dependency-free math with an audit trail:

`income_tax` · `salary_tax` · `business_tax` · `sales_tax` · `withholding_tax` · `federal_excise` · `capital_gains` · `property_tax` · `dividend_tax` · `custom_duty` · `custom_calc`

### 4. Auth & onboarding
- **First-party auth**: PBKDF2 password hashing + opaque 24h session tokens.
- **Persistent accounts**: users are stored in `data/auth_users.json` (git-ignored), so accounts **survive backend restarts**.
- **Supabase dual-path**: the same protected endpoints accept Supabase JWTs; unconfirmed identities are rejected until `email_confirmed_at` is present (confirmation emails come from Supabase).
- **Onboarding questionnaire**: 4 professional questions → weighted recommendation → final workspace choice (**explicit click always wins**).

### 5. Personal & Business workspaces
- Questionnaire allocates the primary workspace (`preferred_workspace`).
- Login lands in the correct workspace; cross-workspace deep links redirect to the allocated workspace.

### 6. Responsive UI
- React + TypeScript + Vite SPA with a government-style design system.
- Landing page with hero CTA, particle background, responsive header (390px-tested), SPA-linked quick actions.

---

## How it works — RAG + agent routing

```
User question
      │
      ▼
┌─────────────────┐     ┌──────────────────────────┐
│ Query           │ ──► │ Agent oracle / router    │
│ understanding   │     │ (intent + domain split)  │
└─────────────────┘     └────────────┬─────────────┘
                                     ▼
              ┌─────────────────────────────────────┐
              │ Specialized domain agent(s)        │
              │ (income tax, sales tax, … 9 total) │
              └──────────────┬──────────────────────┘
                             ▼
              ┌─────────────────────────────────────┐
              │ Hybrid retrieval                   │
              │  • FAISS semantic (all-MiniLM-L6-v2)│
              │  • BM25 keyword                    │
              │  • Fusion + re-ranking             │
              └──────────────┬──────────────────────┘
                             ▼
              ┌─────────────────────────────────────┐
              │ Grounded answer generation         │
              │ (section citations, law tags)      │
              └──────────────┬──────────────────────┘
                             ▼
              ┌─────────────────────────────────────┐
              │ Verification layer                 │
              │ (grounding / consistency checks)   │
              └─────────────────────────────────────┘
```

1. **Ingestion** — official FBR documents (laws, rules, SROs) are chunked (overlapping chunks), embedded, and indexed.
2. **Routing** — the orchestrator classifies the query into one or more domains.
3. **Retrieval** — each agent pulls the top-k most relevant chunks using hybrid semantic + keyword search.
4. **Generation** — the LLM (Groq primary, OpenRouter fallback) writes the answer against the retrieved evidence only.
5. **Verification** — answers that don't match the evidence are refused, never fabricated.

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn, Pydantic v2 |
| Frontend | React 18, TypeScript, Vite 6, Zustand, react-router |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (pinned revision) |
| Vector store | FAISS (`faiss-cpu`) + BM25 (`rank-bm25`) hybrid |
| LLM | Groq (primary), OpenRouter (fallback) — OpenAI-compatible clients |
| Auth | PBKDF2 sessions (first-party) + Supabase JWT (HS256, audience `authenticated`) |
| Persistence | JSON store for accounts (`data/auth_users.json`), SQLite for vault (`data/vault.db`) |
| PDF/doc handling | PyMuPDF, pypdf, python-docx, openpyxl, Pillow |
| Infra | Docker + docker-compose, GitHub Actions (daily corpus update) |

---

## Project structure

```
├── app/
│   ├── main.py               # uvicorn entrypoint
│   ├── api.py                # FastAPI app, routers, rate limits, /answer & /calculate
│   ├── rag.py / rag_engine.py# retrieval pipeline
│   ├── hybrid_retriever.py   # FAISS + BM25 fusion
│   ├── reranker.py           # result re-ranking
│   ├── llm.py                # Groq / OpenRouter adapter
│   ├── supabase_auth.py      # JWT validation + email confirmation gate
│   ├── agents/               # 9 domain agents + orchestrator + router
│   ├── calculations/         # calculation engine + 11 modules
│   ├── tools/                # registered tools (search, tax_optimization, …)
│   ├── compliance_calendar/  # deadlines, reminders, compliance score
│   ├── document_intelligence/# classify/extract from PDFs, images, text
│   ├── invoice_intelligence/ # invoice validation, ITC, reconciliation
│   ├── notice_analyzer/      # notice type classification + action plans
│   ├── tax_health/           # health score, risks, penalties
│   ├── verification_center/  # NTN/CNIC/ATL verification logic
│   ├── fbr_monitor/          # notice event monitoring
│   ├── multi_user/           # UserManager (JSON-persisted), AuthManager, teams
│   ├── routers/              # FastAPI routers (auth, calendar, documents, …)
│   └── config/               # runtime flags
├── frontend/
│   ├── src/
│   │   ├── pages/            # Landing, auth, personal/*, business/*
│   │   ├── components/       # shell, auth (onboarding), ui
│   │   ├── state/            # Zustand stores (auth, onboarding, workspace)
│   │   └── lib/api.ts        # typed API client
│   └── package.json
├── data/                     # runtime data (git-ignored)
│   ├── raw/                  # source corpus (01-markdown … 04-source-docs)
│   ├── auth_users.json       # persistent accounts
│   └── vault.db              # vault documents
├── scripts/                  # corpus build, QA, daily update
├── tests/                    # backend pytest suites
├── requirements.txt          # pinned Python deps
├── Dockerfile / docker-compose.yml
└── .github/workflows/daily-fbr-update.yml
```

---

## Quick start

### Prerequisites
- Python 3.11+ (pinned deps in `requirements.txt`)
- Node.js 20+ and npm

### 1. Backend

```bash
cd Fbr-AI-Assisstant
python -m pip install -r requirements.txt

# optional: create .env with your keys (see Environment variables)
cp .env.example .env

python -m app.main
# or: uvicorn app.api:app --host 127.0.0.1 --port 8000
```

API + interactive docs: **http://127.0.0.1:8000/docs**
Health check: **http://127.0.0.1:8000/health** → `{"status":"ok","version":"1.0.0","auth":"required"}`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: **http://127.0.0.1:5173**

> The frontend calls the backend at `http://127.0.0.1:8000` by default. Override with `VITE_API_BASE_URL` in `frontend/.env.local`.

### 3. Docker (optional)

```bash
docker-compose up --build
```

---

## Environment variables

Create a `.env` in the project root (backend reads it):

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | for LLM answers | Primary LLM provider |
| `OPENROUTER_API_KEY` | fallback | Secondary LLM provider |
| `SUPABASE_URL` | optional | Supabase project URL |
| `SUPABASE_ANON_KEY` | optional | Supabase anon key (frontend config endpoint) |
| `SUPABASE_JWT_SECRET` | optional | Validates Supabase JWTs locally |
| `SUPABASE_REQUIRE_EMAIL_CONFIRM` | optional | `true` (default) rejects unconfirmed emails; `false` to skip |
| `FBR_AUTH_REQUIRED` | optional | `true` (default) enforces bearer tokens on protected endpoints; `false` for local dev fail-open |
| `FBR_AUTH_STORE` | optional | Path to the account JSON store (default `data/auth_users.json`) |
| `CORS_ORIGINS` | optional | Comma-separated allowed frontend origins |

Frontend (`frontend/.env.local`):

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend URL (default `http://127.0.0.1:8000`) |
| `VITE_API_TIMEOUT_MS` | Request timeout |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Supabase client (optional) |
| `VITE_AUTH_CALLBACK_URL` | OAuth/callback URL |

---

## Auth, email confirmation & workspaces

### Flow
1. **Sign up** → `POST /auth/signup` creates the account (PBKDF2 hash) and returns a session token. Accounts persist to `data/auth_users.json`.
2. **Onboarding** → 4 professional questions; the backend stores the final workspace choice via `POST /auth/workspace` (`personal` or `business`). An explicit user click always overrides the algorithm's recommendation.
3. **Login** → `POST /auth/login` verifies the hash, creates a session, returns a token.
4. **Session** → opaque bearer token, 24h TTL, refreshed via `POST /auth/refresh`, destroyed via `POST /auth/logout`. Restart-safe thanks to the JSON store.

### Email confirmation (Supabase)
- Enable **Email confirmation** in Supabase Auth settings.
- The backend's Supabase path enforces it automatically: a JWT without `email_confirmed_at` gets `401 Email not confirmed. Please confirm your email before signing in.` (the frontend surfaces this as a friendly message).
- Set `SUPABASE_REQUIRE_EMAIL_CONFIRM=false` only if your project disables confirmation entirely.

---

## API overview

All protected endpoints accept `Authorization: Bearer <token>` (backend session token or Supabase JWT).

| Router | Prefix | Highlights |
|---|---|---|
| auth | `/auth` | `signup`, `login`, `logout`, `me`, `refresh`, `workspace` |
| assistant | `/assistant` | `ask`, `ask/stream` (SSE with tool runs + verification) |
| qa | `/answer` | Full RAG answer with sources + verification |
| calculations | `/calculate` | 11 modules, `types`, `health` |
| calendar | `/calendar` | events, `dashboard`, `upcoming`, reminders |
| tax_health | `/tax/health` | `check`, `risks`, `penalties`, `score-guide` |
| notices | `/notices` | `analyze`, `types` |
| documents | `/documents` | `analyze`, `verify`, `types` |
| uploads | `/uploads` | document/invoice upload analysis |
| invoices | `/invoices` | `process`, `dashboard`, `reconcile`, `export` |
| verify | `/verify` | `ntn`, `filer`, `vendor`, `cnic`, `business`, `atl`, `batch` |
| monitor | `/monitor` | `subscribe`, `dashboard`, events, `simulate/notice` |
| team | `/team` | `register`, `login`, dashboards, roles |
| workspaces | `/workspaces` | user workspaces, `create`, health |
| vault | `/vault` | per-user document storage CRUD |
| business_reports | `/business/reports` | `types`, `generate` (markdown) |
| system | — | `/health`, `/api/auth/config`, `/api/auth/me`, `/api/auth/status` |

---

## The FBR knowledge corpus

- Source documents live under `data/raw/` (markdown, JSONL, CSV, source PDFs/docx).
- A build pipeline chunks and indexes them into the hybrid FAISS + BM25 store.
- Chunks carry metadata (document, section number, page, law tag) that powers citations.
- **Daily automated update** (`.github/workflows/daily-fbr-update.yml`) re-pulls and re-indexes the corpus on a schedule, so answers track current FBR publications.
- The `scripts/` folder contains corpus inspection, QA, and update tooling.

---

## Testing

```bash
# Backend (pytest)
python -m pytest tests/ -q

# Frontend unit + component tests
cd frontend
npm run test        # vitest
npx tsc --noEmit    # typecheck
```

Examples of covered suites: auth round-trip, workspace allocation, multi-user, production API suite, and the Vitest frontend suite (119 tests).

---

## Deployment

- **Docker**: `docker-compose up --build` runs backend + frontend.
- **GitHub Actions**: daily corpus refresh workflow built in.
- Notes for production:
  - Replace the in-memory rate limiter with Redis for multi-worker deployments.
  - The account store (`data/auth_users.json`) is file-based; move to a real DB (Supabase/Postgres) for multi-instance scale.
  - Set `FBR_AUTH_REQUIRED=true` and real `CORS_ORIGINS` before exposing publicly.

---

## Known limitations

- The account store is a local JSON file — fine for a single backend instance; horizontal scale needs a database.
- The `calculation` domain may refuse without LLM keys configured (grounded RAG domains work without keys; deterministic calculators always work).
- `/calculate` accepts a fixed `TaxYear` enum (documented in the API schema).
- Rate limiting is per-process/in-memory; use Redis when running multiple workers.
- Supabase confirmation emails require Supabase Auth to be enabled and the frontend to sign up through Supabase (the first-party `/auth/signup` path has no built-in mail sender).

---

## License

Proprietary / project-specific. See repository owner for usage rights.