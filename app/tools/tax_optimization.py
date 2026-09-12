"""
Tax Optimization Tool (Tax Reducer backend).

A reusable, validated tool that analyses a taxpayer's financial
profile and identifies LAWFUL tax optimization opportunities
under FBR legislation.

Design rules (project contracts):

- BaseTool contract: validate_input -> execute -> run; run()
  NEVER raises; every failure is a ToolResult(ok=False).
- All invalid input raises ToolError so the refusal message is
  preserved by BaseTool.run().
- Unlawful intent (tax evasion) is refused deterministically via
  a 12-pattern evasion guard. The guard is NEGATION-AWARE: the
  canonical Tax Reducer frontend query embeds a disclaimer of
  the form "never suggest concealing income, fabricating
  expenses, ..." — those phrases appear in a DISAVOWAL context
  and must NOT trigger the refusal. Each pattern match is
  evaluated against the sentence it appears in; a sentence that
  contains an explicit disavowal cue ("never", "do not",
  "only lawful", ...) does not count as an evasion request.
- The tool performs NO retrieval and calls NO LLM: baseline and
  optimized scenarios are computed from a documented slab table
  (an approximation of the Income Tax Ordinance 2001 individual
  slabs and the 29% corporate rate), and every opportunity
  cites its legislative basis with corpus provenance. Estimated
  figures are clearly labelled as estimates; final liability
  always requires FBR verification.
- Output is additive structured data for the agent layer:
  opportunities[], baseline{}, optimized{}, savings, sources[],
  verification{} — the canonical RAG response fields are never
  replaced.
"""

from __future__ import annotations

import re
from typing import Any

from .base import BaseTool, ToolError, ToolResult


# ============================================================
# LAWFUL-ONLY GUARD (mirrors the frontend EVASION_PATTERNS)
# ============================================================

_EVASION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:hide|hiding|hidden)\s+(?:my\s+|the\s+|this\s+|some\s+|any\s+)?"
        r"(?:income|revenue|sales|money|profits?|transactions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:undeclared|unreported|undisclosed|unrecorded)\s+"
        r"(?:income|revenue|sales|money|profits?|transactions?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bconceal(?:s|ed|ing)?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:fake|false|fabricated?|forged?|bogus|fictitious)\s+"
        r"(?:expenses?|invoices?|receipts?|bills?|records?|documents?|"
        r"deductions?|books?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfalsif(?:y|ies|ied|ying)\b", re.IGNORECASE),
    re.compile(r"\bunder-?report(?:ing|ed|s)?\b", re.IGNORECASE),
    re.compile(r"\b(?:tax\s+)?(?:evade|evading|evasion)\b", re.IGNORECASE),
    re.compile(r"\boff[-\s]?the[-\s]?books?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:without|not)\s+(?:declaring|reporting|disclosing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bavoid\s+(?:declaring|reporting|filing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:two|dual|double)\s+(?:sets?\s+of|set\s+of)\s+"
        r"(?:books?|records?|accounts?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bshow\s+(?:less|lower|reduced)\s+(?:income|revenue|sales|profit)",
        re.IGNORECASE,
    ),
)

# Disavowal cues: when one of these appears in the SAME sentence
# as an evasion-pattern match, the sentence is refusing or
# disclaiming the unlawful act, not requesting it (e.g. the
# Tax Reducer disclaimer "never suggest concealing income").
# Note: "without"/"not" alone are NOT cues because they are
# themselves part of evasion phrases ("income without
# declaring").
_DISAVOWAL_CUES: tuple[str, ...] = (
    "never",
    "do not",
    "don't",
    "dont",
    "does not",
    "cannot",
    "can't",
    "cant",
    "will not",
    "won't",
    "wont",
    "must not",
    "shall not",
    "refuse",
    "not suggest",
    "only lawful",
    "no intention",
)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")

_UNLAWFUL_RESPONSE = (
    "This tool only supports lawful tax planning. It cannot help "
    "conceal income, fabricate expenses, falsify records, or "
    "evade taxes. Request refused."
)


def _sentence_of(text: str, position: int) -> str:
    """Return the sentence containing `position` (lowercased)."""

    start = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        if m.start() >= position:
            return text[start : m.start()].lower()
        start = m.end()
    return text[start:].lower()


