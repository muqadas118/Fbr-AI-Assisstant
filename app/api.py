import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.orchestrator import AgentOrchestrator
from app.calculations import get_tax_engine, TaxCalculationEngine
from app.llm import LLMError
from app.routers import (
    calendar_router,
    documents_router,
    invoices_router,
    monitor_router,
    notices_router,
    tax_health_router,
    team_router,
    verify_router,
    workspaces_router,
)
from app.supabase_auth import (
    auth_required,
    get_current_user,
    get_optional_user,
    get_supabase_config,
    require_user,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("fbr_api")

# Rate limiting storage (in-memory, use Redis for production)
# 10 requests per minute per IP
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds
_rate_store: dict[str, list[datetime]] = defaultdict(list)


def _check_rate_limit(client_key: str) -> tuple[bool, int]:
    """Check if a client is within the rate limit. Returns (allowed, remaining).

    `client_key` is "user:<id>" when authenticated, "ip:<addr>" otherwise.
    NOTE: in-memory and per-process — it resets on restart and is not shared
    across uvicorn workers. Move to Redis before relying on it in production.
    """
    now = datetime.now()
    window_start = now - timedelta(seconds=RATE_WINDOW)

    # Clean old entries
    _rate_store[client_key] = [
        ts for ts in _rate_store[client_key] if ts > window_start
    ]

    if len(_rate_store[client_key]) >= RATE_LIMIT:
        return False, 0

    _rate_store[client_key].append(now)
    remaining = RATE_LIMIT - len(_rate_store[client_key])
    return True, remaining


# Rate-limit POST /verify/batch with the shared in-memory limiter.
# verify.py is out of scope for this pass, so attach here in api.py.
# Kept IP-keyed as defense-in-depth; FULL-AUTH (2026-09-13) added
# Depends(require_user) on the route itself, so user identity is now
# available for a future user-keyed upgrade like POST /answer.
async def _verify_batch_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, _remaining = _check_rate_limit("ip:" + client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT} requests per {RATE_WINDOW}s",
        )


for _r in verify_router.routes:
    _p = getattr(_r, "path", "")
    _m = getattr(_r, "methods", set()) or set()
    if _p == "/verify/batch" and "POST" in _m:
        _r.dependencies.append(Depends(_verify_batch_rate_limit))


async def log_requests(request: Request, call_next):
    """Log all incoming requests for audit trail."""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        f"Request | {request.method} {request.url.path} | IP: {client_ip}"
    )

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        f"Response | {request.method} {request.url.path} | "
        f"Status: {response.status_code} | Duration: {duration:.3f}s"
    )

    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    return response


class AnswerRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The user's tax or compliance question.",
    )

    @field_validator("query")
    @classmethod
    def query_strip_whitespace(cls, v: str) -> str:
        return v.strip()


class SourceItem(BaseModel):
    # Chunk metadata carries section_number as an int (e.g. 119) for some
    # sources and a str (e.g. "119A") for others. Coerce numbers to str so a
    # numeric section label does not 500 the whole /answer response.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    chunk_id: str
    document_id: str
    source: str
    source_path: str
    source_sha256: Optional[str] = None
    page: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section: Optional[str] = None
    section_reference: Optional[str] = None
    section_number: Optional[str] = None
    law_tag: Optional[str] = None
    multi_law_candidate: bool = False
    score: float
    semantic_score: float
    bm25_score: float
    exact_match: bool


class VerificationCheck(BaseModel):
    passed: bool
    reason: str
    weak_sentences: Optional[list[str]] = None

    @field_validator("weak_sentences", mode="before")
    @classmethod
    def _normalize_weak_sentences(cls, v):
        # The grounding check emits weak sentences as {"sentence","score"}
        # dicts, not plain strings. Flatten to the sentence text so a failed
        # grounding check does not 500 the whole response.
        if v is None:
            return None
        out = []
        for item in v:
            if isinstance(item, dict):
                out.append(str(item.get("sentence", item)))
            else:
                out.append(str(item))
        return out


class VerificationChecks(BaseModel):
    answer_size: VerificationCheck
    section_consistency: VerificationCheck
    grounding: VerificationCheck
    speculation: VerificationCheck


class VerificationResult(BaseModel):
    passed: bool
    checks: VerificationChecks
    failed_checks: list[str]
    reason: str


