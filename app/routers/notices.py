"""
Notice Analyzer Router
=====================

FastAPI router for FBR notice analysis operations.
Exposes NoticeAnalyzer as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field, field_validator

from app.notice_analyzer import NoticeAnalyzer, get_notice_analyzer

logger = logging.getLogger("fbr_api.notices")

router = APIRouter(prefix="/notices", tags=["FBR Notices"])


# =============================================================================
# Request Models
# =============================================================================

class NoticeAnalysisRequest(BaseModel):
    """Request to analyze a FBR notice."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=500000,
        description="Notice text (extracted from PDF/image, or typed manually)"
    )
    notice_id: Optional[str] = Field(
        default=None,
        description="Optional notice reference ID"
    )

    @field_validator("text")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class NoticeTextRequest(BaseModel):
    """Simple text-based notice analysis."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=500000,
        description="Notice text"
    )


# =============================================================================
# Response Models
# =============================================================================

class ActionStepResponse(BaseModel):
    """Action plan step."""
    step_number: int
    title: str
    description: str
    documents_needed: list[str]
    estimated_hours: float
    priority: str


class ActionPlanResponse(BaseModel):
    """Action plan for responding to notice."""
    notice_type: str
    summary: str
    total_steps: int
    estimated_total_hours: float
    requires_professional_help: bool
    requires_payment: bool
    steps: list[ActionStepResponse]
    common_mistakes: list[str]
    helpful_tips: list[str]
    references: list[str]


class AppealInfoResponse(BaseModel):
    """Appeal guidance."""
    is_appealable: bool
    forum: str
    time_limit_days: int
    forms_required: list[str]
    documents_needed: list[str]
    fees_required: str
    common_grounds: list[str]
    success_factors: list[str]
    typical_success_rate: str
    estimated_cost: str
    notes: list[str]


class NoticeAnalysisResponse(BaseModel):
    """Complete notice analysis."""
    analysis_id: str
    timestamp: str
    duration_ms: float

    # Classification
    notice_type: str
    confidence: float
    is_critical: bool
    is_appealable: bool

    # Extracted info
    taxpayer_name: Optional[str] = None
    taxpayer_ntn: Optional[str] = None
    notice_id: Optional[str] = None
    issue_date: Optional[str] = None
    tax_years: list[str]
    sections_cited: list[str]
    total_demanded: Optional[float] = None
    tax_amount: Optional[float] = None
    penalty_amount: Optional[float] = None

    # Deadline
    deadline_date: Optional[str] = None
    days_remaining: Optional[int] = None
    urgency_level: str

    # Plans
    action_plan: Optional[ActionPlanResponse] = None
    appeal_guide: Optional[AppealInfoResponse] = None

    # Text
    formatted_text: str
    summary: str


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/analyze", response_model=NoticeAnalysisResponse, dependencies=[Depends(require_user)])
async def analyze_notice(request: NoticeAnalysisRequest) -> NoticeAnalysisResponse:
    """
    Analyze a FBR notice/show cause/order.

    Takes notice text (from PDF, image OCR, or manual input) and returns:
    - Notice type classification
    - Key information extraction (NTN, amounts, dates, sections)
    - Response deadline calculation
    - Step-by-step action plan
    - Appeal guidance (if applicable)
    """
    try:
        analyzer = get_notice_analyzer()
        result = analyzer.analyze(request.text)

        # Convert action plan
        action_plan = None
        if result.action_plan:
            ap = result.action_plan
            action_plan = ActionPlanResponse(
                notice_type=ap.notice_type.value if hasattr(ap.notice_type, 'value') else str(ap.notice_type),
                summary=ap.summary,
                total_steps=ap.total_steps,
                estimated_total_hours=ap.estimated_total_hours,
                requires_professional_help=ap.requires_professional_help,
                requires_payment=getattr(ap, "requires_payment", False),
                steps=[
                    ActionStepResponse(
                        step_number=s.step_number,
                        title=s.title,
                        description=s.description,
                        documents_needed=s.documents_needed or [],
                        estimated_hours=s.estimated_hours,
                        priority=s.priority,
                    )
                    for s in (ap.steps or [])
                ],
                common_mistakes=getattr(ap, "common_mistakes", []) or [],
                helpful_tips=getattr(ap, "helpful_tips", []) or [],
                references=getattr(ap, "references", []) or [],
            )

        # Convert appeal guide
        appeal_guide = None
        if result.appeal_guide:
            ag = result.appeal_guide
            appeal_guide = AppealInfoResponse(
                is_appealable=ag.is_appealable,
                forum=ag.forum,
                time_limit_days=ag.time_limit_days,
                forms_required=ag.forms_required or [],
                documents_needed=ag.documents_needed or [],
                fees_required=ag.fees_required or "N/A",
                common_grounds=ag.common_grounds or [],
                success_factors=ag.success_factors or [],
                typical_success_rate=ag.typical_success_rate or "N/A",
                estimated_cost=ag.estimated_cost or "N/A",
                notes=ag.notes or [],
            )

        return NoticeAnalysisResponse(
            analysis_id=result.analysis_id,
            timestamp=result.timestamp,
            duration_ms=result.duration_ms,
            notice_type=result.notice_type,
            confidence=result.confidence,
            is_critical=result.is_critical,
            is_appealable=result.is_appealable,
            taxpayer_name=result.taxpayer_name,
            taxpayer_ntn=result.taxpayer_ntn,
            notice_id=result.notice_id,
            issue_date=result.issue_date,
            tax_years=result.tax_years,
            sections_cited=result.sections_cited,
            total_demanded=result.total_demanded,
            tax_amount=result.tax_amount,
            penalty_amount=result.penalty_amount,
            deadline_date=result.deadline_date,
            days_remaining=result.days_remaining,
            urgency_level=result.urgency_level,
            action_plan=action_plan,
            appeal_guide=appeal_guide,
            formatted_text=result.formatted_text,
            summary=result.summary,
        )
    except Exception as e:
        logger.exception("Error analyzing notice")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze FBR notice"
        )


@router.post("/analyze/text", response_model=NoticeAnalysisResponse, dependencies=[Depends(require_user)])
async def analyze_notice_text(request: NoticeTextRequest) -> NoticeAnalysisResponse:
    """
    Analyze notice from plain text.

    Same as /analyze but takes simple text field.
    """
    return await analyze_notice(NoticeAnalysisRequest(text=request.text))


# PUBLIC - intentionally no auth: static metadata for UI
@router.get("/types")
async def get_notice_types() -> dict:
    """
    List all supported FBR notice types.

    Returns all notice types the analyzer can classify.
    """
    try:
        from app.notice_analyzer.classifier import NoticeType
        types = [t.value for t in NoticeType]
        return {
            "total": len(types),
            "notice_types": types,
            "categories": [
                "Income Tax",
                "Sales Tax",
                "Federal Excise",
                "Customs",
                "Withholding Tax",
                "Wealth Statement",
                "Sales Tax Federal",
                "Professional Tax",
            ],
        }
    except Exception as e:
        logger.exception("Error listing notice types")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notice types"
        )
