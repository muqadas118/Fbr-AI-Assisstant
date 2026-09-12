"""
Form Parser - Production-Grade
===============================

Specialized parsers for FBR forms:
- Form 16A (Salary Certificate)
- Form 16B (WHT Certificate)
- Income Tax Return forms
- Sales Tax Return forms
- WHT Statement
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.document_intelligence.classifier import DocumentType


class FormType(str, Enum):
    """Types of FBR forms."""
    FORM_16A = "form_16a"
    FORM_16B = "form_16b"
    ITR_FORM = "itr_form"
    SALES_TAX_FORM = "sales_tax_form"
    WHT_STATEMENT = "wht_statement"
    WEALTH_STATEMENT = "wealth_statement"
    GENERIC = "generic"


@dataclass
class ParsedForm:
    """Result of form parsing."""
    form_type: FormType
    form_number: Optional[str] = None
    tax_year: Optional[str] = None
    employer_info: dict = field(default_factory=dict)
    employee_info: dict = field(default_factory=dict)
    salary_details: dict = field(default_factory=dict)
    tax_details: dict = field(default_factory=dict)
    wht_details: dict = field(default_factory=dict)
    income_details: dict = field(default_factory=dict)
    deductions: dict = field(default_factory=dict)
    raw_text: str = ""
    fields_extracted: int = 0
    total_fields: int = 0
    extraction_rate: float = 0.0
    notes: list[str] = field(default_factory=list)


class FormParser:
    """Parser for FBR forms."""

    @staticmethod
    def parse(text: str, form_type: FormType = FormType.GENERIC) -> ParsedForm:
        """Parse a form based on type."""
        if form_type == FormType.FORM_16A:
            return FormParser._parse_form_16a(text)
        elif form_type == FormType.FORM_16B:
            return FormParser._parse_form_16b(text)
        elif form_type == FormType.WEALTH_STATEMENT:
            return FormParser._parse_wealth_statement(text)
        else:
            return FormParser._parse_generic(text, form_type)

    @staticmethod
    def _parse_form_16a(text: str) -> ParsedForm:
        """Parse Form 16A - Salary Certificate."""
        form = ParsedForm(
            form_type=FormType.FORM_16A,
            raw_text=text,
        )
        notes = []

        # Form number
        form_num = re.search(r"(?:Form|Form-)\s*(16A)", text, re.IGNORECASE)
        if form_num:
            form.form_number = "16A"
            form.fields_extracted += 1

        # Tax year
        ty = re.search(r"Tax\s+Year[:\s]*(\d{4})", text, re.IGNORECASE)
        if ty:
            form.tax_year = ty.group(1)
            form.fields_extracted += 1

        # Employer info
        emp_name = re.search(r"(?:Employer|Name of Employer)[:\s]*([A-Za-z0-9\s&\.,]+)", text, re.IGNORECASE)
        if emp_name:
            form.employer_info["name"] = emp_name.group(1).strip()
            form.fields_extracted += 1

        emp_ntn = re.search(r"(?:Employer\s+)?NTN[:\s]*(\d{5,8}-?\d?)", text, re.IGNORECASE)
        if emp_ntn:
            form.employer_info["ntn"] = emp_ntn.group(1)
            form.fields_extracted += 1

        # Employee info
        emp_n = re.search(r"(?:Employee|Name of Employee)[:\s]*([A-Za-z\s]+?)(?:\n|Employer|Address)", text, re.IGNORECASE)
        if emp_n:
            form.employee_info["name"] = emp_n.group(1).strip()
            form.fields_extracted += 1

        emp_cnic = re.search(r"(?:CNIC|Employee\s+CNIC)[:\s]*(\d{5}-?\d{7}-?\d)", text, re.IGNORECASE)
        if emp_cnic:
            form.employee_info["cnic"] = emp_cnic.group(1)
            form.fields_extracted += 1

        # Salary details
        gross = re.search(r"Gross\s+Salary[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if gross:
            form.salary_details["gross_salary"] = float(gross.group(1).replace(",", ""))
            form.fields_extracted += 1

        taxable = re.search(r"Taxable\s+(?:Salary|Income)[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if taxable:
            form.salary_details["taxable_salary"] = float(taxable.group(1).replace(",", ""))
            form.fields_extracted += 1

        # Tax details
        tax_paid = re.search(r"Tax\s+(?:Paid|Deducted)[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if tax_paid:
            form.tax_details["tax_paid"] = float(tax_paid.group(1).replace(",", ""))
            form.fields_extracted += 1

        form.total_fields = 9
        form.extraction_rate = round(form.fields_extracted / form.total_fields, 2)

        if form.extraction_rate < 0.5:
            notes.append("Low extraction rate - check if document is Form 16A")

        form.notes = notes
        return form

    @staticmethod
    def _parse_form_16b(text: str) -> ParsedForm:
        """Parse Form 16B - WHT Certificate."""
        form = ParsedForm(
            form_type=FormType.FORM_16B,
            raw_text=text,
        )

        # Form number
        if re.search(r"16B", text, re.IGNORECASE):
            form.form_number = "16B"
            form.fields_extracted += 1

        # Tax year
        ty = re.search(r"Tax\s+Year[:\s]*(\d{4})", text, re.IGNORECASE)
        if ty:
            form.tax_year = ty.group(1)
            form.fields_extracted += 1

        # Withholder
        wh = re.search(r"(?:Withholder|Deductor)[:\s]*([A-Za-z0-9\s&\.,]+)", text, re.IGNORECASE)
        if wh:
            form.employer_info["withholder"] = wh.group(1).strip()
            form.fields_extracted += 1

        # Recipient
        recip = re.search(r"(?:Recipient|Deductee|Payee)[:\s]*([A-Za-z\s]+?)(?:\n|NTN)", text, re.IGNORECASE)
        if recip:
            form.employee_info["recipient"] = recip.group(1).strip()
            form.fields_extracted += 1

        # WHT section
        section = re.search(r"Section[:\s]*(\d+)", text, re.IGNORECASE)
        if section:
            form.wht_details["section"] = section.group(1)
            form.fields_extracted += 1

        # Amount paid
        paid = re.search(r"Amount\s+Paid[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if paid:
            form.wht_details["amount_paid"] = float(paid.group(1).replace(",", ""))
            form.fields_extracted += 1

        # Tax deducted
        deducted = re.search(r"Tax\s+Deducted[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if deducted:
            form.wht_details["tax_deducted"] = float(deducted.group(1).replace(",", ""))
            form.fields_extracted += 1

        form.total_fields = 7
        form.extraction_rate = round(form.fields_extracted / form.total_fields, 2)
        return form

    @staticmethod
    def _parse_wealth_statement(text: str) -> ParsedForm:
        """Parse Wealth Statement."""
        form = ParsedForm(
            form_type=FormType.WEALTH_STATEMENT,
            raw_text=text,
        )

        # Tax year
        ty = re.search(r"Tax\s+Year[:\s]*(\d{4})", text, re.IGNORECASE)
        if ty:
            form.tax_year = ty.group(1)
            form.fields_extracted += 1

        # Assets value
        assets = re.search(r"Total\s+Assets[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if assets:
            form.income_details["total_assets"] = float(assets.group(1).replace(",", ""))
            form.fields_extracted += 1

        # Liabilities
        liab = re.search(r"Total\s+Liabilities[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if liab:
            form.income_details["total_liabilities"] = float(liab.group(1).replace(",", ""))
            form.fields_extracted += 1

        # Net wealth
        net = re.search(r"Net\s+Wealth[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if net:
            form.income_details["net_wealth"] = float(net.group(1).replace(",", ""))
            form.fields_extracted += 1

        form.total_fields = 4
        form.extraction_rate = round(form.fields_extracted / form.total_fields, 2)
        return form

    @staticmethod
    def _parse_generic(text: str, form_type: FormType) -> ParsedForm:
        """Generic parsing for unknown forms."""
        form = ParsedForm(
            form_type=form_type,
            raw_text=text,
        )

        # Extract common fields
        if re.search(form_type.value, text, re.IGNORECASE):
            form.form_number = form_type.value
            form.fields_extracted += 1

        form.total_fields = 1
        form.extraction_rate = 1.0 if form.fields_extracted else 0.0
        return form