class AnswerResponse(BaseModel):
    question: str
    domains: list[str]
    primary_domain: str
    multi_domain: bool
    routing: dict[str, Any]
    domain_results: list[dict[str, Any]]
    answer: str
    sources: list[SourceItem]
    verification: VerificationResult
    grounded: bool


app = FastAPI(
    title="FBR AI Tax & Compliance Assistant API",
    description="Backend API for the FBR AI Tax & Compliance Assistant.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# =============================================================================
# Mount feature routers
# =============================================================================
# These expose the previously built-but-hidden feature modules
# (compliance_calendar, tax_health, notice_analyzer, document_intelligence,
# invoice_intelligence, verification_center, fbr_monitor, multi_user)
# as HTTP endpoints for the frontend.

app.include_router(calendar_router)
app.include_router(tax_health_router)
app.include_router(notices_router)
app.include_router(documents_router)
app.include_router(invoices_router)
app.include_router(verify_router)
app.include_router(monitor_router)
app.include_router(team_router)
app.include_router(workspaces_router)

# SECURITY NOTE - deferred auth hardening (owner decision):
# The feature routers mounted above expose 51 endpoints with no Depends auth
# yet (calendar, documents, invoices, monitor, notices, tax_health, team,
# verify, workspaces). POST /answer and POST /calculate enforce JWT via
# require_user, but router endpoints stay public until the final auth phase.
# Do not add per-router auth here.
# FULL-AUTH 2026-09-13: per-route Depends(require_user) added in all 9
# routers (41 endpoints authed, 10 intentionally public: */types,
# /tax/health/score-guide, /monitor/event-types, POST /monitor/webhook,
# POST /team/register, POST /team/login, GET /team/roles,
# GET /workspaces/health). Health + auth config/status stay public.
# FBR_AUTH_REQUIRED=false bypass still honored by require_user.

# CORS Middleware - Configure for production frontend origin
# CORS_ORIGINS env (comma-separated) overrides the localhost defaults.
_cors_env = os.environ.get("CORS_ORIGINS", "")
_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
if not _origins:
    _origins = [
        "http://localhost:5173",  # Local dev
        "http://localhost:3000",  # Alternative local dev
        # Add your production frontend URL here
        # "https://your-frontend-domain.com",
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Register request logging middleware
app.middleware("http")(log_requests)


_orchestrator: Optional[AgentOrchestrator] = None


def _get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


@app.post("/calculate", tags=["calculations"])
async def calculate(
    request: Request,
    user: Optional[dict] = Depends(require_user),
):
    """
    Production-Grade Tax Calculation Endpoint.
    Supports all 11 tax calculator modules.
    Expects JSON body: {"calc_type": "...", "inputs": {...}}
    """
    # Rate limiting - same in-memory limiter as POST /answer (10 req/60s).
    rate_key = "user:" + str(user.get("id")) if user and user.get("id") else ("ip:" + str(request.client.host) if request.client else "ip:unknown")
    allowed, remaining = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT} requests per {RATE_WINDOW}s",
        )

    try:
        body = await request.json()
        calc_type = body.get("calc_type", "income_tax")
        inputs = body.get("inputs", {})

        engine = get_tax_engine()
        result = engine.calculate(calc_type, inputs)

        if result.success:
            return {
                "success": True,
                "calculation_type": result.calculation_type,
                "data": result.data,
                "formatted_text": result.formatted,
                "audit_id": result.audit.calculation_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Calculation failed",
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculation error: {str(e)}",
        )


@app.get("/calculate/types", tags=["calculations"])
async def calc_types() -> dict:
    """List all supported calculation types."""
    engine = get_tax_engine()
    return {
        "status": "ok",
        "engine": "TaxCalculationEngine",
        "version": "1.0.0",
        "supported": engine.supported_types,
        "count": len(engine.supported_types),
    }


@app.get("/calculate/health", tags=["calculations"])
async def calc_health() -> dict:
    engine = get_tax_engine()
    return {
        "status": "ok",
        "engine": "TaxCalculationEngine",
        "supported": engine.supported_types,
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "1.0.0",
        # Surfaced so a fail-open deployment is visible without reading logs.
        "auth": "required" if auth_required() else "disabled",
    }


