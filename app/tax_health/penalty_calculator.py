"""
Penalty Calculator - Production-Grade
====================================

Calculates estimated penalties for non-compliance.
"""

from dataclasses import dataclass, field
from enum import Enum


class PenaltyType(str, Enum):
    """Type of penalty."""
    LATE_FILING = "late_filing"
    LATE_PAYMENT = "late_payment"
    DEFAULT_SURCHARGE = "default_surcharge"
    WHT_PENALTY = "wht_penalty"
    SALES_TAX_PENALTY = "sales_tax_penalty"
    CONCEALMENT = "concealment"
    FRAUD = "fraud"


@dataclass
class PenaltyBreakdown:
    """Penalty calculation breakdown."""
    penalty_type: PenaltyType
    description: str
    base_amount: float  # PKR
    penalty_rate: float  # Percentage
    penalty_amount: float  # PKR
    notes: str = ""


class PenaltyCalculator:
    """Calculate estimated penalties for tax non-compliance."""

    # Standard rates (as per Finance Act)
    RATES = {
        PenaltyType.LATE_FILING: {
            "base_fee": 5000,
            "min_penalty": 1000,
            "max_penalty": 50000,
            "per_day_fee": 500,
            "max_days": 100,
        },
        PenaltyType.LATE_PAYMENT: {
            "surcharge_rate": 0.15,  # 15% per annum (roughly 1.25%/month)
        },
        PenaltyType.DEFAULT_SURCHARGE: {
            "rate": 0.50,  # 50% of unpaid tax
        },
        PenaltyType.WHT_PENALTY: {
            "rate": 0.10,  # 10% of shortfall
        },
        PenaltyType.SALES_TAX_PENALTY: {
            "rate": 0.25,  # 25% of shortfall
        },
        PenaltyType.CONCEALMENT: {
            "rate": 0.100,  # 10% of concealed income
        },
    }

    @staticmethod
    def calculate_itr_penalty(
        tax_assessed: float,
        days_late: int,
        is_concealment: bool = False,
    ) -> list[PenaltyBreakdown]:
        """Calculate ITR late filing/payment penalties."""
        penalties = []
        rates = PenaltyCalculator.RATES[PenaltyType.LATE_FILING]

        # Base fee
        base = min(rates["base_fee"] + (days_late * rates["per_day_fee"]), rates["max_penalty"])
        base = max(base, rates["min_penalty"])
        penalties.append(PenaltyBreakdown(
            penalty_type=PenaltyType.LATE_FILING,
            description=f"Late filing penalty ({days_late} days @ PKR 500/day)",
            base_amount=tax_assessed,
            penalty_rate=0,
            penalty_amount=base,
            notes="Flat fee under Section 114(4)",
        ))

        # Default surcharge if tax unpaid
        if tax_assessed > 0:
            rates_ds = PenaltyCalculator.RATES[PenaltyType.DEFAULT_SURCHARGE]
            surcharge = tax_assessed * rates_ds["rate"]
            penalties.append(PenaltyBreakdown(
                penalty_type=PenaltyType.DEFAULT_SURCHARGE,
                description="Default surcharge (50% of unpaid tax)",
                base_amount=tax_assessed,
                penalty_rate=rates_ds["rate"] * 100,
                penalty_amount=surcharge,
                notes="Section 205, ITO 2001",
            ))

        # Concealment penalty
        if is_concealment:
            concealment = tax_assessed * PenaltyCalculator.RATES[PenaltyType.CONCEALMENT]["rate"]
            penalties.append(PenaltyBreakdown(
                penalty_type=PenaltyType.CONCEALMENT,
                description="Penalty for concealment of income",
                base_amount=tax_assessed,
                penalty_rate=PenaltyCalculator.RATES[PenaltyType.CONCEALMENT]["rate"] * 100,
                penalty_amount=concealment,
                notes="Section 111, ITO 2001",
            ))

        return penalties

    @staticmethod
    def calculate_wht_penalty(shortfall: float, days_late: int = 0) -> list[PenaltyBreakdown]:
        """Calculate WHT penalty."""
        rates = PenaltyCalculator.RATES[PenaltyType.WHT_PENALTY]
        penalty = shortfall * rates["rate"]
        return [
            PenaltyBreakdown(
                penalty_type=PenaltyType.WHT_PENALTY,
                description="WHT penalty (10% of shortfall)",
                base_amount=shortfall,
                penalty_rate=rates["rate"] * 100,
                penalty_amount=penalty,
                notes="Section 161/162, ITO 2001",
            )
        ]

    @staticmethod
    def calculate_sales_tax_penalty(
        shortfall: float,
        days_late: int = 0,
    ) -> list[PenaltyBreakdown]:
        """Calculate sales tax penalty."""
        penalties = []
        rates = PenaltyCalculator.RATES[PenaltyType.SALES_TAX_PENALTY]

        penalty = shortfall * rates["rate"]
        penalties.append(PenaltyBreakdown(
            penalty_type=PenaltyType.SALES_TAX_PENALTY,
            description="Sales tax penalty (25% of shortfall)",
            base_amount=shortfall,
            penalty_rate=rates["rate"] * 100,
            penalty_amount=penalty,
            notes="Sales Tax Act 1990",
        ))

        # Daily late fee
        if days_late > 0:
            daily_fee = min(days_late * 500, 50000)
            penalties.append(PenaltyBreakdown(
                penalty_type=PenaltyType.LATE_FILING,
                description=f"Daily late fee ({days_late} days @ PKR 500/day)",
                base_amount=shortfall,
                penalty_rate=0,
                penalty_amount=daily_fee,
                notes="Section 26, Sales Tax Act",
            ))

        return penalties

    @staticmethod
    def estimate_total_penalties(
        tax_assessed: float = 0,
        tax_paid: float = 0,
        days_late_itr: int = 0,
        days_late_payment: int = 0,
        wht_shortfall: float = 0,
        st_shortfall: float = 0,
        is_concealment: bool = False,
    ) -> dict:
        """Estimate all penalties at once."""
        breakdown = []

        # ITR penalties
        if days_late_itr > 0 or tax_assessed > 0:
            itr_penalties = PenaltyCalculator.calculate_itr_penalty(
                tax_assessed=max(tax_assessed - tax_paid, 0),
                days_late=days_late_itr,
                is_concealment=is_concealment,
            )
            breakdown.extend(itr_penalties)

        # WHT penalties
        if wht_shortfall > 0:
            breakdown.extend(
                PenaltyCalculator.calculate_wht_penalty(wht_shortfall)
            )

        # Sales tax penalties
        if st_shortfall > 0:
            breakdown.extend(
                PenaltyCalculator.calculate_sales_tax_penalty(st_shortfall)
            )

        total = sum(p.penalty_amount for p in breakdown)

        return {
            "breakdown": [
                {
                    "type": p.penalty_type.value,
                    "description": p.description,
                    "amount": p.penalty_amount,
                }
                for p in breakdown
            ],
            "total_penalty_estimate": round(total, 2),
            "total_tax_shortfall": max(tax_assessed - tax_paid, 0) + wht_shortfall + st_shortfall,
            "total_liability": max(tax_assessed - tax_paid, 0) + wht_shortfall + st_shortfall + total,
        }
