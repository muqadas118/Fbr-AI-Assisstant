# FBR AI Tax & Compliance Assistant

AI-powered assistant for Pakistan's Federal Board of Revenue (FBR) tax and compliance queries.

## Tech Stack

- **Backend:** FastAPI (Python)
- **Frontend:** React 18 + TypeScript + Vite
- **LLM:** Groq (primary) / OpenRouter (fallback)
- **Vector DB:** FAISS + BM25 hybrid retrieval
- **Auth:** PBKDF2 session auth (first-party) + Supabase JWT fallback
- **DB:** SQLite (dev) / PostgreSQL (prod)

## Quick Start

### Backend

```bash
cd "D:/All Projects/AI Assistant fbr"
# Install deps in your Python env
pip install -r requirements.txt
python -m app.main
```

API: [http://localhost:8000/docs](http://localhost:8000/docs)

### Frontend

```bash
cd frontend
npm i
npm run dev
```

App: [http://localhost:5173](http://localhost:5173)

## Features

- 9-agent routing system (Income Tax, Sales Tax, FED, Customs, Registration, Return Filing, Calculations, Notices/Appeals, Research)
- Grounded RAG over 100+ FBR documents with citations
- 11 tax calculation modules
- Compliance calendar, tax health, notice analyzer, document/invoice intelligence, verification center
- Personal & Business workspaces with onboarding questionnaire

## Environment

Create `.env` in backend root (as needed):
- `GROQ_API_KEY` / `OPENROUTER_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`
- `FBR_AUTH_REQUIRED` (default: `true`)

## License

Proprietary/Project-specific.