@app.post("/answer", response_model=AnswerResponse, tags=["qa"])
async def answer(
    request: AnswerRequest,
    http_request: Request,
    user: Optional[dict] = Depends(require_user),
) -> AnswerResponse:
    # Rate limiting — key on the authenticated user when we have one, since an IP
    # is shared behind NAT and trivially rotated. Falls back to IP for the
    # FBR_AUTH_REQUIRED=false dev path.
    rate_key = f"user:{user['id']}" if user and user.get("id") else (
        f"ip:{http_request.client.host}" if http_request.client else "ip:unknown"
    )
    allowed, remaining = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT} requests per {RATE_WINDOW}s",
        )

    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is required.",
        )

    try:
        orch = _get_orchestrator()
        result = orch.handle(request.query)

        sources = [
            SourceItem(
                chunk_id=s.get("chunk_id", ""),
                document_id=s.get("document_id", ""),
                source=s.get("source", ""),
                source_path=s.get("source_path", ""),
                source_sha256=s.get("source_sha256"),
                page=s.get("page"),
                page_start=s.get("page_start"),
                page_end=s.get("page_end"),
                section=s.get("section"),
                section_reference=s.get("section_reference"),
                section_number=s.get("section_number"),
                law_tag=s.get("law_tag"),
                multi_law_candidate=s.get("multi_law_candidate", False),
                score=s.get("score", 0.0),
                semantic_score=s.get("semantic_score", 0.0),
                bm25_score=s.get("bm25_score", 0.0),
                exact_match=s.get("exact_match", False),
            )
            for s in result.get("sources", [])
        ]

        verification_data = result.get("verification", {})
        checks_data = verification_data.get("checks", {})
        verification = VerificationResult(
            passed=verification_data.get("passed", False),
            checks=VerificationChecks(
                answer_size=VerificationCheck(
                    passed=checks_data.get("answer_size", {}).get("passed", False),
                    reason=checks_data.get("answer_size", {}).get("reason", ""),
                    weak_sentences=checks_data.get("answer_size", {}).get("weak_sentences"),
                ),
                section_consistency=VerificationCheck(
                    passed=checks_data.get("section_consistency", {}).get("passed", False),
                    reason=checks_data.get("section_consistency", {}).get("reason", ""),
                    weak_sentences=checks_data.get("section_consistency", {}).get("weak_sentences"),
                ),
                grounding=VerificationCheck(
                    passed=checks_data.get("grounding", {}).get("passed", False),
                    reason=checks_data.get("grounding", {}).get("reason", ""),
                    weak_sentences=checks_data.get("grounding", {}).get("weak_sentences"),
                ),
                speculation=VerificationCheck(
                    passed=checks_data.get("speculation", {}).get("passed", False),
                    reason=checks_data.get("speculation", {}).get("reason", ""),
                    weak_sentences=checks_data.get("speculation", {}).get("weak_sentences"),
                ),
            ),
            failed_checks=verification_data.get("failed_checks", []),
            reason=verification_data.get("reason", ""),
        )

        return AnswerResponse(
            question=result.get("question", request.query),
            domains=result.get("domains", []),
            primary_domain=result.get("primary_domain", ""),
            multi_domain=result.get("multi_domain", False),
            routing=result.get("routing", {}),
            domain_results=result.get("domain_results", []),
            answer=result.get("answer", ""),
            sources=sources,
            verification=verification,
            grounded=result.get("grounded", False),
        )

    except LLMError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM unavailable",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# =============================================================================
# Supabase Auth Endpoints
# =============================================================================

@app.get("/api/auth/config", tags=["auth"])
async def auth_config():
    """Public endpoint that returns the Supabase URL and anon key.

    The frontend uses this to initialize the Supabase JS client without
    hardcoding credentials in the HTML.
    """
    cfg = get_supabase_config()
    if not cfg["configured"]:
        return {
            "configured": False,
            "message": "Supabase is not configured on the server. "
                       "Set SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_JWT_SECRET.",
        }
    return {
        "configured": True,
        "url": cfg["url"],
        "anon_key": cfg["anon_key"],
    }


@app.get("/api/auth/me", tags=["auth"])
async def auth_me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user (from Supabase JWT).

    Requires: Authorization: Bearer <supabase-jwt>
    """
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "avatar_url": user.get("avatar_url", ""),
        "role": user.get("role", "authenticated"),
    }


@app.get("/api/auth/status", tags=["auth"])
async def auth_status(user: Optional[dict] = Depends(get_optional_user)):
    """Lightweight check: returns whether the request is authenticated.

    Always returns 200; `authenticated` is true/false.
    """
    return {"authenticated": user is not None, "user": user}
