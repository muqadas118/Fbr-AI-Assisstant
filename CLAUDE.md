# FBR AI Assistant - Project Overview

## Project Name
**FBR AI Tax & Compliance Assistant** - Pakistan's Federal Board of Revenue AI Assistant

## Location
`D:\All Projects\AI Assistant fbr`

## What It Does
AI-powered assistant for FBR (Federal Board of Revenue) Pakistan tax and compliance queries. It answers questions about:
- Income Tax
- Sales Tax
- Federal Excise
- Customs
- Tax Registration (NTN, STRN)
- Return Filing
- Tax Calculations
- FBR Notices & Appeals
- Research (multi-domain, Finance Act comparisons)

## Tech Stack

### Backend
- **Language:** Python 3.x
- **Framework:** FastAPI
- **LLM:** Groq (primary), OpenRouter (fallback)
- **Vector DB:** FAISS (IndexFlatIP, 58,822 vectors, 384 dimensions)
- **Embeddings:** sentence-transformers/all-MiniLM-L6-v2
- **Retrieval:** Hybrid (Semantic + BM25, 60/40 weighted)
- **Architecture:** 9-agent system with deterministic router
- **Database:** SQLite (dev) / PostgreSQL (production)
- **Auth:** Supabase JWT (PBKDF2 for internal multi-user)

### Frontend
- **Framework:** React 18 + TypeScript
- **Build Tool:** Vite
- **State Management:** Zustand
- **Router:** React Router v6
- **Styling:** Custom CSS (no external UI library)

## Architecture

### 9-Agent System
1. **IncomeTaxAgent** - Income Tax Ordinance, WHT, returns
2. **SalesTaxAgent** - Sales Tax Act, registration, invoices
3. **FederalExciseAgent** - FED, SROs
4. **CustomsAgent** - Imports, tariffs, HS codes
5. **RegistrationAgent** - NTN, IRIS, STRN registration
6. **ReturnFilingAgent** - Filing deadlines, forms
7. **CalculationAgent** - Tax math, penalty calculations + TaxOptimizationTool
8. **NoticeAppealAgent** - FBR notices, appeals
9. **ResearchAgent** - Multi-domain, Finance Act comparisons

### Query Flow
```
User Query → Deterministic Router → Specialized Agent(s) → RAG Engine → Verification → Grounded Answer
```

### RAG Pipeline
1. Query Understanding (keyword extraction)
2. Hybrid Retrieval (FAISS + BM25)
3. Context Assembly (bounded 16,000 chars)
4. LLM Answer Generation
5. Verification Layer (grounding, section consistency, speculation check)

### API Router Architecture (app/routers/)
```
app/api.py                    → Main FastAPI app + original 8 endpoints
app/routers/calendar.py      → /calendar/* (Compliance Calendar)
app/routers/tax_health.py    → /tax/health/* (Tax Health)
app/routers/notices.py        → /notices/* (FBR Notice Analyzer)
app/routers/documents.py      → /documents/* (Document Intelligence)
app/routers/invoices.py       → /invoices/* (Invoice Intelligence)
app/routers/verify.py         → /verify/* (Verification Center)
app/routers/monitor.py        → /monitor/* (FBR Monitor)
app/routers/team.py           → /team/* (Team Management)
app/routers/workspaces.py     → /workspaces/* (Workspace Management)
```

## API Endpoints (63 total)

### Original Endpoints
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /calculate | Required | Tax calculations (11 types) |
| GET | /calculate/types | Public | List calc types |
| GET | /calculate/health | Public | Calc engine health |
| GET | /health | Public | API health |
| POST | /answer | Required | RAG Q&A |
| GET | /api/auth/config | Public | Supabase config |
| GET | /api/auth/me | Required | Current user |
| GET | /api/auth/status | Optional | Auth status |

### Compliance Calendar (7 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| GET | /calendar | Get compliance calendar |
| GET | /calendar/upcoming | Upcoming tasks |
| POST | /calendar/events/{id}/complete | Mark event complete |
| POST | /calendar/reminders | Schedule reminders |
| GET | /calendar/export | Export calendar (JSON/CSV) |
| GET | /calendar/dashboard | Dashboard summary |
| GET | /calendar/types | Event types & categories |

### Tax Health (4 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /tax/health/check | Run health check |
| POST | /tax/health/risks | Risk analysis |
| POST | /tax/health/penalties | Penalty estimation |
| GET | /tax/health/score-guide | Score guide |

### FBR Notices (3 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /notices/analyze | Analyze FBR notice |
| POST | /notices/analyze/text | Analyze from text |
| GET | /notices/types | Supported notice types |

### Document Intelligence (3 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /documents/analyze | Analyze document |
| POST | /documents/verify | Verify NTN/CNIC |
| GET | /documents/types | Supported document types |

### Invoice Intelligence (4 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /invoices/process | Process invoice |
| POST | /invoices/reconcile | Period reconciliation |
| GET | /invoices/dashboard | Invoice dashboard |
| GET | /invoices/export | Export invoices |

