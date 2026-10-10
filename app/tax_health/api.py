"""
Tax Health API - Production-Grade
=============================

High-level API for tax health operations.
"""

from dataclasses import dataclass
from typing import Optional

from app.tax_health.health_engine import TaxHealthEngine, TaxHealthProfile
from app.tax_health.risk_analyzer import RiskAnalyzer
from app.tax_health.penalty_calculator import PenaltyCalculator


@dataclass
class TaxHealthAPI:
    """High-level API for tax health operations."""

    def __init__(self):
        self.engine = TaxHealthEngine()
        self.risk_analyzer = RiskAnalyzer()
        self.penalty_calculator = PenaltyCalculator()

    def run_health_check(
        self,
        ntn: str,
        tax_year: int = 2024,
        data: Optional[dict] = None,
    ) -> dict:
        """
        Run a health check.

        Without filing/payment data there is nothing to analyse, so this
        returns an explicit insufficient-data result instead of a placeholder
        that reads like a completed check (the previous "pending_data"
        template was reported to users as "Tax health checked", ok=True).

        When the caller supplies `data`, the check is computed for real via
        analyze_with_data() - the same path POST /tax/health/check uses.
        """
        if data:
            return self.analyze_with_data({"ntn": ntn, "tax_year": tax_year, **data})

        return {
            "ntn": ntn,
            "tax_year": tax_year,
            "status": "insufficient_data",
            "ok": False,
            "message": (
                "No tax data was supplied, so no health score was calculated. "
                "Provide the fields in required_fields (or POST /tax/health/check) "
                "to get a real result."
            ),
            "required_fields": [
                "itr_filed", "itr_filing_date", "declared_income",
                "tax_assessed", "tax_paid", "wht_collected",
                "wht_deposited", "st_collected", "st_deposited",
            ],
        }

    def analyze_with_data(self, data: dict) -> dict:
        """Analyze health with provided data."""
        profile = self.engine.analyze(
            ntn=data.get("ntn", ""),
            tax_year=data.get("tax_year", 2024),
            itr_filed=data.get("itr_filed", False),
            itr_filing_date=data.get("itr_filing_date"),
            itr_due_date=data.get("itr_due_date"),
            declared_income=data.get("declared_income", 0),
            estimated_income=data.get("estimated_income", 0),
            tax_assessed=data.get("tax_assessed", 0),
            tax_paid=data.get("tax_paid", 0),
            wht_collected=data.get("wht_collected", 0),
            wht_deposited=data.get("wht_deposited", 0),
            st_collected=data.get("st_collected", 0),
            st_deposited=data.get("st_deposited", 0),
            notices_outstanding=data.get("notices_outstanding", 0),
        )

        return self._profile_to_dict(profile)

    def _profile_to_dict(self, profile: TaxHealthProfile) -> dict:
        """Convert profile to dict."""
        return {
            "ntn": profile.ntn,
            "tax_year": profile.tax_year,
            "health_score": profile.health_score,
            "health_grade": profile.health_grade,
            "risk_level": profile.risk_level,
            # Filing
            "itr_filed": profile.itr_filed,
            "itr_filing_date": profile.itr_filing_date,
            "itr_due_date": profile.itr_due_date,
            # Tax position
            "declared_income": profile.declared_income,
            "estimated_income": profile.estimated_income,
            "tax_assessed": profile.tax_assessed,
            "tax_paid": profile.tax_paid,
            "tax_outstanding": profile.tax_outstanding,
            # WHT
            "wht_collected": profile.wht_collected,
            "wht_deposited": profile.wht_deposited,
            "wht_shortfall": profile.wht_shortfall,
            # Sales Tax
            "st_collected": profile.sales_tax_collected,
            "st_deposited": profile.sales_tax_deposited,
            "st_shortfall": profile.st_shortfall,
            # Scores
            "filing_score": profile.filing_score,
            "deposit_score": profile.deposit_score,
            "compliance_score": profile.compliance_score,
            "reconciliation_score": profile.reconciliation_score,
            # Issues
            "issues": [
                {
                    "code": i.code,
                    "title": i.title,
                    "description": i.description,
                    "severity": i.severity.value,
                    "tax_impact": i.tax_impact,
                    "penalty_estimate": i.penalty_estimate,
                }
                for i in profile.issues
            ],
            "critical_issues_count": profile.critical_issues_count,
            "total_penalty_exposure": profile.total_penalty_exposure,
            # Recommendations
            "recommendations": [
                {
                    "priority": r.priority,
                    "action": r.action,
                    "reason": r.reason,
                    "deadline": r.deadline,
                }
                for r in profile.recommendations
            ],
            "generated_at": profile.generated_at,
        }

    def estimate_penalties(self, data: dict) -> dict:
        """Estimate penalties for non-compliance."""
        result = self.penalty_calculator.estimate_total_penalties(
            tax_assessed=data.get("tax_assessed", 0),
            tax_paid=data.get("tax_paid", 0),
            days_late_itr=data.get("days_late_itr", 0),
            days_late_payment=data.get("days_late_payment", 0),
            wht_shortfall=data.get("wht_shortfall", 0),
            st_shortfall=data.get("st_shortfall", 0),
            is_concealment=data.get("is_concealment", False),
        )
        return result

    def analyze_risk(self, data: dict) -> dict:
        """Analyze risk factors."""
        factors = self.risk_analyzer.analyze(
            tax_outstanding=data.get("tax_outstanding", 0),
            notices_count=data.get("notices_count", 0),
            itr_filed=data.get("itr_filed", True),
            wht_shortfall=data.get("wht_shortfall", 0),
            st_shortfall=data.get("st_shortfall", 0),
            estimated_income=data.get("estimated_income", 0),
            declared_income=data.get("declared_income", 0),
            # Passed through explicitly: RiskAnalyzer used to default this to
            # 5 years, which made the new-business risk (RISK008) unreachable
            # because no caller ever supplied a real age.
            business_age_years=data.get("business_age_years"),
        )
        overall_level, overall_score = self.risk_analyzer.get_overall_risk(factors)

        return {
            "risk_level": overall_level.value,
            "risk_score": overall_score,
            "factors": [
                {
                    "code": f.code,
                    "description": f.description,
                    "level": f.level.value,
                    "weight": f.weight,
                    "mitigation": f.mitigation,
                }
                for f in factors
            ],
        }


# Singleton
_api: Optional[TaxHealthAPI] = None


def get_tax_health_api() -> TaxHealthAPI:
    """Get singleton tax health API."""
    global _api
    if _api is None:
        _api = TaxHealthAPI()
    return _api
