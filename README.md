# FBR AI Tax & Compliance Assistant

A production-grade, **RAG-powered AI assistant** for Pakistan's Federal Board of Revenue (FBR) tax and compliance work. It answers tax queries with grounded, cited answers drawn from the official FBR law corpus, runs 11 tax calculators, analyzes FBR notices, tracks filing deadlines, verifies NTNs/CNICs, analyzes documents and invoices, and gives every user a Personal or Business compliance workspace.

Built for tax professionals, accountants, businesses and individual taxpayers who need *evidence-led* answers — not generic chat.

---

## Table of Contents

- [What this project does](#what-this-project-does)
- [Key features](#key-features)
- [How it works — RAG + agent routing](#how-it-works--rag--agent-routing)
- [Self-learning & personalization](#self-learning--personalization)
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
- **Notice analyzer** — classifies 22 of the 38 catalogued FBR notice types, with deadlines, action plans and appeal guides (the 16 types without classification signals are reported as unclassifiable rather than advertised as supported).
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

### 7. Daily per-account quota
- Every account gets a daily budget of assistant messages (`FBR_DAILY_MESSAGE_LIMIT`, default 10) and chat file uploads (`FBR_DAILY_UPLOAD_LIMIT`, default 5), resetting at local midnight in `FBR_QUOTA_TIMEZONE` (default `Asia/Karachi`).
- Enforced by `app/quotas.py` on `POST /assistant/ask`, `POST /assistant/ask/stream` and the `/uploads/*` routes; exhaustion returns **429** with a localized message (`quota_exceeded` / `quota_upload_exceeded` from `app/language.py`).
- `GET /quota` (owner-scoped, `app/routers/quota.py`) returns the caller's snapshot; the `/assistant/ask` response and the SSE `meta` event carry the same `quota` object.
- Limit semantics: `0` blocks immediately, a **negative** limit means unlimited. On a store error the default fails open (the request is allowed, the error is logged); set `FBR_QUOTA_FAIL_OPEN=0` to fail closed instead.

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

### Answer language (mirrors the user)

The assistant replies in the user's own language and script. `app/language.py` is the canonical, stdlib-only policy module: `detect_language` classifies a message as Urdu script (`ur`), Roman Urdu (`roman_ur`) or English (`en`); `resolve_language` picks the reply language with the precedence **explicit `response_language` choice > the current question's language > a remembered profile `language` signal > English**, so the profile is used only as a fallback when the question itself carries no signal. `output_directive` builds the per-language prompt block (which also pins numbers and FBR citations to their original form) and is appended to both the streaming and non-streaming prompts; `localize` renders the refusal texts (`no_evidence`, `ambiguous_section`, `unverified`, `llm_unavailable`, `placeholder`) in the reply language.

| Question language | Answer |
|---|---|
| Roman Urdu | Roman Urdu answer (natural WhatsApp-style), but every tax/legal term, law name, section number, form name, amount and percentage stays as written |
| Urdu script (اردو) | Urdu-script answer, with the same tax/legal terms and figures left unchanged |
| English, or no language signal | English (default) |

A remembered profile language preference is used only as a fallback; the explicit `response_language` override wins over everything. The `app/llm.py` adapter appends the directive to both the streaming and non-streaming prompts; `app/rag_engine.py` (`answer` and `ground`) and the CLI (`app/answer_generator.py`) resolve the language and return localized refusals. `app/verification_answer.py` makes the English lexical grounding check language-aware, so a faithful Roman-Urdu/Urdu answer is not falsely rejected while numeric grounding and section checks still apply.

---

## Self-learning & personalization

This is **per-user behavioural personalization, not model training**. No model weights are read, written or changed anywhere in this feature — there is no fine-tuning and no retraining. One account's interaction history is reduced to small derived signals, aggregated into that account's profile, and used to shape only that account's recommendations. Nothing is ever aggregated across users.

| Module | Role |
|---|---|
| `app/learning/store.py` | SQLite store (default `data/learning.db`) holding per-user signals, feedback, recommendations and the on/off setting. Every read and write is scoped by `user_id`, so one user can never see or mutate another user's rows. Every method degrades to an empty result instead of raising when the store is unavailable. |
| `app/learning/profile.py` | Deterministic keyword/regex extraction of derived signals — tax year, NTN, notice type, document type, language hint, entity type, filing status — and their aggregation into a `UserProfile`. Domain interest is scored with **exponential time decay** (weight halves every 30 days) and 👍/👎 ratings nudge a domain's score up or down. |
| `app/learning/recommender.py` | Rule-based transform of that profile, plus FBR compliance-calendar events, into an ordered, dismissible recommendation list. |
| `app/routers/personalization.py` | The authenticated, owner-scoped HTTP surface. Rate-limited on the profile and feedback routes. |

Recommendation kinds: `deadline`, `calculator`, `notice_followup`, `document_followup`, `learning_topic`, `verification`, `tax_health`. Recommendations are priority-sorted (calendar deadlines outrank behavioural suggestions), capped per request, and dismissible by id.

### How it shapes answers

Before generating, `POST /assistant/ask` (and the SSE stream) reads the caller's profile and appends a **USER CONTEXT** block to the LLM prompt — frequently-asked domains, taxpayer type, tax year, language preference and interaction count, plus one or two relevant suggestions. A hard rule in the prompt keeps the profile subordinate to the evidence: computed tool figures and FBR citations always win, and the profile must never change a number or a legal reference. After answering, the interaction is recorded (domain + tools used + derived signals), so later answers are grounded in that account's context. When personalization is unavailable or opted out, the block is simply omitted and answering is unaffected — this path can never fail a request.

`POST /assistant/ask` returns a `personalization` object (`{enabled, recommendations, profile_summary}`) alongside the answer; `POST /assistant/ask/stream` emits the same object as an `event: personalization` immediately after `event: meta`.

### What is collected — and what is not

| Collected | Detail |
|---|---|
| Derived signals | tax year, NTN, notice type, document type, money amounts, language hint (English / Urdu script / Roman-Urdu), entity type, filing status — derived from the question text, not the text itself |
| Domains | which routed domains the questions hit, scored with recency decay |
| Tool usage | which backend tools ran for the questions (frequency counts) |
| Ratings | 👍/👎 per assistant message, plus any comment typed with it |
| Dismissals | ids of the recommendations the user dismissed |

| Not collected | Detail |
|---|---|
| Raw question text | stored only when `FBR_LEARNING_STORE_RAW_QUERIES=1`; default off keeps derived signals only |
| Cross-user aggregation | no profile, signal or statistic is ever merged across accounts |
| Shared training | no model weights, fine-tuning or retraining happen anywhere in this feature |

### Privacy controls

- **Opt out** — `PUT /personalization/me/personalization` with `{"enabled": false}`. New accounts are opted in by default (opt-out model).
- **Delete everything** — `DELETE /personalization/me/data` drops all of that account's interactions, feedback, recommendations and settings.
- **Global kill switch** — `FBR_LEARNING_ENABLED=false` disables the module; every endpoint then returns an empty result.
- **Retention** — `FBR_LEARNING_RETENTION_DAYS` (default 90) plus a hard cap of 500 stored interactions per user.

### Where it appears in the UI

- **Assistant header — "For you"** opens the `PersonalizationPanel`: learned top domains, entity type and tax year, an on/off switch, and a delete-everything action.
- **`RecommendationStrip`** renders the per-answer recommendation list (renders nothing when the list is empty).
- **👍 / 👎 buttons** on each assistant message post to `POST /personalization/feedback`.
- **Settings → "Personalization & Learning"** explains the feature and jumps to the panel.

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
| Infra | Docker + docker-compose, GitHub Actions (CI + daily corpus update) |

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
└── .github/workflows/ci.yml + daily-fbr-update.yml
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
| `FBR_METRICS_ENABLED` | optional | `true` exposes `/metrics` (Prometheus text format); unset keeps the endpoint unregistered |
| `FBR_AUTH_STORE` | optional | Path to the account JSON store (default `data/auth_users.json`) |
| `CORS_ORIGINS` | optional | Comma-separated allowed frontend origins |

LLM provider chain (see [Choosing LLM providers](#choosing-llm-providers-free-tiers) below):

| Variable | Required | Purpose |
|---|---|---|
| `LLM_PROVIDERS` | optional | Ordered, comma-separated provider chain (e.g. `gemini,groq,cerebras,openrouter,local`); tried left to right |
| `LLM_<NAME>_BASE_URL` | optional | OpenAI-compatible base URL for logical provider `<NAME>` |
| `LLM_<NAME>_MODEL` | optional | Model id for `<NAME>` |
| `LLM_<NAME>_API_KEY` | optional | API key for `<NAME>` (a local server needs none) |

Daily per-account quota (see [Daily per-account quota](#7-daily-per-account-quota)):

| Variable | Required | Purpose |
|---|---|---|
| `FBR_QUOTA_ENABLED` | optional | `1` (default) enables the daily quota; `0` disables it |
| `FBR_DAILY_MESSAGE_LIMIT` | optional | Assistant messages per account per day (default 10); `0` blocks, negative = unlimited |
| `FBR_DAILY_UPLOAD_LIMIT` | optional | Chat file uploads per account per day (default 5); `0` blocks, negative = unlimited |
| `FBR_QUOTA_DB` | optional | SQLite path for the usage counters (default `data/usage.db`) |
| `FBR_QUOTA_TIMEZONE` | optional | IANA timezone for the local-midnight reset (default `Asia/Karachi`) |
| `FBR_QUOTA_FAIL_OPEN` | optional | `1` (default) fails open on a store error; `0` fails closed (429) |

### Choosing LLM providers (free tiers)

`app/llm.py` builds an **ordered provider chain** and fails over automatically:

1. `LLM_PROVIDERS=name1,name2,...` lists logical names in priority order. Each name is resolved from `LLM_<NAME>_BASE_URL` + `LLM_<NAME>_MODEL` (plus an optional `LLM_<NAME>_API_KEY`).
2. The legacy `GROQ_API_KEY` / `OPENROUTER_API_KEY` (and `GROQ_MODEL` / `OPENROUTER_MODEL`) are mapped in after the explicit chain.
3. Any other `LLM_<NAME>_*` set is auto-discovered and appended.

On a `429`, `5xx`, network error or empty content the next provider is tried (with a short backoff); the streaming path only fails over before the first token is produced. If every provider fails, a single `LLMError` is raised and the app degrades to the deterministic no-evidence answer instead of a raw stack trace. Any OpenAI-compatible endpoint works — Gemini (OpenAI-compat), Cerebras, Mistral, DeepSeek, Together, Fireworks, AgentRouter, or a local Ollama / LM Studio / vLLM server.

| Provider | Free / low-cost shape | Notes |
|---|---|---|
| Google AI Studio (Gemini) | Generous free tier on capable models | OpenAI-compatible endpoint; set its base URL + model explicitly (no built-in default) |
| Groq | Generous free tier, very fast inference | Strong first choice for latency |
| Cerebras | Free tier with very fast inference | OpenAI-compatible; set base URL + model explicitly |
| Mistral | Modest free tier on La Plateforme | OpenAI-compatible |
| OpenRouter | Aggregated gateway; **free models carry a small daily request cap** | Paid models available; model ids are `vendor/model` |
| Local (Ollama / LM Studio / vLLM) | Unlimited and free, bounded by your hardware | No API key needed; good last-resort fallback |

A concrete chain that favours free capacity, then reliability:

```
LLM_PROVIDERS=gemini,groq,cerebras,openrouter,local
```

If this is user-facing at scale, put a paid/high-limit provider first so the free tiers are not exhausted early. Provider free tiers and rate limits change over time — confirm the current limits on each provider's own site before relying on them.

Self-learning / personalization (see [Self-learning & personalization](#self-learning--personalization)):

| Variable | Required | Purpose |
|---|---|---|
| `FBR_LEARNING_DB` | optional | Path to the personalization SQLite store (default `data/learning.db`) |
| `FBR_LEARNING_ENABLED` | optional | `1` (default) enables the module; `0` disables it globally |
| `FBR_LEARNING_STORE_RAW_QUERIES` | optional | `1` stores raw question text; default off keeps derived signals only |
| `FBR_LEARNING_RETENTION_DAYS` | optional | Days of per-user interaction history kept (default 90) |
| `FBR_LEARNING_PROFILE_RATE_LIMIT` | optional | `GET /personalization/profile` limit as `<requests>/<seconds>` (default 60/60) |
| `FBR_LEARNING_FEEDBACK_RATE_LIMIT` | optional | `POST /personalization/feedback` limit as `<requests>/<seconds>` (default 30/60) |

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
| assistant | `/assistant` | `ask`, `ask/stream` (SSE with tool runs + verification + a `personalization` payload / `event: personalization`); asks accept `response_language` (`auto` default, or `en`/`roman_ur`/`ur`), and the response plus the SSE `meta` event carry `answer_language` |
| quota | `/quota` | `GET /quota` — the caller's daily message/upload snapshot (owner-scoped) |
| personalization | `/personalization` | `profile`, `recommendations`, `recommendations/{id}/dismiss`, `feedback`, `me/data`, `me/personalization` |
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

Every feature router enforces `Depends(require_user)` on its routes. Of the 86 routes on the app (`/metrics` is registered only when `FBR_METRICS_ENABLED=true`), 68 require a bearer token and 18 are intentionally public: the auth bootstrap endpoints (`POST /auth/signup`, `POST /auth/login`, `POST /team/register`, `POST /team/login`, `GET /team/roles`), static reference data (`GET /notices/types`, `GET /documents/types`, `GET /calendar/types`, `GET /calculate/types`, `GET /calculate/health`, `GET /vault/health`, `GET /monitor/event-types`, `GET /tax/health/score-guide`, `GET /workspaces/health`) and health/diagnostics (`GET /health`, `GET /api/auth/config`, `GET /api/auth/status`). `GET /api/auth/me` takes the Supabase JWT path. Setting `FBR_AUTH_REQUIRED=false` makes `require_user` fail open for local development.

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

**CI** (`.github/workflows/ci.yml`) runs on every push and pull request to `main`: the Python job installs `requirements.txt` plus `ruff`, runs `python -m pytest tests/ -q` and `ruff check app tests scripts`; the frontend job runs `npm ci` and `npx tsc --noEmit`.

Examples of covered suites: auth round-trip, workspace allocation, multi-user, production API suite, self-learning/personalization, and the Vitest frontend suite (135 tests across 9 files).

---

## Deployment

- **Docker**: `docker-compose up --build` runs backend + frontend.
- **GitHub Actions**: a CI workflow (pytest + ruff + frontend typecheck) plus the daily corpus refresh workflow.
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
- Recommendations rely on the stored interaction history, so a brand-new account (or one that has just deleted its data) gets few or none — only the always-on `tax_health` suggestion and the calendar deadlines. History builds up automatically: every answered assistant question is recorded (`domain`, tools used and derived signals), and 👍/👎 feedback nudges the profile.
- No model fine-tuning happens: personalization is behavioural (interest scoring with time decay plus recommendation re-ranking), so it cannot improve the underlying answers, only the per-user recommendation list.
- Answer-language mirroring is best-effort on very short or mixed-language messages, and while refusal texts are localized the retrieved FBR legal text (sources and quoted law) stays in its original English.

---

## License

Proprietary / project-specific. See repository owner for usage rights.
