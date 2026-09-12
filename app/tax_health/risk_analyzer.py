"""
Risk Analyzer - Production-Grade
=================================

Analyzes tax-related risk factors.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskFactor:
    """Single risk factor."""
    code: str
    description: str
    level: RiskLevel
    weight: int  # 1-10
    mitigation: str = ""


class RiskAnalyzer:
    """Analyzes tax-related risk factors."""

    @staticmethod
    def analyze(
        tax_outstanding: float = 0.0,
        notices_count: int = 0,
        itr_filed: bool = True,
        wht_shortfall: float = 0.0,
        st_shortfall: float = 0.0,
        estimated_income: float = 0.0,
        declared_income: float = 0.0,
        business_age_years: int = 5,
    ) -> list[RiskFactor]:
        """Identify risk factors."""
        factors = []

        # Tax outstanding risk
        if tax_outstanding > 1000000:
            factors.append(RiskFactor(
                code="RISK001",
                description=f"High outstanding tax: PKR {tax_outstanding:,.0f}",
                level=RiskLevel.CRITICAL,
                weight=10,
                mitigation="Pay outstanding tax immediately to reduce penalty accrual",
            ))
        elif tax_outstanding > 500000:
            factors.append(RiskFactor(
                code="RISK002",
                description=f"Significant outstanding tax: PKR {tax_outstanding:,.0f}",
                level=RiskLevel.HIGH,
                weight=7,
                mitigation="Set up payment plan or pay full amount",
            ))

        # Outstanding notices
        if notices_count > 0:
            level = RiskLevel.CRITICAL if notices_count >= 3 else RiskLevel.HIGH
            factors.append(RiskFactor(
                code="RISK003",
                description=f"{notices_count} outstanding FBR notice(s)",
                level=level,
                weight=8 if notices_count >= 3 else 5,
                mitigation="Engage tax professional and respond to all notices",
            ))

        # ITR filing
        if not itr_filed:
            factors.append(RiskFactor(
                code="RISK004",
                description="ITR not filed for current year",
                level=RiskLevel.CRITICAL,
                weight=10,
                mitigation="File return immediately with late filing fee",
            ))

        # WHT shortfall
        if wht_shortfall > 100000:
            factors.append(RiskFactor(
                code="RISK005",
                description=f"WHT shortfall: PKR {wht_shortfall:,.0f}",
                level=RiskLevel.HIGH,
                weight=7,
                mitigation="Deposit all collected WHT with explanation",
            ))

        # Sales tax shortfall
        if st_shortfall > 100000:
            factors.append(RiskFactor(
                code="RISK006",
                description=f"Sales tax shortfall: PKR {st_shortfall:,.0f}",
                level=RiskLevel.CRITICAL,
                weight=9,
                mitigation="Deposit immediately - ST shortfall attracts highest penalties",
            ))

        # Income mismatch
        if estimated_income > 0 and declared_income > 0:
            diff_pct = abs(estimated_income - declared_income) / estimated_income
            if diff_pct > 0.30:
                factors.append(RiskFactor(
                    code="RISK007",
                    description=f"Income mismatch: {diff_pct*100:.0f}% difference",
                    level=RiskLevel.HIGH,
                    weight=8,
                    mitigation="Reconcile income sources - may trigger FBR scrutiny",
                ))

        # New business risk (less history)
        if business_age_years < 2:
            factors.append(RiskFactor(
                code="RISK008",
                description="New business - higher scrutiny from FBR",
                level=RiskLevel.MEDIUM,
                weight=4,
                mitigation="Maintain extra-clean records and file all returns on time",
            ))

        return factors

    @staticmethod
    def get_overall_risk(factors: list[RiskFactor]) -> tuple[RiskLevel, int]:
        """Get overall risk level and score."""
        if not factors:
            return RiskLevel.LOW, 0

        total_weight = sum(f.weight for f in factors)

        # Critical if any critical factor exists
        if any(f.level == RiskLevel.CRITICAL for f in factors):
            return RiskLevel.CRITICAL, total_weight
        elif any(f.level == RiskLevel.HIGH for f in factors):
            return RiskLevel.HIGH, total_weight
        elif any(f.level == RiskLevel.MEDIUM for f in factors):
            return RiskLevel.MEDIUM, total_weight
        else:
            return RiskLevel.LOW, total_weight
