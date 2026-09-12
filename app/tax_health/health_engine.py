"""
Tax Health Engine - Production-Grade
=====================================

Core engine that evaluates taxpayer's tax health.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class IssueSeverity(str, Enum):
    """Severity of a health issue."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class HealthIssue:
    """Single health issue found."""
    code: str
    title: str
    description: str
    severity: IssueSeverity
    section: str  # ITR, WHT, ST, Audit, etc.
    tax_impact: float = 0.0  # PKR
    penalty_estimate: float = 0.0  # PKR
    recommendation: str = ""


@dataclass
class HealthRecommendation:
    """Actionable recommendation."""
    priority: int  # 1 = highest
    action: str
    reason: str
    deadline: Optional[str] = None
    penalty_if_ignored: str = ""
    estimated_cost: str = ""


@dataclass
class TaxHealthProfile:
    """Complete tax health profile."""
    ntn: str
    tax_year: int
    assessment_year: int

    # Overall score
    health_score: float = 0.0  # 0-100
    health_grade: str = "F"  # A+, A, B, C, D, F

    # Filing status
    itr_filed: bool = False
    itr_filing_date: Optional[str] = None
    itr_due_date: str = ""

    # Tax position
    declared_income: float = 0.0
    estimated_income: float = 0.0
    tax_assessed: float = 0.0
    tax_paid: float = 0.0
    tax_outstanding: float = 0.0

    # WHT compliance
    wht_deposited: float = 0.0
    wht_collected: float = 0.0
    wht_shortfall: float = 0.0

    # Sales Tax compliance
    sales_tax_collected: float = 0.0
    sales_tax_deposited: float = 0.0
    st_shortfall: float = 0.0

    # Risk profile
    risk_level: str = "unknown"  # low, medium, high, critical
    risk_factors: list[str] = field(default_factory=list)
    notices_outstanding: int = 0

    # Issues found
    issues: list[HealthIssue] = field(default_factory=list)

    # Recommendations
    recommendations: list[HealthRecommendation] = field(default_factory=list)

    # Breakdown scores
    filing_score: float = 0.0
    deposit_score: float = 0.0
    compliance_score: float = 0.0
    reconciliation_score: float = 0.0

    # Timestamps
    generated_at: str = ""
    period_from: Optional[str] = None
    period_to: Optional[str] = None

    @property
    def critical_issues_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def total_penalty_exposure(self) -> float:
        return sum(i.penalty_estimate for i in self.issues)


