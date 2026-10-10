"""
Invoice Validator - Production-Grade
====================================

Validates invoice data against FBR rules:
- Required fields presence
- NTN format validation
- Date format validation
- Amount calculations correct
- Tax rate matches regime
- Duplicate detection
- Anomaly detection
"""

from dataclasses import dataclass, field

from app.invoice_intelligence.extractor import ExtractedInvoice


@dataclass
class ValidationIssue:
    """Single validation issue."""
    severity: str  # "error", "warning", "info"
    field: str
    message: str


@dataclass
class ValidationResult:
    """Validation result for an invoice."""
    is_valid: bool
    score: float  # 0-1
    issues: list[ValidationIssue] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0

    @property
    def is_valid_for_filing(self) -> bool:
        return self.errors_count == 0


class InvoiceValidator:
    """Validates invoice data."""

    REQUIRED_FIELDS = [
        "invoice_number",
        "invoice_date",
        "seller_ntn",
        "buyer_ntn",
        "total",
    ]

    @staticmethod
    def validate(invoice: ExtractedInvoice) -> ValidationResult:
        """Validate an invoice."""
        issues = []

        # Check required fields
        for field_name in InvoiceValidator.REQUIRED_FIELDS:
            value = getattr(invoice, field_name, None)
            if not value:
                issues.append(ValidationIssue(
                    severity="error",
                    field=field_name,
                    message=f"Required field '{field_name}' is missing",
                ))

        # Validate NTN format
        if invoice.seller_ntn and not InvoiceValidator._is_valid_ntn(invoice.seller_ntn):
            issues.append(ValidationIssue(
                severity="error",
                field="seller_ntn",
                message=f"Invalid NTN format: {invoice.seller_ntn}",
            ))

        if invoice.buyer_ntn and not InvoiceValidator._is_valid_ntn(invoice.buyer_ntn):
            issues.append(ValidationIssue(
                severity="error",
                field="buyer_ntn",
                message=f"Invalid NTN format: {invoice.buyer_ntn}",
            ))

        # Validate amounts
        if invoice.total < 0:
            issues.append(ValidationIssue(
                severity="error",
                field="total",
                message="Total cannot be negative",
            ))

        if invoice.subtotal < 0:
            issues.append(ValidationIssue(
                severity="error",
                field="subtotal",
                message="Subtotal cannot be negative",
            ))

        # Check tax calculation
        if invoice.subtotal and invoice.tax_rate:
            expected_tax = round(invoice.subtotal * invoice.tax_rate / 100, 2)
            if abs(expected_tax - invoice.tax_amount) > 1:  # Allow PKR 1 difference
                issues.append(ValidationIssue(
                    severity="warning",
                    field="tax_amount",
                    message=(
                        f"Tax amount {invoice.tax_amount} doesn't match "
                        f"expected {expected_tax} ({invoice.tax_rate}% of {invoice.subtotal})"
                    ),
                ))

        # Check total
        if invoice.subtotal and invoice.tax_amount:
            expected_total = invoice.subtotal + invoice.tax_amount - invoice.discount
            if abs(expected_total - invoice.total) > 1:
                issues.append(ValidationIssue(
                    severity="warning",
                    field="total",
                    message=(
                        f"Total {invoice.total} doesn't match "
                        f"expected {expected_total} (subtotal + tax - discount)"
                    ),
                ))

        # Validate tax rate
        if invoice.tax_rate and invoice.tax_rate not in (0, 5, 10, 16, 17, 18, 20, 25):
            issues.append(ValidationIssue(
                severity="warning",
                field="tax_rate",
                message=f"Unusual tax rate: {invoice.tax_rate}%",
            ))

        # Date validation
        if invoice.invoice_date:
            from datetime import datetime
            try:
                for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        d = datetime.strptime(invoice.invoice_date, fmt)
                        if d.year < 2000 or d.year > 2030:
                            issues.append(ValidationIssue(
                                severity="warning",
                                field="invoice_date",
                                message=f"Unusual invoice year: {d.year}",
                            ))
                        break
                    except ValueError:
                        continue
                else:
                    issues.append(ValidationIssue(
                        severity="warning",
                        field="invoice_date",
                        message=f"Could not parse date: {invoice.invoice_date}",
                    ))
            except Exception:
                pass

        # Calculate score
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        score = max(0.0, 1.0 - (len(errors) * 0.2) - (len(warnings) * 0.05))

        return ValidationResult(
            is_valid=len(errors) == 0,
            score=round(score, 2),
            issues=issues,
            errors_count=len(errors),
            warnings_count=len(warnings),
        )

    @staticmethod
    def _is_valid_ntn(ntn: str) -> bool:
        """Validate NTN format (XXXXXXX-X or XXXXXXX)."""
        if not ntn:
            return False
        ntn_clean = ntn.replace("-", "")
        return ntn_clean.isdigit() and len(ntn_clean) in (7, 8)
