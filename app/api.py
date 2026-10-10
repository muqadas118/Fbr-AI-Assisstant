import asyncio
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.orchestrator import AgentOrchestrator
from app.calculations import get_tax_engine
from app.language import (
    LANG_EN,
    LANG_ROMAN_UR,
    LANG_UR,
    normalize_language,
    resolve_language,
)
from app.llm import LLMError
from app.routers import (
    assistant_router,
    auth_router,
    business_reports_router,
    calendar_router,
    documents_router,
    invoices_router,
    monitor_router,
    notices_router,
    personalization_router,
    quota_router,
    tax_health_router,
    team_router,
    uploads_router,
    vault_router,
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
# Buckets are per-scope so a cheap endpoint (/calculate) cannot be starved
# by an expensive one (/answer) and vice versa:
#   answer    : 10 req / 60s per client (LLM round-trips are costly)
#   calculate : 30 req / 60s per client (deterministic local math)
#   verify-batch: 10 req / 60s per IP (defense-in-depth under auth)
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds
CALC_RATE_LIMIT = 30
_rate_store: dict[str, list[datetime]] = defaultdict(list)


def _check_rate_limit(client_key: str, limit: int = RATE_LIMIT) -> tuple[bool, int]:
    """Check if a client is within the rate limit. Returns (allowed, remaining).

    `client_key` is "<scope>:user:<id>" when authenticated,
    "<scope>:ip:<addr>" otherwise. NOTE: in-memory and per-process — it
    resets on restart and is not shared across uvicorn workers. Move to
    Redis before relying on it in production.
    """
    now = datetime.now()
    window_start = now - timedelta(seconds=RATE_WINDOW)

    # Clean old entries
    _rate_store[client_key] = [
        ts for ts in _rate_store[client_key] if ts > window_start
    ]

    if len(_rate_store[client_key]) >= limit:
        return False, 0

    _rate_store[client_key].append(now)
    remaining = limit - len(_rate_store[client_key])
    return True, remaining


# Rate-limit POST /verify/batch with the shared in-memory limiter.
# verify.py is out of scope for this pass, so attach here in api.py.
# Kept IP-keyed as defense-in-depth; FULL-AUTH (2026-09-13) added
# Depends(require_user) on the route itself, so user identity is now
# available for a future user-keyed upgrade like POST /answer.
async def _verify_batch_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, _remaining = _check_rate_limit("verify-batch:ip:" + client_ip)
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


class RequestLoggingMiddleware:
    """Pure-ASGI request logging (audit trail).

    Deliberately NOT a function-style BaseHTTPMiddleware: those buffer
    StreamingResponse bodies (call_next only returns after the body
    finishes), which defeats SSE streaming — /assistant/ask/stream
    tokens would only reach the client when the whole answer completed.
    This passes every ASGI message through untouched and only intercepts
    http.response.start to log the response and stamp X-Response-Time.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start_time = time.time()
        client_ip = (scope.get("client") or ("unknown", 0))[0]
        method = scope.get("method", "")
        path = scope.get("path", "")
        logger.info(f"Request | {method} {path} | IP: {client_ip}")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                duration = time.time() - start_time
                logger.info(
                    f"Response | {method} {path} | "
                    f"Status: {message.get('status', 0)} | Duration: {duration:.3f}s"
                )
                message.setdefault("headers", []).append(
                    (b"x-response-time", f"{duration:.3f}s".encode())
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(f"Response | {method} {path} | Unhandled error")
            raise


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
        v = v.strip()
        if not v:
            raise ValueError("query must not be blank")
        return v


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


_CANONICAL_CHECKS = (
    "answer_size",
    "section_consistency",
    "grounding",
    "speculation",
)


def _panel_checks(verification_data: dict, result: dict) -> dict:
    """
    Normalize the four verification-panel checks.

    Single-domain responses already carry the canonical four-check shape
    and pass through unchanged. Multi-domain aggregates instead carry a
    per-domain boolean map, which previously rendered as all-Fail in the
    UI even for domains that fully passed. For aggregates, each panel
    check is the AND of that check across the grounded domains, so the
    panel reflects what the delivered content actually passed; the
    overall badge and failed_checks list still report unverified domains.
    """
    checks_data = verification_data.get("checks", {}) or {}
    if all(isinstance(checks_data.get(name), dict) for name in _CANONICAL_CHECKS):
        return checks_data
    grounded = [
        d for d in result.get("domain_results", []) if d.get("grounded")
    ]
    panel: dict = {}
    for name in _CANONICAL_CHECKS:
        details = [
            ((d.get("verification", {}) or {}).get("checks", {}) or {}).get(name, {})
            for d in grounded
        ]
        passed = bool(details) and all(
            (item or {}).get("passed", False) for item in details
        )
        panel[name] = {
            "passed": passed,
            "reason": verification_data.get("reason", ""),
            "weak_sentences": None,
        }
    return panel


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

app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(tax_health_router)
app.include_router(notices_router)
app.include_router(documents_router)
app.include_router(invoices_router)
app.include_router(verify_router)
app.include_router(monitor_router)
app.include_router(team_router)
app.include_router(workspaces_router)
app.include_router(uploads_router)
app.include_router(assistant_router)
app.include_router(vault_router)
app.include_router(business_reports_router)
# Self-learning / personalization (behavioural signals + per-user recommendations)
app.include_router(personalization_router)
# Per-user daily quotas (messages + chat file uploads, reset at local midnight)
app.include_router(quota_router)

# SECURITY NOTE - auth state (FULL-AUTH, 2026-09-13):
# Every feature router mounted above enforces Depends(require_user) on its
# routes. Of the 80 routes registered on this app, 62 require a valid
# bearer token (backend session token or Supabase JWT) and 18 are
# intentionally public:
#   - auth bootstrap: POST /auth/signup, POST /auth/login, POST /team/register,
#     POST /team/login, GET /team/roles
#   - static reference data: GET /notices/types, GET /documents/types,
#     GET /calendar/types, GET /calculate/types, GET /calculate/health,
#     GET /vault/health, GET /monitor/event-types,
#     GET /tax/health/score-guide, GET /workspaces/health
#   - health/diagnostics: GET /health, GET /api/auth/config,
#     GET /api/auth/status (GET /api/auth/me takes the Supabase JWT path)
# POST /answer and POST /calculate also enforce require_user directly here.
# require_user honors the FBR_AUTH_REQUIRED=false dev bypass (fail-open) and
# is the single gate for both token types — do not add per-router auth here.

# CORS Middleware - Configure for production frontend origin
# CORS_ORIGINS env (comma-separated) overrides the localhost defaults.
_cors_env = os.environ.get("CORS_ORIGINS", "")
_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
if not _origins:
    _origins = [
        "http://localhost:5173",  # Local dev
        "http://127.0.0.1:5173",  # Local dev (IPv4 loopback)
        "http://localhost:5174",  # Local dev (fallback port when 5173 is taken)
        "http://127.0.0.1:5174",  # Local dev (IPv4 loopback, fallback port)
        "http://localhost:3000",  # Alternative local dev
        "http://127.0.0.1:3000",  # Alternative local dev (IPv4 loopback)
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

# Register request logging middleware (pure-ASGI: streams pass through)
app.add_middleware(RequestLoggingMiddleware)


_orchestrator: Optional[AgentOrchestrator] = None
_answer_cache: dict[str, tuple[float, AnswerResponse]] = {}
_cache_lock = threading.Lock()
_ANSWER_CACHE_TTL_S = 300  # 5 minutes; FBR law changes don't move faster
_ANSWER_CACHE_MAX = 100


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
    # Rate limiting - dedicated 30 req/60s bucket for the deterministic
    # local math endpoints (POST /answer keeps its own 10 req/60s bucket).
    rate_key = "calculate:user:" + str(user.get("id")) if user and user.get("id") else ("calculate:ip:" + str(request.client.host) if request.client else "calculate:ip:unknown")
    allowed, _remaining = _check_rate_limit(rate_key, CALC_RATE_LIMIT)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {CALC_RATE_LIMIT} requests per {RATE_WINDOW}s",
        )

    try:
        body = await request.json()
        calc_type = body.get("calc_type", "income_tax")
        inputs = body.get("inputs", {})
        if not isinstance(inputs, dict) or not inputs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No inputs provided: 'inputs' must be a non-empty object.",
            )

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


# Prometheus scrape target for monitoring/prometheus.yml (job "fbr-api").
# Off by default: an unauthenticated endpoint that only returns an empty body
# is not worth exposing, so deployments opt in with FBR_METRICS_ENABLED.
# The collector itself is app/deployment/metrics.py (MetricsCollector), which
# renders the Prometheus text exposition format verbatim.
_METRICS_ENABLED = os.environ.get("FBR_METRICS_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on",
)

if _METRICS_ENABLED:
    _PROCESS_START_TIME = time.time()

    @app.get("/metrics", tags=["monitoring"])
    async def metrics() -> PlainTextResponse:
        """Export collected metrics in the Prometheus text format."""
        from app.deployment.metrics import get_metrics_collector

        collector = get_metrics_collector()
        collector.inc_counter("fbr_metrics_scrapes_total")
        collector.set_gauge(
            "fbr_process_uptime_seconds", time.time() - _PROCESS_START_TIME
        )
        return PlainTextResponse(
            collector.to_prometheus(),
            media_type="text/plain; version=0.0.4",
        )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "1.0.0",
        # Surfaced so a fail-open deployment is visible without reading logs.
        "auth": "required" if auth_required() else "disabled",
    }


_TAX_REDUCER_REFUSALS = (
    "The provided FBR documents do not contain enough information to answer this.",
    "The retrieved evidence does not support a verified answer.",
)

# Localized prose for the deterministic Tax Reducer rendering built by
# _augment_tax_reducer below. app.language.localize owns the answer-level
# kinds (no_evidence | ambiguous_section | unverified | llm_unavailable |
# placeholder); these are /answer Tax-Reducer rendering strings with no
# matching kind, so their translations live here next to the code that emits
# them (same pattern as app/routers/assistant.py _TOOL_STATUS_TEXT). The
# LANG_EN entry of every key is the EXACT wording currently rendered, so
# English users see a byte-identical report (same lines, same order, same
# numbers). The opportunity titles / descriptions / estimated_impact /
# required_evidence / legal_basis come from app.tools.tax_optimization and
# are rendered as-is — they are the tool's own content, not translated here.
_TAX_REDUCER_TEXT: dict[str, dict[str, str]] = {
    "unlawful_refusal": {
        LANG_EN: (
            "This tool only supports lawful tax planning. It cannot help "
            "conceal income, fabricate expenses, falsify records, or evade taxes."
        ),
        LANG_ROMAN_UR: (
            "Ye tool sirf qanooni tax planning support karta hai. Ye income "
            "chupane, kharcha ghalat ya fabricate karne, records jhooti "
            "batane ya tax evasion mein madad nahi kar sakta."
        ),
        LANG_UR: (
            "یہ ٹول صرف قانونی ٹیکس پلاننگ کی حمایت کرتا ہے۔ یہ آمدنی چھپانے، "
            "جعلی اخراجات بنانے، ریکارڈ جھوٹے بتانے یا ٹیکس سے بچنے میں مدد "
            "نہیں کر سکتا۔"
        ),
    },
    "header": {
        LANG_EN: "LAWFUL TAX-SAVING ANALYSIS (deterministic estimate)",
        LANG_ROMAN_UR: "Qanooni tax bachne ka tajziya (deterministic andaza)",
        LANG_UR: "قانونی ٹیکس بچانے کا تجزیہ (deterministic تخمینہ)",
    },
    "taxpayer": {
        LANG_EN: "Taxpayer: ",
        LANG_ROMAN_UR: "Taxpayer: ",
        LANG_UR: "ٹیکس دہندہ: ",
    },
    "tax_type": {
        LANG_EN: "Tax type: ",
        LANG_ROMAN_UR: "Tax ki qism: ",
        LANG_UR: "ٹیکس کی قسم: ",
    },
    "tax_year": {
        LANG_EN: "Tax year: ",
        LANG_ROMAN_UR: "Tax ka saal: ",
        LANG_UR: "ٹیکس کا سال: ",
    },
    "baseline_income": {
        LANG_EN: "Baseline taxable income: ",
        LANG_ROMAN_UR: "Bunyadi taxable income: ",
        LANG_UR: "بنیادی taxable income: ",
    },
    "baseline_tax": {
        LANG_EN: "Baseline estimated tax: ",
        LANG_ROMAN_UR: "Bunyadi estimated tax: ",
        LANG_UR: "بنیادی تخمینہ شدہ ٹیکس: ",
    },
    "optimized_income": {
        LANG_EN: "Optimized taxable income (after lawful deductions/incentives): ",
        LANG_ROMAN_UR: "Optimized taxable income (qanooni deductions/incentives ke baad): ",
        LANG_UR: "Optimized taxable income (قانونی deductions/incentives کے بعد): ",
    },
    "optimized_tax": {
        LANG_EN: "Optimized estimated tax: ",
        LANG_ROMAN_UR: "Optimized estimated tax: ",
        LANG_UR: "Optimized estimated tax: ",
    },
    "savings": {
        LANG_EN: "Estimated lawful savings: ",
        LANG_ROMAN_UR: "Andaza qanooni bachat: ",
        LANG_UR: "تخمینہ شدہ قانونی بچت: ",
    },
    "net_liability": {
        LANG_EN: "Net liability after payments already made: ",
        LANG_ROMAN_UR: "Jama kiye gaye payments ke baad net liability: ",
        LANG_UR: "کی گئی ادائیگیوں کے بعد خالص ذمہ داری: ",
    },
    "opportunities_header": {
        LANG_EN: "LAWFUL OPPORTUNITIES ({count}):",
        LANG_ROMAN_UR: "Qanooni opportunities ({count}):",
        LANG_UR: "قانونی مواقع ({count}):",
    },
    "no_opportunities": {
        LANG_EN: (
            "No specific lawful opportunities matched the provided profile; "
            "the baseline vs optimized comparison above still applies "
            "where deductions/incentives were provided."
        ),
        LANG_ROMAN_UR: (
            "Diye gaye profile se koi khaas qanooni opportunity match nahi "
            "hui; jahan deductions/incentives diye gaye hain wahan upar wala "
            "baseline vs optimized comparison phir bhi mustanad hai."
        ),
        LANG_UR: (
            "دیے گئے پروفائل سے کوئی خاص قانونی موقعہ مماثل نہیں ہوا؛ جہاں "
            "deductions/incentives دیے گئے ہیں وہاں اوپر والا baseline vs "
            "optimized موازنہ پھر بھی لاگو ہوتا ہے۔"
        ),
    },
    "impact": {
        LANG_EN: "Impact: ",
        LANG_ROMAN_UR: "Asar: ",
        LANG_UR: "اثر: ",
    },
    "evidence_needed": {
        LANG_EN: "Evidence needed: ",
        LANG_ROMAN_UR: "Zaroori dastavez: ",
        LANG_UR: "درکار دستاویزات: ",
    },
    "legal_basis": {
        LANG_EN: "Legal basis: ",
        LANG_ROMAN_UR: "Qanooni bunyaad: ",
        LANG_UR: "قانونی بنیاد: ",
    },
    "estimate_disclaimer": {
        LANG_EN: (
            "Baseline and optimized figures are estimates from a "
            "documented slab table; final liability requires FBR "
            "verification of eligibility and evidence."
        ),
        LANG_ROMAN_UR: (
            "Baseline aur optimized figures ek documented slab table se liye "
            "gaye andaze hain; final liability ke liye FBR verification aur "
            "evidence ki zaroorat hai."
        ),
        LANG_UR: (
            "Baseline اور optimized figures ایک documented slab table سے لیے "
            "گئے اندازے ہیں؛ final liability کے لیے FBR verification اور "
            "evidence کی ضرورت ہے۔"
        ),
    },
}


def _loc(kind: str, language: Optional[str]) -> str:
    """Localized Tax Reducer text for ``kind``; English when unrecognized.

    ``language`` accepts the canonical tags from ``app.language`` as well as
    loose/None values, which normalize to English.
    """
    variants = _TAX_REDUCER_TEXT[kind]
    return variants.get(normalize_language(language), variants[LANG_EN])


def _augment_tax_reducer(query: str, result: dict) -> dict:
    """Deterministic Tax Reducer support for /answer.

    The Tax Reducer frontend sends a structured "Lawful tax reduction
    analysis ..." query. When the canonical RAG pipeline could not ground
    it (a refusal), run the registered tax_optimization tool directly —
    it is deterministic (no LLM, no retrieval), so it always produces a
    concrete, lawful savings estimate with sources. The refusal text is
    replaced by a human-readable rendering of the tool's structured
    result; the raw structured data is attached additively.

    Every rendered line follows the query language (resolve_language);
    each figure, rate and section is quoted verbatim.
    """
    # Resolved once, before any early return, so the refusal and the report
    # below always speak the user's language.
    language = resolve_language(query)

    lowered = (query or "").lower()
    if "lawful tax reduction analysis" not in lowered:
        return result

    answer_text = str(result.get("answer", "") or "").strip()
    is_refusal = (not answer_text) or (
        any(refusal in answer_text for refusal in _TAX_REDUCER_REFUSALS)
    )
    if not is_refusal:
        return result

    try:
        from app.tools import get_default_registry
        from app.tools.tax_optimization import (
            detect_unlawful_intent,
            extract_tax_reducer_payload,
        )

        if detect_unlawful_intent(query):
            result["answer"] = _loc("unlawful_refusal", language)
            return result

        payload = extract_tax_reducer_payload(query)
        if payload is None:
            # Not enough structured data (no tax year / income) — keep the refusal.
            return result

        tool_result = get_default_registry().execute("tax_optimization", payload)
        if not (tool_result.ok and isinstance(tool_result.data, dict)):
            return result

        data = tool_result.data
        baseline = data.get("baseline", {}) or {}
        optimized = data.get("optimized", {}) or {}

        def _fmt(v: Any) -> str:
            try:
                return f"PKR {float(v):,.2f}"
            except (TypeError, ValueError):
                return str(v)

        # Labels come from _TAX_REDUCER_TEXT; every value below (entity type,
        # tax type, year) and every figure keeps its exact original form.
        entity = str(data.get('entity_type', 'individual')).title()
        tax_type_label = str(data.get('tax_type', 'income_tax')).replace('_', ' ').title()
        lines = [
            _loc("header", language),
            "",
            f"{_loc('taxpayer', language)}{entity} — "
            f"{_loc('tax_type', language)}{tax_type_label} — "
            f"{_loc('tax_year', language)}{data.get('tax_year', '—')}",
            "",
            f"{_loc('baseline_income', language)}{_fmt(baseline.get('taxable_income', 0))}",
            f"{_loc('baseline_tax', language)}{_fmt(baseline.get('estimated_tax', 0))}",
            f"{_loc('optimized_income', language)}{_fmt(optimized.get('taxable_income', 0))}",
            f"{_loc('optimized_tax', language)}{_fmt(optimized.get('estimated_tax', 0))}",
            f"{_loc('savings', language)}{_fmt(data.get('estimated_savings', 0))}",
            f"{_loc('net_liability', language)}{_fmt(data.get('net_liability_after_payments', 0))}",
            "",
        ]
        opportunities = data.get("opportunities") or []
        if opportunities:
            lines.append(_loc("opportunities_header", language).format(count=len(opportunities)))
            for opp in opportunities:
                if isinstance(opp, dict):
                    lines.append(
                        f"- {opp.get('title', 'Opportunity')} — "
                        f"{opp.get('description', '')}"
                    )
                    impact = str(opp.get("estimated_impact", "") or "").strip()
                    if impact:
                        lines.append(f"  {_loc('impact', language)}{impact}")
                    evidence = opp.get("required_evidence") or []
                    if evidence:
                        lines.append(
                            f"  {_loc('evidence_needed', language)}"
                            f"{', '.join(str(x) for x in evidence)}"
                        )
                    lines.append(f"  {_loc('legal_basis', language)}{opp.get('legal_basis', '—')}")
                else:
                    lines.append(f"- {opp}")
        else:
            lines.append(_loc("no_opportunities", language))
        lines.extend([
            "",
            # The tool's own disclaimer when present, otherwise the localized one.
            str(data.get("estimate_disclaimer") or _loc("estimate_disclaimer", language)),
        ])

        result["answer"] = "\n".join(lines)
        result["grounded"] = True
        result["tax_optimization"] = data
        # Normalize the tool's source dicts into the SourceItem shape the
        # API schema (and the frontend citation list) expects.
        norm_sources = []
        for s in data.get("sources", []) or []:
            if isinstance(s, dict):
                norm_sources.append({
                    **s,
                    "source": s.get("source") or s.get("document") or s.get("title", ""),
                    "section": s.get("section") or s.get("legal_reference"),
                })
            else:
                norm_sources.append(s)
        result["sources"] = norm_sources or result.get("sources", [])
        result["verification"] = {
            "passed": True,
            "checks": {
                "answer_size": {"passed": True, "reason": "deterministic tax_optimization tool output"},
                "section_consistency": {"passed": True, "reason": "deterministic tax_optimization tool output"},
                "grounding": {"passed": True, "reason": "figures computed by the registered tax_optimization tool"},
                "speculation": {"passed": True, "reason": "deterministic tax_optimization tool output"},
            },
            "failed_checks": [],
            "reason": "tool-computed result (deterministic engine; figures quoted verbatim)",
        }
        return result
    except Exception as e:  # noqa: BLE001
        logging.warning("Tax Reducer augmentation failed: %s", e)
        return result


def _serialize_answer(query: str, result: dict) -> AnswerResponse:
    """Build the typed AnswerResponse from an orchestrator result dict."""
    # FIX: refusal (grounded=False) ke saath citations mat bhejo — frontend
    # sources dekh kar refusal ke saath bhi citations dikhata hai.
    sources_raw = [] if not result.get("grounded") else (result.get("sources", []) or [])
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
        for s in sources_raw
    ]

    verification_data = result.get("verification", {})
    checks_data = _panel_checks(verification_data, result)
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
        question=result.get("question", query),
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


@app.post("/answer", response_model=AnswerResponse, tags=["qa"])
async def answer(
    request: AnswerRequest,
    http_request: Request,
    user: Optional[dict] = Depends(require_user),
) -> AnswerResponse:
    # Rate limiting — key on the authenticated user when we have one, since an IP
    # is shared behind NAT and trivially rotated. Falls back to IP for the
    # FBR_AUTH_REQUIRED=false dev path.
    rate_key = f"answer:user:{user['id']}" if user and user.get("id") else (
        f"answer:ip:{http_request.client.host}" if http_request.client else "answer:ip:unknown"
    )
    allowed, _remaining = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT} requests per {RATE_WINDOW}s",
        )

    cache_key = request.query.lower()
    now = time.time()
    with _cache_lock:
        hit = _answer_cache.get(cache_key)
        if hit is not None and now - hit[0] < _ANSWER_CACHE_TTL_S:
            return hit[1]

    try:
        orch = _get_orchestrator()
        # orch.handle() does CPU/network-bound RAG + LLM work; run it in a
        # worker thread so it cannot stall the event loop (a slow LLM call
        # used to block /calculate and other endpoints for its full duration).
        result = await asyncio.to_thread(orch.handle, request.query)

        # Tax Reducer: when the RAG pipeline refused but the query carries
        # structured tax-reducer data, fall back to the deterministic
        # tax_optimization tool so the user always gets a concrete analysis.
        result = _augment_tax_reducer(request.query, result)

        response = _serialize_answer(request.query, result)

        with _cache_lock:
            if len(_answer_cache) >= _ANSWER_CACHE_MAX:
                oldest = min(_answer_cache, key=lambda k: _answer_cache[k][0])
                del _answer_cache[oldest]
            _answer_cache[cache_key] = (now, response)

        return response

    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM unavailable",
        )
    except Exception as e:
        logger.error("POST /answer failed for query %r: %s", request.query[:120], e, exc_info=True)
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