### Verification Center (8 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /verify/ntn | Verify NTN |
| POST | /verify/filer | Check filer status |
| POST | /verify/vendor | Verify vendor |
| POST | /verify/cnic | Verify CNIC |
| POST | /verify/business | Verify business registration |
| POST | /verify/batch | Batch verification |
| GET | /verify/atl/{ntn} | Check ATL status |

### FBR Monitor (10 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /monitor/subscribe | Subscribe to monitoring |
| DELETE | /monitor/unsubscribe/{user_id} | Unsubscribe |
| GET | /monitor/dashboard/{user_id} | Monitoring dashboard |
| GET | /monitor/event/{id} | Event details |
| POST | /monitor/event/{id}/acknowledge | Acknowledge event |
| POST | /monitor/event/{id}/resolve | Resolve event |
| POST | /monitor/webhook | Register webhook |
| GET | /monitor/webhook/stats | Webhook stats |
| POST | /monitor/simulate/notice | Test notice simulation |
| GET | /monitor/event-types | Event types |

### Team Management (10 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /team/register | Register user |
| POST | /team/login | User login |
| POST | /team/logout | User logout |
| POST | /team/password/change | Change password |
| POST | /team/create | Create team |
| POST | /team/invite | Invite user |
| POST | /team/invitation/accept | Accept invitation |
| GET | /team/dashboard/{team_id} | Team dashboard |
| GET | /team/user-dashboard/{user_id} | User dashboard |
| GET | /team/roles | List roles & permissions |

### Workspaces (3 endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| GET | /workspaces/{user_id} | Get workspaces |
| POST | /workspaces/create | Create workspace |
| GET | /workspaces/health | Health check |

## 11 Calculation Modules
income_tax, salary_tax, business_tax, sales_tax, withholding_tax, federal_excise, capital_gains, property_tax, dividend_tax, custom_duty, custom_calc

## 13 Tools in Registry
rag_search, hybrid_search, metadata_filter, rule_engine, calculation_engine, document_parser, duplicate_detection, similarity_engine, anomaly_detection, web_research, notification, report_generator, tax_optimization (with 12-pattern evasion guard)

## Data
- **Source Documents:** 94 FBR documents (PDFs)
- **Chunks:** 58,822 (section/page-aware, paragraph-preserving)
- **Sources:** Income Tax, Sales Tax, Federal Excise, Finance Act, Property Valuation, SOPs
- **Property Valuation:** 54 cities covered (Lahore, Karachi, Islamabad, etc.)

## Key Backend Modules
- `app/api.py` - FastAPI app + 8 original endpoints
- `app/rag_engine.py` - Core RAG pipeline
- `app/agents/orchestrator.py` - 9-agent orchestration
- `app/agents/router.py` - Deterministic query routing
- `app/verification_layer.py` - Answer verification (10 enforcement rules)
- `app/routers/` - FastAPI routers (9 modules, 55 new endpoints)
- `app/compliance_calendar/` - FY 2024-27 deadlines, reminders, compliance score
- `app/document_intelligence/` - PDF/OCR, 50+ doc types, extraction
- `app/invoice_intelligence/` - Invoice extract, validate, ITC reconcile
- `app/notice_analyzer/` - FBR notice (30+ types), action plan, appeal guide
- `app/tax_health/` - Health score, 6 checks, risk analysis, penalties
- `app/verification_center/` - NTN/STRN/filer/business verification
- `app/fbr_monitor/` - Real-time FBR portal monitoring, webhooks
- `app/multi_user/` - Teams, roles, PBKDF2 auth
- `app/deployment/` - Health probes, Prometheus metrics, alerts
- `app/tools/` - 13 registered tools (tax_optimization, etc.)

## Running the Project

### Backend
```bash
cd "D:\All Projects\AI Assistant fbr"
python -m app.main
# API runs on http://127.0.0.1:8000
# Docs: http://127.0.0.1:8000/docs
```

### Frontend
```bash
cd frontend
npm run dev
# Frontend runs on http://localhost:5173
```

## Environment Variables
- `GROQ_API_KEY` - Primary LLM (recommended)
- `OPENROUTER_API_KEY` - Fallback LLM
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anon key
- `SUPABASE_JWT_SECRET` - JWT secret for auth
- `FBR_AUTH_REQUIRED` - Require auth (default: true)

## Status
- Backend: ✅ Complete (9 routers, 63 total endpoints)
- Frontend Personal: ⚠️ Partial (5 ready, 2 partial, 7 stub)
- Frontend Business: ❌ Not built
- Frontend Shared Platform: ❌ Not built
- Auth: ⏸️ Deferred (to be added LAST per user instruction)

## User Priority
Auth integration to be added LAST, after ALL UI/workspace work is complete.

## Notes
- Deterministic routing (no LLM needed for routing)
- Grounded answers only (refuses when no evidence)
- Verification layer prevents hallucinations
- Multi-domain queries handled independently per domain
- All 9 hidden modules now exposed via FastAPI routers
- Production-grade error handling on all endpoints
