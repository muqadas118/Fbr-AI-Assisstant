"""
Business Reports Router
=======================

"Report Generate" feature for the Business workspace: assemble the data the
business dashboard already shows (compliance calendar, filer status) into a
structured report via the registered report_generator tool. No new facts are
invented — the payload's own data and provenance are rendered by the tool.

Endpoints:
    GET  /business/reports/types   (authed)  -> supported report types
    POST /business/reports/generate (authed) -> markdown/json report content
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.common.rate_limit import RateLimiter
from app.supabase_auth import require_user
from app.tools import get_default_registry

logger = logging.getLogger("fbr_api.business_reports")

router = APIRouter(prefix="/business/reports", tags=["Business Reports"])

_limiter = RateLimiter.from_env(
    "BUSINESS_REPORT_RATE_LIMIT", default_limit=20, default_window=300.0
)


class ReportGenerateRequest(BaseModel):
    report_type: str = Field(
        "overview",
        description="overview | calculation | compliance | documents | notices | research | daily_update",
    )
    title: str = Field(..., min_length=1, max_length=200)
    taxpayer_type: str = Field("business", description="individual | business | company | aop")
    ntn: str = Field("", max_length=20)
    tax_year: int = Field(default_factory=lambda: date.today().year)
    include_calendar: bool = True
    include_filer_status: bool = True


def _section(key: str, fn, errors: list[str]) -> dict:
    """Run one data collector; failures degrade the section, not the report."""
    try:
        return {"available": True, "data": fn()}
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("Report section %s failed: %s", key, exc)
        errors.append(f"{key}: {exc}")
        return {"available": False, "data": None}


def _filer_status_payload(ntn: str) -> dict:
    """Real filer/ATL status for one NTN, or the honest unavailable payload.

    Delegates to the Verification Center, which returns an explicit
    "unavailable" result when no official FBR source is configured. That
    result is rendered as-is — the compliance calendar's score is NOT a
    substitute, and nothing is fabricated.
    """
    from app.verification_center.api import get_verification_api

    result = get_verification_api().verify_filer_status(ntn=ntn)
    details = result.details or {}
    return {
        "ntn": result.value,
        "is_verified": result.is_verified,
        "status": details.get("status", "unknown"),
        "confidence": result.confidence,
        "message": result.message,
        "reason": details.get("reason", ""),
        "verification_source": details.get("verification_source", "unavailable"),
        "format_valid": details.get("format_valid"),
        "format_expected": details.get("format_expected"),
    }


@router.get("/types", dependencies=[Depends(require_user)])
async def get_report_types() -> dict:
    """Report types offered by the generator (from the tool registry contract)."""
    from app.tools.output_tools import REPORT_TYPES

    return {
        "report_types": list(REPORT_TYPES),
        "default": "overview",
        "formats": ["markdown", "json"],
    }


@router.post("/generate", dependencies=[Depends(require_user)])
async def generate_report(request: Request, payload: ReportGenerateRequest) -> dict:
    """Assemble business dashboard data into a structured report.

    Sections mirror the Business Overview page: compliance calendar and
    filer status. Each section is best-effort — a failing section is
    reported in `sections_unavailable` instead of failing the whole report.
    """
    _limiter.check(request)

    from app.compliance_calendar import ComplianceCalendarAPI

    errors: list[str] = []
    sections: dict[str, dict] = {}

    calendar_api = ComplianceCalendarAPI()

    if payload.include_calendar:
        sections["compliance_calendar"] = _section(
            "compliance_calendar",
            lambda: calendar_api.get_dashboard_summary(
                taxpayer_type=payload.taxpayer_type
            ),
            errors,
        )

    if payload.include_filer_status:
        ntn = payload.ntn.strip()
        if not ntn:
            sections["filer_status"] = {
                "available": False,
                "data": None,
                "reason": "no NTN provided",
            }
        else:
            sections["filer_status"] = _section(
                "filer_status",
                lambda: _filer_status_payload(ntn),
                errors,
            )

    report_payload = {
        "report_type": payload.report_type,
        "title": payload.title,
        "sections": sections,
        "taxpayer_type": payload.taxpayer_type,
        "tax_year": payload.tax_year,
        "ntn": payload.ntn or None,
    }

    result = get_default_registry().execute(
        "report_generator",
        {
            "report_type": payload.report_type,
            "title": payload.title,
            "payload": report_payload,
            "format": "markdown",
        },
    )
    # ToolResult is a dataclass — support both attribute and dict access.
    ok = getattr(result, "ok", None)
    if ok is None and isinstance(result, dict):
        ok = result.get("ok")
    if not ok:
        error = getattr(result, "error", None) or (
            result.get("error") if isinstance(result, dict) else None
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Report generation failed.",
        )

    data = getattr(result, "data", None)
    if data is None and isinstance(result, dict):
        data = result.get("data")
    data = data or {}
    return {
        "report_type": data.get("report_type", payload.report_type),
        "format": data.get("format", "markdown"),
        "generated_at": data.get("generated_at"),
        "content": data.get("content", ""),
        "sections_available": [k for k, v in sections.items() if v.get("available")],
        "sections_unavailable": [k for k, v in sections.items() if not v.get("available")],
        "errors": errors,
    }