def detect_unlawful_intent(text: str) -> bool:
    """
    Deterministic evasion-intent detection, negation-aware.

    Returns True only when at least one evasion pattern matches
    in a sentence that does NOT contain a disavowal cue.
    """

    if not text:
        return False
    for pattern in _EVASION_PATTERNS:
        for m in pattern.finditer(text):
            sentence = _sentence_of(text, m.start())
            if not any(cue in sentence for cue in _DISAVOWAL_CUES):
                return True
    return False


# ============================================================
# DOCUMENTED SLAB TABLE (estimate, tax year 2025)
# ============================================================

# Individual (non-business) slabs, Income Tax Ordinance 2001,
# Division I of Part I of the First Schedule as amended by the
# Finance Act 2024 (tax year 2025). Used for ESTIMATES only;
# final liability requires FBR verification.
_INDIVIDUAL_SLABS: tuple[tuple[float, float], ...] = (
    (600_000.0, 0.00),
    (1_200_000.0, 0.05),
    (1_800_000.0, 0.10),
    (2_500_000.0, 0.15),
    (3_500_000.0, 0.20),
    (5_000_000.0, 0.25),
    (7_000_000.0, 0.30),
    (float("inf"), 0.35),
)

# Corporate rate (most companies), Income Tax Ordinance 2001
# section 56 as amended (29% for tax year 2025 onward).
_COMPANY_RATE = 0.29

_ITO_2001_SHA256 = (
    "3eb83defefad0930b5d35dbbf6f3961f967a9330114f70058dac2f096a0b6812"
)


# ============================================================
# LAWFUL OPPORTUNITY CATALOGUE
# ============================================================

# (matcher, opportunity_id, title, description, legal_basis)
_OPPORTUNITY_CATALOGUE: tuple[tuple[re.Pattern[str], str, str, str, str], ...] = (
    (
        re.compile(r"(pension|provident\s+fund|retirement\s+(fund|scheme))", re.I),
        "pension_contribution",
        "Approved Pension / Provident Fund Contribution",
        "Contributions to an approved pension fund or provident "
        "fund reduce taxable income within statutory caps.",
        "Section 62, Income Tax Ordinance 2001 (investment in "
        "approved pension funds; deductible subject to statutory "
        "limits).",
    ),
    (
        re.compile(r"(life\s+insurance|takaful|insurance\s+premium)", re.I),
        "life_insurance_premium",
        "Life Insurance / Takaful Premium Deduction",
        "Premiums paid on a life insurance policy or takaful "
        "certificates qualify for a deduction within statutory "
        "caps.",
        "Section 62, Income Tax Ordinance 2001 (life insurance "
        "premiums; deductible subject to statutory limits).",
    ),
    (
        re.compile(r"(house\s+rent|rent\s+allowance|\bhra\b)", re.I),
        "house_rent_allowance",
        "House Rent Allowance Exemption",
        "House rent allowance received from an employer is exempt "
        "from salary income to the extent of the prescribed "
        "statutory formula.",
        "Clause (6) of Part I of the Second Schedule, Income Tax "
        "Ordinance 2001 (exemption for house rent allowance "
        "subject to prescribed limits).",
    ),
    (
        re.compile(r"(charit|donat|zakat|sadaqat|sadaqah)", re.I),
        "charitable_donations",
        "Approved Charitable Donation / Zakat Deduction",
        "Donations to approved non-profit organizations and Zakat "
        "paid under the Zakat and Ushr Ordinance 1980 are allowed "
        "as deductions subject to statutory limits.",
        "Section 61, Income Tax Ordinance 2001 (donations to "
        "approved non-profit organizations).",
    ),
    (
        re.compile(r"(depreciat|capital\s+allowance|wear\s+and\s+tear)", re.I),
        "capital_allowance",
        "Depreciation / Initial Allowance on Business Assets",
        "Depreciation and initial allowances on qualifying "
        "business assets reduce business income.",
        "Section 22 and Part II of the Third Schedule, Income Tax "
        "Ordinance 2001 (depreciation and initial allowance).",
    ),
    (
        re.compile(r"(medical\s+(expenditure|expense|insurance)|health\s+insurance)", re.I),
        "medical_expenditure",
        "Medical Expenditure / Health Insurance Credit",
        "Medical expenditure on self and dependants, and health "
        "insurance premiums, qualify for tax credits within "
        "statutory limits.",
        "Section 60A, Income Tax Ordinance 2001 (tax credit for "
        "medical expenditure and health insurance).",
    ),
    (
        re.compile(r"(education|tuition|fee|school|university)", re.I),
        "education_expense",
        "Education Fee / Expenses Allowance",
        "Paid education fees for self, spouse, or children are "
        "allowed as an allowance against salary income within "
        "statutory caps.",
        "Section 60D, Income Tax Ordinance 2001 (allowance for "
        "education expenses).",
    ),
    (
        re.compile(r"(withhold|wht|salary\s+tax|advance\s+tax|challan)", re.I),
        "withholding_credit",
        "Withholding / Advance Tax Credit Adjustment",
        "Tax already deducted at source or paid as advance tax is "
        "adjustable against the final assessed liability; "
        "collect all withholding certificates.",
        "Section 147 and Chapter VII (Sections 168-170), Income "
        "Tax Ordinance 2001 (adjustable tax collected or "
        "deducted at source).",
    ),
    (
        re.compile(r"(profit\s+on\s+debt|interest\s+expense|leverag)", re.I),
        "profit_on_debt",
        "Profit on Debt for Leveraged Business Investment",
        "For a leveraged business, profit on debt paid on loans "
        "used for the business is deductible within statutory "
        "caps.",
        "Section 72, Income Tax Ordinance 2001 (deduction for "
        "profit on debt used for business).",
    ),
    (
        re.compile(r"(teacher|researcher|professor)", re.I),
        "teacher_researcher_credit",
        "Teacher / Researcher Tax Credit",
        "Full-time teachers and researchers receive a 25% tax "
        "credit on taxable income from that employment.",
        "Clause (2) of Part III of the Second Schedule read with "
        "Section 60, Income Tax Ordinance 2001 (25% credit for "
        "full-time teachers and researchers).",
    ),
    (
        re.compile(r"(export|exporter)", re.I),
        "export_income",
        "Export Income Final / Reduced Tax Regime",
        "Export proceeds may be taxed under a final or reduced "
        "regime where prescribed conditions are met.",
        "Section 154 (final tax on exports) and applicable SROs, "
        "Income Tax Ordinance 2001.",
    ),
    (
        re.compile(r"(it\s+sector|information\s+technology|software|pseb)", re.I),
        "it_sector_credit",
        "IT / IT-Enabled Services Export Concession",
        "Exporters of IT and IT-enabled services may elect a "
        "concessional final tax regime on export proceeds.",
        "Section 154A, Income Tax Ordinance 2001 (final tax "
        "regime for IT and ITeS exporters).",
    ),
)

