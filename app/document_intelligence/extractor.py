"""
Document Information Extractor - Production-Grade
==================================================

Extracts structured information from documents:
- Names, addresses, NTN, CNIC
- Dates, amounts, quantities
- Reference numbers
- Tax-specific fields (rates, sections)
- Form field extraction
- Table extraction
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Any

from app.document_intelligence.classifier import DocumentType, DocumentCategory


@dataclass
class ExtractionField:
    """Single extracted field with confidence."""
    name: str
    value: Any
    confidence: float
    raw_text: str = ""
    source: str = ""  # regex, table, nlp


@dataclass
class ExtractedDocument:
    """All extracted document information."""
    document_id: str = ""
    document_type: str = "unknown"
    category: str = "other"

    # Common fields
    title: Optional[str] = None
    reference_number: Optional[str] = None
    issue_date: Optional[str] = None

    # People & entities
    person_name: Optional[str] = None
    person_cnic: Optional[str] = None
    person_ntn: Optional[str] = None
    company_name: Optional[str] = None
    company_ntn: Optional[str] = None

    # Money fields
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    net_amount: Optional[float] = None
    currency: str = "PKR"

    # Tax-specific
    tax_rate: Optional[float] = None
    tax_section: Optional[str] = None
    fbr_reference: Optional[str] = None

    # Address
    address: Optional[str] = None

    # Other fields
    fields: dict[str, Any] = field(default_factory=dict)

    # Quality metrics
    extraction_quality: float = 0.0
    raw_text: str = ""
    notes: list[str] = field(default_factory=list)


class DocumentExtractor:
    """Production-grade document info extractor."""

    PATTERNS = {
        "ntn": r"(?:NTN|National Tax No)[:\s]*(\d{5,8}-?\d?)",
        "cnic": r"(?:CNIC|Identity)[No.:\s]*(\d{5}-?\d{7}-?\d)",
        "reference": r"(?:Ref(?:erence)?|Ref\.?)\s*(?:No\.?)?[:\s]*([A-Z0-9/-]+)",
        "invoice_no": r"(?:Invoice|Bill)\s*(?:No\.?|Number)[:\s]*([A-Z0-9/-]+)",
        "date": r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        "amount_pkr": r"(?:PKR|Rs\.?|Rs)\s*([\d,]+(?:\.\d{1,2})?)",
        "amount": r"([\d,]+(?:\.\d{1,2})?)\s*(?:PKR|Rs\.?)?",
        "phone": r"(\+?92-?\d{3}-?\d{7}|\d{4}-?\d{7})",
        "email": r"([\w.-]+@[\w.-]+\.[a-zA-Z]{2,})",
        "section": r"Section\s+(\d+\w?(?:\(\d+\))?(?:\(\w+\))?)",
        "rate_percent": r"(\d+(?:\.\d+)?)\s*%",
        "iban": r"PK\d{2}[A-Z]{4}\d{16}",
    }

    @staticmethod
    def extract(text: str, document_type: str = "unknown") -> ExtractedDocument:
        """Extract all information from document text."""
        if not text:
            return ExtractedDocument(extraction_quality=0.0)

        doc = ExtractedDocument(
            document_type=document_type,
            raw_text=text[:2000],
        )
        fields_found = 0
        total_fields = 10
        notes = []

        # Extract common entities
        ntn = DocumentExtractor._extract_first(text, DocumentExtractor.PATTERNS["ntn"])
        if ntn:
            doc.person_ntn = ntn
            fields_found += 1

        cnic = DocumentExtractor._extract_first(text, DocumentExtractor.PATTERNS["cnic"])
        if cnic:
            doc.person_cnic = cnic
            fields_found += 1

        ref = DocumentExtractor._extract_first(text, DocumentExtractor.PATTERNS["reference"])
        if ref:
            doc.reference_number = ref
            fields_found += 1

        inv = DocumentExtractor._extract_first(text, DocumentExtractor.PATTERNS["invoice_no"])
        if inv:
            doc.reference_number = inv
            fields_found += 1

        # Date
        date_match = re.search(DocumentExtractor.PATTERNS["date"], text)
        if date_match:
            doc.issue_date = date_match.group(1)
            fields_found += 1

        # Amounts
        amounts = re.findall(DocumentExtractor.PATTERNS["amount_pkr"], text)
        if amounts:
            parsed = [float(a.replace(",", "")) for a in amounts]
            doc.total_amount = max(parsed) if parsed else None
            fields_found += 1

        # Email/phone
        email = re.search(DocumentExtractor.PATTERNS["email"], text)
        if email:
            doc.fields["email"] = email.group(1)
            fields_found += 1

        phone = re.search(DocumentExtractor.PATTERNS["phone"], text)
        if phone:
            doc.fields["phone"] = phone.group(1)
            fields_found += 1

        # Document-type specific extraction
        if document_type == DocumentType.SALES_INVOICE.value:
            DocumentExtractor._extract_invoice_fields(text, doc, notes)
            fields_found += 1
        elif document_type in (DocumentType.INCOME_TAX_RETURN.value, DocumentType.SALES_TAX_RETURN.value):
            DocumentExtractor._extract_return_fields(text, doc, notes)
            fields_found += 1
        elif document_type in (DocumentType.FORM_16A.value, DocumentType.SALARY_CERTIFICATE.value):
            DocumentExtractor._extract_salary_fields(text, doc, notes)
            fields_found += 1
        elif document_type == DocumentType.BANK_STATEMENT.value:
            DocumentExtractor._extract_bank_fields(text, doc, notes)
            fields_found += 1

        # Quality
        doc.extraction_quality = round(fields_found / total_fields, 2)

        if not fields_found:
            notes.append("No structured fields extracted - may need OCR")

        doc.notes = notes
        return doc

    @staticmethod
    def _extract_first(text: str, pattern: str) -> Optional[str]:
        """Extract first match."""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_invoice_fields(text: str, doc: ExtractedDocument, notes: list):
        """Extract invoice-specific fields."""
        # GST rate - search for percentage near GST/sales tax keywords
        gst_match = re.search(r"(?:GST|sales\s*tax)[^\d]{0,20}(\d+)\s*%", text, re.IGNORECASE)
        if not gst_match:
            gst_match = re.search(r"(\d+)\s*%", text, re.IGNORECASE)
        if gst_match:
            doc.tax_rate = float(gst_match.group(1))
            notes.append(f"Tax rate: {doc.tax_rate}%")

        # Quantity, unit price
        qty = re.search(r"(?:Qty|Quantity)[:\s]*(\d+)", text, re.IGNORECASE)
        if qty:
            doc.fields["quantity"] = int(qty.group(1))

        # Subtotal
        subtotal = re.search(r"(?:Sub\s*total|Subtotal)[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        if subtotal:
            doc.fields["subtotal"] = float(subtotal.group(1).replace(",", ""))

    @staticmethod
    def _extract_return_fields(text: str, doc: ExtractedDocument, notes: list):
        """Extract tax return fields."""
        # Tax year
        ty = re.search(r"Tax\s+Year[:\s]*(\d{4})", text, re.IGNORECASE)
        if ty:
            doc.fields["tax_year"] = int(ty.group(1))

        # Tax paid
        paid = re.search(r"Tax\s+Paid[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if paid:
            doc.fields["tax_paid"] = float(paid.group(1).replace(",", ""))

        # Total income
        ti = re.search(r"Total\s+Income[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if ti:
            doc.fields["total_income"] = float(ti.group(1).replace(",", ""))

    @staticmethod
    def _extract_salary_fields(text: str, doc: ExtractedDocument, notes: list):
        """Extract salary certificate fields."""
        gross = re.search(r"Gross\s+Salary[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if gross:
            doc.fields["gross_salary"] = float(gross.group(1).replace(",", ""))

        net = re.search(r"Net\s+(?:Pay|Salary)[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if net:
            doc.fields["net_salary"] = float(net.group(1).replace(",", ""))

        tax = re.search(r"Tax\s+Deducted[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if tax:
            doc.fields["tax_deducted"] = float(tax.group(1).replace(",", ""))

    @staticmethod
    def _extract_bank_fields(text: str, doc: ExtractedDocument, notes: list):
        """Extract bank statement fields."""
        # Account number
        acc = re.search(r"(?:Account|Acc\.?)\s*(?:No\.?)?[:\s]*(\d{8,16})", text, re.IGNORECASE)
        if acc:
            doc.fields["account_number"] = acc.group(1)

        # IBAN
        iban = re.search(DocumentExtractor.PATTERNS["iban"], text)
        if iban:
            doc.fields["iban"] = iban.group(0)

        # Opening/closing balance
        op = re.search(r"Opening\s+Balance[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if op:
            doc.fields["opening_balance"] = float(op.group(1).replace(",", ""))

        cb = re.search(r"Closing\s+Balance[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+)", text, re.IGNORECASE)
        if cb:
            doc.fields["closing_balance"] = float(cb.group(1).replace(",", ""))