class TaxHealthEngine:
    """
    Evaluates tax health based on available data.

    Uses signals from:
    - Filing history
    - Payment history
    - WHT statements
    - Sales tax returns
    - Bank statement analysis
    - Notice history
    """

    # Thresholds for scoring
    FILING_DAYS_LATE_THRESHOLD = 30
    TAX_PAYMENT_THRESHOLD = 0.90  # 90% of assessed tax
    WHT_DEPOSIT_THRESHOLD = 0.95  # 95% of collected
    RECONCILIATION_THRESHOLD = 0.85

    def analyze(
        self,
        ntn: str,
        tax_year: int,
        # Filing data
        itr_filed: bool = False,
        itr_filing_date: Optional[str] = None,
        itr_due_date: Optional[str] = None,
        # Income data
        declared_income: float = 0.0,
        estimated_income: float = 0.0,
        # Tax payment data
        tax_assessed: float = 0.0,
        tax_paid: float = 0.0,
        # WHT data
        wht_collected: float = 0.0,
        wht_deposited: float = 0.0,
        # Sales Tax data
        st_collected: float = 0.0,
        st_deposited: float = 0.0,
        # Notices
        notices_outstanding: int = 0,
        # Period
        period_from: Optional[str] = None,
        period_to: Optional[str] = None,
    ) -> TaxHealthProfile:
        """Analyze tax health for a taxpayer."""

        profile = TaxHealthProfile(
            ntn=ntn,
            tax_year=tax_year,
            assessment_year=tax_year + 1,
            itr_filed=itr_filed,
            itr_filing_date=itr_filing_date,
            itr_due_date=itr_due_date or f"{tax_year + 1}-09-30",
            declared_income=declared_income,
            estimated_income=estimated_income,
            tax_assessed=tax_assessed,
            tax_paid=tax_paid,
            wht_collected=wht_collected,
            wht_deposited=wht_deposited,
            sales_tax_collected=st_collected,
            sales_tax_deposited=st_deposited,
            period_from=period_from,
            period_to=period_to,
            generated_at=datetime.utcnow().isoformat(),
            notices_outstanding=notices_outstanding,
        )

        issues: list[HealthIssue] = []
        recommendations: list[HealthRecommendation] = []

        # ===================================================================
        # CHECK 1: ITR Filing Status
        # ===================================================================
        if not profile.itr_filed:
            issues.append(HealthIssue(
                code="ITR001",
                title="Income Tax Return Not Filed",
                description=(
                    f"ITR for Tax Year {tax_year} has not been filed. "
                    f"Due date was {profile.itr_due_date}."
                ),
                severity=IssueSeverity.CRITICAL,
                section="ITR",
                tax_impact=0,
                penalty_estimate=self._estimate_itr_penalty(tax_assessed),
                recommendation="File ITR immediately with late filing fee",
            ))
        else:
            # Check if filed late
            if itr_filing_date and itr_due_date:
                try:
                    filed = datetime.strptime(itr_filing_date, "%Y-%m-%d")
                    due = datetime.strptime(itr_due_date, "%Y-%m-%d")
                    days_late = (filed - due).days
                    if days_late > self.FILING_DAYS_LATE_THRESHOLD:
                        issues.append(HealthIssue(
                            code="ITR002",
                            title=f"ITR Filed Late by {days_late} Days",
                            description="Return was filed after the due date",
                            severity=IssueSeverity.HIGH,
                            section="ITR",
                            penalty_estimate=self._estimate_itr_penalty(tax_assessed) * 0.5,
                            recommendation="Ensure timely filing in future",
                        ))
                except ValueError:
                    pass

        # ===================================================================
        # CHECK 2: Tax Payment Status
        # ===================================================================
        if profile.tax_assessed > 0:
            payment_ratio = profile.tax_paid / profile.tax_assessed
            if payment_ratio < 1.0:
                shortfall = profile.tax_assessed - profile.tax_paid
                profile.tax_outstanding = shortfall
                issues.append(HealthIssue(
                    code="TAX001",
                    title="Outstanding Tax Liability",
                    description=(
                        f"Tax assessed: PKR {tax_assessed:,.0f}, "
                        f"Tax paid: PKR {tax_paid:,.0f}, "
                        f"Shortfall: PKR {shortfall:,.0f}"
                    ),
                    severity=IssueSeverity.CRITICAL if shortfall > 100000 else IssueSeverity.HIGH,
                    section="ITR",
                    tax_impact=shortfall,
                    penalty_estimate=shortfall * 0.15,  # 15% default surcharge
                    recommendation="Pay outstanding tax immediately",
                ))
            elif payment_ratio < self.TAX_PAYMENT_THRESHOLD:
                issues.append(HealthIssue(
                    code="TAX002",
                    title="Partial Tax Payment",
                    description="Less than 90% of assessed tax was paid",
                    severity=IssueSeverity.MEDIUM,
                    section="ITR",
                    recommendation="Pay remaining tax before penalty accrues",
                ))

        # ===================================================================
        # CHECK 3: Income Declaration vs Estimate
        # ===================================================================
        if profile.estimated_income > 0 and profile.declared_income > 0:
            income_diff = abs(profile.estimated_income - profile.declared_income)
            income_diff_pct = income_diff / profile.estimated_income

            if income_diff_pct > 0.30:  # >30% difference
                issues.append(HealthIssue(
                    code="INC001",
                    title="Income Discrepancy",
                    description=(
                        f"Declared income (PKR {declared_income:,.0f}) differs by "
                        f"{income_diff_pct*100:.0f}% from estimated (PKR {estimated_income:,.0f})"
                    ),
                    severity=IssueSeverity.HIGH,
                    section="ITR",
                    recommendation="Review income sources and ensure all declared",
                ))

        # ===================================================================
        # CHECK 4: WHT Compliance
        # ===================================================================
        if profile.wht_collected > 0:
            wht_ratio = profile.wht_deposited / profile.wht_collected
            if wht_ratio < 1.0:
                shortfall = profile.wht_collected - profile.wht_deposited
                profile.wht_shortfall = shortfall
                issues.append(HealthIssue(
                    code="WHT001",
                    title="WHT Shortfall",
                    description=(
                        f"WHT collected: PKR {wht_collected:,.0f}, "
                        f"WHT deposited: PKR {wht_deposited:,.0f}, "
                        f"Shortfall: PKR {shortfall:,.0f}"
                    ),
                    severity=IssueSeverity.HIGH,
                    section="WHT",
                    tax_impact=shortfall,
                    penalty_estimate=shortfall * 0.10,  # 10% penalty
                    recommendation="Deposit all WHT immediately",
                ))

        # ===================================================================
        # CHECK 5: Sales Tax Compliance
        # ===================================================================
        if profile.sales_tax_collected > 0:
            st_ratio = profile.sales_tax_deposited / profile.sales_tax_collected
            if st_ratio < 1.0:
                shortfall = profile.sales_tax_collected - profile.sales_tax_deposited
                profile.st_shortfall = shortfall
                issues.append(HealthIssue(
                    code="ST001",
                    title="Sales Tax Shortfall",
                    description=(
                        f"Sales tax collected: PKR {st_collected:,.0f}, "
                        f"Sales tax deposited: PKR {st_deposited:,.0f}, "
                        f"Shortfall: PKR {shortfall:,.0f}"
                    ),
                    severity=IssueSeverity.CRITICAL,
                    section="ST",
                    tax_impact=shortfall,
                    penalty_estimate=shortfall * 0.25,  # 25% penalty
                    recommendation="Deposit all collected sales tax",
                ))

        # ===================================================================
        # CHECK 6: Outstanding Notices
        # ===================================================================
        if notices_outstanding > 0:
            issues.append(HealthIssue(
                code="NOT001",
                title=f"{notices_outstanding} FBR Notice(s) Outstanding",
                description="You have unanswered FBR notices",
                severity=IssueSeverity.CRITICAL,
                section="Audit",
                penalty_estimate=notices_outstanding * 50000,
                recommendation="Respond to all notices immediately",
            ))

        # ===================================================================
        # Calculate Scores
        # ===================================================================
        profile.issues = issues
        profile.filing_score = self._calculate_filing_score(profile)
        profile.deposit_score = self._calculate_deposit_score(profile)
        profile.compliance_score = self._calculate_compliance_score(profile)
        profile.reconciliation_score = self._calculate_reconciliation_score(profile)
        profile.health_score = (
            profile.filing_score * 0.3
            + profile.deposit_score * 0.3
            + profile.compliance_score * 0.2
            + profile.reconciliation_score * 0.2
        )
        profile.health_grade = self._get_grade(profile.health_score)

        # Risk factors
        profile.risk_factors = [i.code for i in issues]
        profile.risk_level = self._get_risk_level(profile)

        # Recommendations
        profile.recommendations = self._generate_recommendations(issues)

        return profile

    def _estimate_itr_penalty(self, tax_assessed: float) -> float:
        """Estimate ITR late filing penalty."""
        base_penalty = 5000
        pct_penalty = tax_assessed * 0.05 if tax_assessed > 0 else 0
        return base_penalty + pct_penalty

    def _calculate_filing_score(self, p: TaxHealthProfile) -> float:
        """Score 0-100 for filing compliance."""
        if p.itr_filed:
            return 100.0
        return 0.0

    def _calculate_deposit_score(self, p: TaxHealthProfile) -> float:
        """Score 0-100 for tax deposit compliance."""
        scores = []

        # Tax deposit
        if p.tax_assessed > 0:
            ratio = min(p.tax_paid / p.tax_assessed, 1.0)
            scores.append(ratio * 40)

        # WHT deposit
        if p.wht_collected > 0:
            ratio = min(p.wht_deposited / p.wht_collected, 1.0)
            scores.append(ratio * 30)

        # Sales tax deposit
        if p.sales_tax_collected > 0:
            ratio = min(p.sales_tax_deposited / p.sales_tax_collected, 1.0)
            scores.append(ratio * 30)

        if not scores:
            return 100.0  # No obligations
        return sum(scores)

    def _calculate_compliance_score(self, p: TaxHealthProfile) -> float:
        """Score 0-100 for general compliance."""
        if p.critical_issues_count == 0 and p.notices_outstanding == 0:
            return 100.0
        return max(0, 100 - p.critical_issues_count * 20)

    def _calculate_reconciliation_score(self, p: TaxHealthProfile) -> float:
        """Score 0-100 for reconciliation."""
        if p.estimated_income == 0 or p.declared_income == 0:
            return 100.0
        diff = abs(p.estimated_income - p.declared_income) / p.estimated_income
        return max(0, (1 - diff) * 100)

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _get_risk_level(self, p: TaxHealthProfile) -> str:
        """Determine overall risk level."""
        if p.critical_issues_count >= 3 or p.tax_outstanding > 1000000:
            return "critical"
        elif p.critical_issues_count >= 1 or p.tax_outstanding > 500000:
            return "high"
        elif p.critical_issues_count > 0 or p.tax_outstanding > 100000:
            return "medium"
        else:
            return "low"

    def _generate_recommendations(self, issues: list[HealthIssue]) -> list[HealthRecommendation]:
        """Generate actionable recommendations from issues."""
        recommendations = []
        priority = 1

        for issue in issues:
            rec = HealthRecommendation(
                priority=priority,
                action=issue.recommendation,
                reason=issue.description,
                penalty_if_ignored=f"PKR {issue.penalty_estimate:,.0f} potential penalty",
            )
            recommendations.append(rec)
            priority += 1

        # Always add a general recommendation
        recommendations.append(HealthRecommendation(
            priority=99,
            action="Schedule quarterly tax review",
            reason="Regular review helps catch issues early",
        ))

        return recommendations