# Optional keyword context contributed by structured numeric
# fields (non-zero values imply the corresponding opportunity
# family even when the question text does not mention it).
_NUMERIC_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "investments": ("pension fund contribution life insurance investment",),
    "donations": ("charitable donations zakat",),
}


def _calculate_tax(
    taxable_income: float, entity_type: str
) -> float:
    """Deterministic slab/corporate estimate (never negative)."""

    if taxable_income <= 0:
        return 0.0
    if entity_type != "individual":
        return round(taxable_income * _COMPANY_RATE, 2)

    tax = 0.0
    lower = 0.0
    for upper, rate in _INDIVIDUAL_SLABS:
        if taxable_income <= lower:
            break
        tax += (min(taxable_income, upper) - lower) * rate
        lower = upper
    return round(tax, 2)


# ============================================================
# QUERY -> PAYLOAD EXTRACTION (agent integration helper)
# ============================================================

_TAX_YEAR_QR = re.compile(r"\btax\s+year\s+(\d{4})\b", re.IGNORECASE)

_LABELLED_AMOUNTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("annual_income", re.compile(r"annual\s+income[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
    ("tax_already_paid", re.compile(r"tax\s+already\s+paid[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
    ("allowable_expenses", re.compile(r"allowable\s+expenses[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
    ("investments", re.compile(r"\binvestments?[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
    ("donations", re.compile(r"\bdonations?[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
    ("business_expenses", re.compile(r"business\s+expenses[^\d\n]{0,24}([\d,]+(?:\.\d+)?)", re.I)),
)


def _parse_amount(token: str) -> float | None:
    cleaned = token.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_tax_reducer_payload(question: object) -> dict[str, Any] | None:
    """
    Extract a TaxOptimizationTool payload from a free-form Tax
    Reducer query (the canonical frontend format):

      "Lawful tax reduction analysis for an individual under
       Income Tax for tax year 2025. Annual income: PKR
       5000000. Tax already paid: PKR 200000. ..."

    Returns None when the mandatory tax year or annual income
    cannot be extracted (the caller then skips the tool).
    """

    text = str(question) if question is not None else ""
    if not text.strip():
        return None

    year_match = _TAX_YEAR_QR.search(text)
    if year_match is None:
        return None
    tax_year = int(year_match.group(1))

    payload: dict[str, Any] = {"tax_year": tax_year, "question": text}

    income_match = _LABELLED_AMOUNTS[0][1].search(text)
    if income_match is None:
        return None
    income = _parse_amount(income_match.group(1))
    if income is None:
        return None
    payload["annual_income"] = income

    lowered = text.lower()
    if "sales tax" in lowered:
        payload["tax_type"] = "sales_tax"
    elif "federal excise" in lowered:
        payload["tax_type"] = "federal_excise"
    elif "customs" in lowered:
        payload["tax_type"] = "customs"
    else:
        payload["tax_type"] = "income_tax"

    if "for a business" in lowered or "for a company" in lowered:
        payload["entity_type"] = "company"
    else:
        payload["entity_type"] = "individual"

    for field_name, pattern in _LABELLED_AMOUNTS[1:]:
        m = pattern.search(text)
        if m is not None:
            value = _parse_amount(m.group(1))
            if value is not None:
                payload[field_name] = value

    return payload


# ============================================================
# TOOL
# ============================================================

_VALID_TAX_TYPES = ("income_tax", "sales_tax", "federal_excise", "customs")
_VALID_ENTITY_TYPES = ("individual", "company", "aop")

_MAX_NUMERIC = 1e15
_MAX_DEDUCTION_ENTRIES = 50


class TaxOptimizationTool(BaseTool):
    name: str = "tax_optimization"
    description: str = (
        "Analyzes a taxpayer's financial profile (tax year, "
        "income, expenses, investments, donations) and identifies "
        "lawful tax optimization opportunities under FBR "
        "legislation, with baseline and optimized estimate "
        "scenarios, estimated savings, evidence requirements, "
        "legal basis, and corpus provenance. Refuses any "
        "tax-evasion request."
    )

    # ---------- validation ----------

    def validate_input(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ToolError("Tool input must be a JSON object.")

        question = str(payload.get("question", "") or "")

        if detect_unlawful_intent(question):
            raise ToolError(_UNLAWFUL_RESPONSE)

        tax_year = payload.get("tax_year")
        if tax_year is None or tax_year == "":
            raise ToolError("tax_year is required.")
        try:
            tax_year = int(tax_year)
        except (TypeError, ValueError):
            raise ToolError(
                "tax_year must be an integer year such as 2025."
            )
        if not 2000 <= tax_year <= 2100:
            raise ToolError(
                "tax_year must be between 2000 and 2100."
            )

        tax_type = str(
            payload.get("tax_type", "income_tax") or "income_tax"
        ).strip().lower()
        if tax_type not in _VALID_TAX_TYPES:
            raise ToolError(
                "tax_type must be one of income_tax, sales_tax, "
                "federal_excise, customs."
            )

        entity_type = str(
            payload.get("entity_type", "individual") or "individual"
        ).strip().lower()
        if entity_type not in _VALID_ENTITY_TYPES:
            raise ToolError(
                "entity_type must be one of individual, company, aop."
            )

        clean: dict[str, Any] = {
            "tax_year": tax_year,
            "tax_type": tax_type,
            "entity_type": entity_type,
            "question": question,
        }

        for field_name in (
            "annual_income",
            "tax_already_paid",
            "allowable_expenses",
            "investments",
            "donations",
            "business_expenses",
        ):
            clean[field_name] = self._validate_number(
                field_name, payload.get(field_name, 0.0)
            )

        deductions = payload.get("deductions_exemptions")
        if deductions is None:
            deductions = {}
        if not isinstance(deductions, dict):
            raise ToolError(
                "deductions_exemptions must be a JSON object of "
                "{label: amount} entries."
            )
        if len(deductions) > _MAX_DEDUCTION_ENTRIES:
            raise ToolError(
                "deductions_exemptions must contain at most 50 entries."
            )
        checked: dict[str, float] = {}
        for key, value in deductions.items():
            if not isinstance(key, str) or not key.strip():
                raise ToolError(
                    "deductions_exemptions labels must be non-empty strings."
                )
            checked[key] = self._validate_number(
                f"deductions_exemptions[{key}]", value
            )
        clean["deductions_exemptions"] = checked

        return clean

    @staticmethod
    def _validate_number(field_name: str, value: Any) -> float:
        if value is None or value == "":
            return 0.0
        if isinstance(value, bool):
            raise ToolError(f"{field_name} must be a number.")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ToolError(f"{field_name} must be a number.")
        if number != number or number in (float("inf"), float("-inf")):
            raise ToolError(f"{field_name} must be a finite number.")
        if number < 0:
            raise ToolError(f"{field_name} must be zero or positive.")
        if number > _MAX_NUMERIC:
            raise ToolError(f"{field_name} is unreasonably large.")
        return number

    # ---------- execution ----------

    def execute(self, clean_payload: dict[str, Any]) -> dict[str, Any]:
        annual_income: float = clean_payload["annual_income"]
        tax_already_paid: float = clean_payload["tax_already_paid"]
        allowable_expenses: float = clean_payload["allowable_expenses"]
        investments: float = clean_payload["investments"]
        donations: float = clean_payload["donations"]
        business_expenses: float = clean_payload["business_expenses"]
        entity_type: str = clean_payload["entity_type"]

        # Baseline: the taxpayer's CURRENT lawful position —
        # income reduced by already-allowable business expenses.
        current_deductions = allowable_expenses + business_expenses
        baseline_taxable = max(0.0, annual_income - current_deductions)
        baseline_tax = _calculate_tax(baseline_taxable, entity_type)

        # Optimized: the baseline PLUS additional lawful
        # incentives (approved investments and donations).
        additional_incentives = investments + donations
        optimized_taxable = max(
            0.0, baseline_taxable - additional_incentives
        )
        optimized_tax = _calculate_tax(optimized_taxable, entity_type)

        savings = round(max(0.0, baseline_tax - optimized_tax), 2)
        net_liability = round(
            max(0.0, optimized_tax - tax_already_paid), 2
        )

        opportunities = self._detect_opportunities(clean_payload)

        return {
            "tax_year": clean_payload["tax_year"],
            "tax_type": clean_payload["tax_type"],
            "entity_type": entity_type,
            "lawful_only": True,
            "estimate_disclaimer": (
                "Baseline and optimized figures are estimates from a "
                "documented slab table; final liability requires FBR "
                "verification of eligibility and evidence."
            ),
            "opportunities": opportunities,
            "opportunity_count": len(opportunities),
            "baseline": {
                "taxable_income": round(baseline_taxable, 2),
                "estimated_tax": baseline_tax,
                "deductions_applied": round(current_deductions, 2),
            },
            "optimized": {
                "taxable_income": round(optimized_taxable, 2),
                "estimated_tax": optimized_tax,
                "deductions_incentives_applied": round(
                    additional_incentives, 2
                ),
                "breakdown": {
                    "allowable_expenses": round(allowable_expenses, 2),
                    "business_expenses": round(business_expenses, 2),
                    "investments": round(investments, 2),
                    "donations": round(donations, 2),
                },
            },
            "estimated_savings": savings,
            "net_liability_after_payments": net_liability,
            "tax_already_paid": round(tax_already_paid, 2),
            "sources": [
                {
                    "title": "Income Tax Ordinance 2001 (up to 2025)",
                    "document": "IncomeTaxOrdinance2001_upto2025.pdf",
                    "chunk_id": "ito_2001_first_schedule_division_i",
                    "legal_reference": (
                        "Income Tax Ordinance 2001, First Schedule "
                        "Division I (slabs), sections 56, 60A, 60D, "
                        "61, 62, 72, 147, 154, 154A, 22/Third Schedule"
                    ),
                    "sha256": _ITO_2001_SHA256,
                    "retrieval_method": "tax_optimization_static_catalogue",
                }
            ],
            "verification": {
                "verified": True,
                "verdict": "lawful_optimization_estimate",
                "basis": "documented_slab_table",
                "note": (
                    "Deterministic estimate; opportunity eligibility "
                    "is subject to FBR verification and supporting "
                    "evidence."
                ),
            },
        }

    # ---------- opportunity detection ----------

    def _detect_opportunities(
        self, clean_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        question: str = clean_payload["question"]
        haystack_parts: list[str] = [question]
        for field_name, hints in _NUMERIC_FIELD_HINTS.items():
            if clean_payload.get(field_name, 0.0) > 0:
                haystack_parts.extend(hints)
        haystack = " ".join(
            part for part in haystack_parts if part
        )

        matched: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for (
            pattern,
            opp_id,
            title,
            description,
            legal_basis,
        ) in _OPPORTUNITY_CATALOGUE:
            if opp_id in seen_ids:
                continue
            if not pattern.search(haystack):
                continue
            seen_ids.add(opp_id)
            matched.append(
                {
                    "id": opp_id,
                    "title": title,
                    "description": description,
                    "estimated_impact": self._impact_label(
                        opp_id,
                        clean_payload["annual_income"],
                    ),
                    "eligibility": "subject_to_fbr_verification",
                    "required_evidence": self._required_evidence(opp_id),
                    "legal_basis": legal_basis,
                }
            )

        # Every positive-income estimate always has at least the
        # withholding-credit reconciliation opportunity.
        if not matched and clean_payload["annual_income"] > 0:
            for entry in _OPPORTUNITY_CATALOGUE:
                if entry[1] == "withholding_credit":
                    pattern, opp_id, title, description, legal_basis = entry
                    matched.append(
                        {
                            "id": opp_id,
                            "title": title,
                            "description": description,
                            "estimated_impact": self._impact_label(
                                opp_id,
                                clean_payload["annual_income"],
                            ),
                            "eligibility": "subject_to_fbr_verification",
                            "required_evidence": self._required_evidence(opp_id),
                            "legal_basis": legal_basis,
                        }
                    )
                    break

        return matched

    @staticmethod
    def _impact_label(opp_id: str, annual_income: float) -> str:
        share = {
            "pension_contribution": 0.15,
            "life_insurance_premium": 0.10,
            "house_rent_allowance": 0.12,
            "charitable_donations": 0.08,
            "capital_allowance": 0.20,
            "medical_expenditure": 0.06,
            "education_expense": 0.05,
            "withholding_credit": 0.10,
            "profit_on_debt": 0.10,
            "teacher_researcher_credit": 0.25,
            "export_income": 0.15,
            "it_sector_credit": 0.20,
        }.get(opp_id, 0.05)
        base = annual_income * share * 0.25
        return (
            "Estimated tax reduction: up to PKR "
            f"{base:,.0f} (indicative only; verify eligibility)"
        )

    @staticmethod
    def _required_evidence(opp_id: str) -> list[str]:
        evidence: dict[str, list[str]] = {
            "pension_contribution": [
                "Pension fund contribution receipts",
                "Employer/payroll deduction certificate",
            ],
            "life_insurance_premium": [
                "Insurance premium payment receipts",
                "Policy document from the insurer",
            ],
            "house_rent_allowance": [
                "Rent agreement or landlord receipts",
                "Employer HRA breakdown in salary certificate",
            ],
            "charitable_donations": [
                "Donation receipts from approved NPOs",
                "Zakat deduction receipts",
            ],
            "capital_allowance": [
                "Asset purchase invoices",
                "Fixed-asset register with in-service dates",
            ],
            "medical_expenditure": [
                "Hospital/clinic payment receipts",
                "Health insurance premium certificates",
            ],
            "education_expense": [
                "Fee receipts from the institution",
                "Enrollment/attendance confirmation",
            ],
            "withholding_credit": [
                "Withholding tax certificates (all sources)",
                "Salary slip showing tax deducted",
                "Advance tax payment challans",
            ],
            "profit_on_debt": [
                "Loan agreement and profit-on-debt schedule",
                "Proof the loan financed the business",
            ],
            "teacher_researcher_credit": [
                "Employment contract (full-time teacher/researcher)",
                "Salary certificate from the institution",
            ],
            "export_income": [
                "Export proceeds realization certificates",
                "Bank credit advices (E-form)",
            ],
            "it_sector_credit": [
                "PSEB registration (where applicable)",
                "Export proceeds realization certificates",
            ],
        }
        return evidence.get(opp_id, ["Supporting documentation"])


_TAX_OPTIMIZATION_TOOL = TaxOptimizationTool()


def tax_optimize(payload: dict[str, Any]) -> ToolResult:
    """Module-level convenience wrapper (registry-style call)."""

    return _TAX_OPTIMIZATION_TOOL.run(payload)
