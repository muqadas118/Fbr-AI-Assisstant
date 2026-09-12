"""
Tax Health Check - Production-Grade
=================================

Comprehensive health analysis of taxpayer's tax profile:
- Filing compliance (ITR filed on time?)
- Tax deposit compliance (WHT deposited?)
- Invoice reconciliation (sales = declared?)
- Credit utilization (ITC claimed correctly?)
- Risk indicators (red flags)
- Penalty exposure calculator
- Estimated tax liability
- Recommendations for compliance
- Compliance score (0-100)
- Grade (A+ to F)
"""

from app.tax_health.health_engine import (
    TaxHealthEngine, TaxHealthProfile,
    HealthIssue, IssueSeverity,
    HealthRecommendation,
)
from app.tax_health.risk_analyzer import (
    RiskAnalyzer, RiskFactor, RiskLevel,
)
from app.tax_health.penalty_calculator import (
    PenaltyCalculator, PenaltyBreakdown, PenaltyType,
)
from app.tax_health.api import TaxHealthAPI, get_tax_health_api

__all__ = [
    "TaxHealthEngine",
    "TaxHealthProfile",
    "HealthIssue",
    "IssueSeverity",
    "HealthRecommendation",
    "RiskAnalyzer",
    "RiskFactor",
    "RiskLevel",
    "PenaltyCalculator",
    "PenaltyBreakdown",
    "PenaltyType",
    "TaxHealthAPI",
    "get_tax_health_api",
]
