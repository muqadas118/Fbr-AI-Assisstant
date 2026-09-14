"""
Tax Health Router
================

FastAPI router for tax health check operations.
Exposes TaxHealthAPI as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.tax_health import TaxHealthAPI, get_tax_health_api

logger = logging.getLogger("fbr_api.tax_health")

router = APIRouter(prefix="/tax/health", tags=["Tax Health"])


# =============================================================================
# Request Models
# =============================================================================

class HealthCheckRequest(BaseModel):
    """Request for tax health check."""
    ntn: str = Field(..., min_length=1, description="NTN number")
    tax_year: int = Field(
        default=2024,
        ge=2000,
        le=2030,
        description="Tax year"
    )
    # Filing
    itr_filed: bool = Field(default=False, description="Income tax return filed")
    itr_filing_date: Optional[str] = Field(default=None, description="ITR filing date YYYY-MM-DD")
    itr_due_date: Optional[str] = Field(default=None, description="ITR due date YYYY-MM-DD")
    # Income
    declared_income: float = Field(default=0, ge=0, description="Declared income")
    estimated_income: float = Field(default=0, ge=0, description="Estimated income")
    # Tax
    tax_assessed: float = Field(default=0, ge=0, description="Tax assessed")
    tax_paid: float = Field(default=0, ge=0, description="Tax paid")
    # WHT
    wht_collected: float = Field(default=0, ge=0, description="WHT collected")
    wht_deposited: float = Field(default=0, ge=0, description="WHT deposited")
    # Sales Tax
    st_collected: float = Field(default=0, ge=0, description="Sales tax collected")
    st_deposited: float = Field(default=0, ge=0, description="Sales tax deposited")
    # Notices
    notices_outstanding: int = Field(default=0, ge=0, description="Outstanding notices count")


class PenaltyEstimateRequest(BaseModel):
    """Request for penalty estimation."""
    tax_assessed: float = Field(default=0, ge=0, description="Tax assessed")
    tax_paid: float = Field(default=0, ge=0, description="Tax paid")
    days_late_itr: int = Field(default=0, ge=0, description="Days late ITR")
    days_late_payment: int = Field(default=0, ge=0, description="Days late payment")
    wht_shortfall: float = Field(default=0, ge=0, description="WHT shortfall")
    st_shortfall: float = Field(default=0, ge=0, description="Sales tax shortfall")
    is_concealment: bool = Field(default=False, description="Is concealment alleged")


class RiskAnalysisRequest(BaseModel):
    """Request for risk analysis."""
    tax_outstanding: float = Field(default=0, ge=0, description="Tax outstanding")
    notices_count: int = Field(default=0, ge=0, description="Number of notices")
    itr_filed: bool = Field(default=True, description="ITR filed")
    wht_shortfall: float = Field(default=0, ge=0, description="WHT shortfall")
    st_shortfall: float = Field(default=0, ge=0, description="Sales tax shortfall")
    estimated_income: float = Field(default=0, ge=0, description="Estimated income")
    declared_income: float = Field(default=0, ge=0, description="Declared income")


# =============================================================================
# Response Models
# =============================================================================

class HealthIssueResponse(BaseModel):
    """Tax health issue."""
    code: str
    title: str
    description: str
    severity: str
    tax_impact: float
    penalty_estimate: float


class HealthRecommendationResponse(BaseModel):
    """Health recommendation."""
    priority: str
    action: str
    reason: str
    deadline: Optional[str] = None


class TaxHealthResponse(BaseModel):
    """Tax health check response."""
    ntn: str
    tax_year: int
    health_score: float
    health_grade: str
    risk_level: str
    # Filing
    itr_filed: bool
    itr_filing_date: Optional[str] = None
    itr_due_date: Optional[str] = None
    # Tax position
    declared_income: float
    estimated_income: float
    tax_assessed: float
    tax_paid: float
    tax_outstanding: float
    # WHT
    wht_collected: float
    wht_deposited: float
    wht_shortfall: float
    # Sales Tax
    st_collected: float
    st_deposited: float
    st_shortfall: float
    # Scores
    filing_score: float
    deposit_score: float
    compliance_score: float
    reconciliation_score: float
    # Issues
    issues: list[HealthIssueResponse]
    critical_issues_count: int
    total_penalty_exposure: float
    # Recommendations
    recommendations: list[HealthRecommendationResponse]
    generated_at: str


class RiskFactorResponse(BaseModel):
    """Risk factor."""
    code: str
    description: str
    level: str
    weight: float
    mitigation: Optional[str] = None


class RiskAnalysisResponse(BaseModel):
    """Risk analysis response."""
    risk_level: str
    risk_score: float
    factors: list[RiskFactorResponse]


class PenaltyBreakdownResponse(BaseModel):
    """Penalty breakdown."""
    penalty_type: str
    description: str
    amount: float
    days_late: int


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/check", response_model=TaxHealthResponse, dependencies=[Depends(require_user)])
async def run_health_check(request: HealthCheckRequest) -> TaxHealthResponse:
    """
    Run comprehensive tax health check.

    Analyzes filing status, tax payments, WHT compliance, sales tax
    compliance, and generates a health score (0-100) with grade (A+ to F).

    Provide as much data as available for accurate analysis.
    """
    try:
        api = get_tax_health_api()

        data = {
            "ntn": request.ntn,
            "tax_year": request.tax_year,
            "itr_filed": request.itr_filed,
            "itr_filing_date": request.itr_filing_date,
            "itr_due_date": request.itr_due_date,
            "declared_income": request.declared_income,
            "estimated_income": request.estimated_income,
            "tax_assessed": request.tax_assessed,
            "tax_paid": request.tax_paid,
            "wht_collected": request.wht_collected,
            "wht_deposited": request.wht_deposited,
            "st_collected": request.st_collected,
            "st_deposited": request.st_deposited,
            "notices_outstanding": request.notices_outstanding,
        }

        result = api.analyze_with_data(data)

        return TaxHealthResponse(
            ntn=result["ntn"],
            tax_year=result["tax_year"],
            health_score=result["health_score"],
            health_grade=result["health_grade"],
            risk_level=result["risk_level"],
            itr_filed=result["itr_filed"],
            itr_filing_date=result["itr_filing_date"],
            itr_due_date=result["itr_due_date"],
            declared_income=result["declared_income"],
            estimated_income=result["estimated_income"],
            tax_assessed=result["tax_assessed"],
            tax_paid=result["tax_paid"],
            tax_outstanding=result["tax_outstanding"],
            wht_collected=result["wht_collected"],
            wht_deposited=result["wht_deposited"],
            wht_shortfall=result["wht_shortfall"],
            st_collected=result["st_collected"],
            st_deposited=result["st_deposited"],
            st_shortfall=result["st_shortfall"],
            filing_score=result["filing_score"],
            deposit_score=result["deposit_score"],
            compliance_score=result["compliance_score"],
            reconciliation_score=result["reconciliation_score"],
            issues=[HealthIssueResponse(**i) for i in result["issues"]],
            critical_issues_count=result["critical_issues_count"],
            total_penalty_exposure=result["total_penalty_exposure"],
            recommendations=[
                HealthRecommendationResponse(
                    priority=str(r.get("priority", "medium")),
                    action=r.get("action", ""),
                    reason=r.get("reason", ""),
                    deadline=r.get("deadline"),
                )
                for r in result["recommendations"]
            ],
            generated_at=result["generated_at"],
        )
    except Exception as e:
        logger.exception("Error running health check")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run tax health check"
        )


@router.post("/risks", response_model=RiskAnalysisResponse, dependencies=[Depends(require_user)])
async def analyze_risks(request: RiskAnalysisRequest) -> RiskAnalysisResponse:
    """
    Analyze tax risk factors.

    Identifies risk indicators and provides overall risk level assessment.
    """
    try:
        api = get_tax_health_api()

        data = {
            "tax_outstanding": request.tax_outstanding,
            "notices_count": request.notices_count,
            "itr_filed": request.itr_filed,
            "wht_shortfall": request.wht_shortfall,
            "st_shortfall": request.st_shortfall,
            "estimated_income": request.estimated_income,
            "declared_income": request.declared_income,
        }

        result = api.analyze_risk(data)

        return RiskAnalysisResponse(
            risk_level=result["risk_level"],
            risk_score=result["risk_score"],
            factors=[RiskFactorResponse(**f) for f in result["factors"]],
        )
    except Exception as e:
        logger.exception("Error analyzing risks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze tax risks"
        )


@router.post("/penalties", response_model=dict, dependencies=[Depends(require_user)])
async def estimate_penalties(request: PenaltyEstimateRequest) -> dict:
    """
    Estimate penalties for non-compliance.

    Calculates potential penalties for late ITR filing, late tax payment,
    WHT shortfall, and sales tax shortfall.
    """
    try:
        api = get_tax_health_api()

        data = {
            "tax_assessed": request.tax_assessed,
            "tax_paid": request.tax_paid,
            "days_late_itr": request.days_late_itr,
            "days_late_payment": request.days_late_payment,
            "wht_shortfall": request.wht_shortfall,
            "st_shortfall": request.st_shortfall,
            "is_concealment": request.is_concealment,
        }

        return api.estimate_penalties(data)
    except Exception as e:
        logger.exception("Error estimating penalties")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to estimate penalties"
        )


# PUBLIC - intentionally no auth: static metadata for UI
@router.get("/score-guide")
async def get_score_guide() -> dict:
    """
    Get tax health score guide.

    Explains what each score range and grade means.
    """
    return {
        "score_ranges": [
            {"score": "95-100", "grade": "A+", "color": "#16a34a", "message": "Excellent — Highly compliant"},
            {"score": "90-94", "grade": "A", "color": "#16a34a", "message": "Very Good — Minor improvements possible"},
            {"score": "80-89", "grade": "B", "color": "#2563eb", "message": "Good — Some gaps to address"},
            {"score": "70-79", "grade": "C", "color": "#ca8a04", "message": "Average — Focus on compliance"},
            {"score": "60-69", "grade": "D", "color": "#ea580c", "message": "Below Average — Catch up on filings"},
            {"score": "0-59", "grade": "F", "color": "#dc2626", "message": "Critical — Immediate action required"},
        ],
        "checks_performed": [
            "ITR Filing Status",
            "Tax Deposit Compliance",
            "WHT Compliance",
            "Sales Tax Compliance",
            "Income Discrepancy Check",
            "Outstanding Notices",
        ],
    }
