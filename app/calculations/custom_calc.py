"""
Custom Calculation Engine - Production-Grade
==============================================

For user-defined tax calculations, advanced scenarios, and
special computations not covered by standard calculators.

Supports:
- Custom percentage calculations (tax on X% of amount)
- Penalty calculations (FBR penalties with daily/monthly accrual)
- Tax credit calculations
- Multi-step calculations
- Conditional logic (if A > threshold, then B, else C)
- Compound calculations
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable


class CustomCalcType(str, Enum):
    PERCENTAGE = "percentage"
    PENALTY = "penalty"
    COMPOUND = "compound"
    CONDITIONAL = "conditional"
    FORMULA = "formula"


@dataclass
class CustomCalcInput:
    """Input for custom calculation."""
    calc_type: CustomCalcType
    base_value: float = 0.0
    rate: float = 0.0  # For percentage
    description: str = ""

    # For penalty
    principal: float = 0.0
    days_late: int = 0
    monthly_rate: float = 0.0  # e.g., 0.10 for 10% per month

    # For compound
    periods: int = 1  # Number of compounding periods

    # For formula
    variables: dict = field(default_factory=dict)  # e.g., {"A": 100, "B": 200}

    # For custom callback
    custom_func: Optional[Callable] = None


@dataclass
class CustomCalcResult:
    """Result of custom calculation."""
    calc_type: str
    result: float
    intermediate_steps: list[dict] = field(default_factory=list)
    formula_text: str = ""
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class CustomCalculator:
    """Production-grade custom calculation engine."""

    @staticmethod
    def validate_input(inp: CustomCalcInput) -> tuple[bool, str]:
        if inp.calc_type not in CustomCalcType:
            return False, f"Unknown calculation type: {inp.calc_type}"
        if inp.base_value < 0:
            return False, "Base value cannot be negative."
        return True, ""

    @staticmethod
    def calculate(inp: CustomCalcInput) -> CustomCalcResult:
        valid, error = CustomCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = ["Custom calculation performed"]
        sources = ["User-defined calculation"]
        steps = []

        if inp.calc_type == CustomCalcType.PERCENTAGE:
            result = inp.base_value * inp.rate
            steps.append({
                "step": "Calculate",
                "operation": f"{inp.base_value} × {inp.rate}",
                "result": result,
            })
            notes.append(f"Result: {inp.base_value} × {inp.rate} = {result}")

        elif inp.calc_type == CustomCalcType.PENALTY:
            # FBR penalty: principal × monthly_rate × (days/30)
            months = inp.days_late / 30
            result = inp.principal * inp.monthly_rate * months
            steps.append({
                "step": 1,
                "operation": f"Months late = {inp.days_late} / 30 = {months:.2f}",
                "result": months,
            })
            steps.append({
                "step": 2,
                "operation": f"Penalty = {inp.principal} × {inp.monthly_rate} × {months:.2f}",
                "result": result,
            })
            notes.append(f"Penalty: PKR {inp.principal:,.2f} × {inp.monthly_rate * 100:.0f}% × {months:.2f} months")

        elif inp.calc_type == CustomCalcType.COMPOUND:
            # Compound: P × (1 + r)^n
            result = inp.base_value * ((1 + inp.rate) ** inp.periods)
            steps.append({
                "step": "Compound",
                "operation": f"{inp.base_value} × (1 + {inp.rate})^{inp.periods}",
                "result": result,
            })
            notes.append(f"Compound result: {result}")

        elif inp.calc_type == CustomCalcType.CONDITIONAL:
            # Simple conditional: if base > threshold, apply rate, else no penalty
            threshold = inp.variables.get("threshold", 0)
            if inp.base_value > threshold:
                result = inp.base_value * inp.rate
                notes.append(f"Condition met: {inp.base_value} > {threshold}")
                notes.append(f"Applied: {inp.base_value} × {inp.rate} = {result}")
            else:
                result = 0
                notes.append(f"Condition not met: {inp.base_value} <= {threshold}")
                notes.append(f"Result: 0")
            steps.append({"step": "Conditional", "result": result})

        elif inp.calc_type == CustomCalcType.FORMULA:
            if inp.custom_func:
                result = inp.custom_func(inp.variables)
                steps.append({"step": "Custom", "result": result})
                notes.append(f"Custom function result: {result}")
            else:
                result = inp.base_value
                notes.append("No custom function provided, returning base value")

        return CustomCalcResult(
            calc_type=inp.calc_type.value,
            result=round(result, 2),
            intermediate_steps=steps,
            formula_text=inp.description,
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: CustomCalcResult, currency: str = "PKR") -> str:
        lines = [
            f"=== Custom Calculation ===",
            f"Type: {result.calc_type}",
            f"",
            f"Result: {currency} {result.result:>15,.2f}",
            f"",
            f"--- Steps ---",
        ]
        for step in result.intermediate_steps:
            lines.append(f"  Step {step.get('step', '')}: {step.get('operation', step.get('result'))}")
        lines.append(f"")
        lines.append(f"--- Notes ---")
        for note in result.notes:
            lines.append(f"  • {note}")
        return "\n".join(lines)
