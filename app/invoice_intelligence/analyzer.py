"""
Invoice Analyzer - Unified Engine
================================

Combines extraction, validation, and analysis into one workflow.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.invoice_intelligence.extractor import InvoiceExtractor, ExtractedInvoice
from app.invoice_intelligence.validator import InvoiceValidator, ValidationResult
from app.invoice_intelligence.matcher import InvoiceMatcher, MatchResult
from app.invoice_intelligence.reconciler import InvoiceReconciler, ReconciliationReport

logger = logging.getLogger("invoice_intelligence")


@dataclass
class InvoiceAnalysis:
    """Complete invoice analysis."""
    analysis_id: str
    timestamp: str
    duration_ms: float

    # Invoice data
    invoice: ExtractedInvoice

    # Validation
    validation: ValidationResult

    # Analysis
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    itc_eligible: bool = False
    tax_impact: float = 0.0

    # Summary
    summary: str = ""
    formatted_text: str = ""


class InvoiceAnalyzer:
    """Unified invoice analysis engine."""

    def __init__(self):
        self.extractor = InvoiceExtractor()
        self.validator = InvoiceValidator()
        self.matcher = InvoiceMatcher()
        self.reconciler = InvoiceReconciler()
        self.audit_log: list[dict] = []

    def analyze(
        self,
        text: str,
        invoice_id: Optional[str] = None,
        invoice_list: Optional[list[ExtractedInvoice]] = None,
    ) -> InvoiceAnalysis:
        """Analyze a single invoice."""
        start_time = time.time()
        analysis_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Extract
        invoice = self.extractor.extract(text)
        invoice.invoice_id = invoice_id or analysis_id

        # Validate
        validation = self.validator.validate(invoice)

        # Check for duplicates
        is_duplicate = False
        duplicate_of = None
        if invoice_list:
            match = self.matcher.find_duplicate(invoice, invoice_list)
            if match and match.is_match:
                is_duplicate = True
                duplicate_of = match.matched_invoice_id

        # ITC eligibility (for purchases)
        itc_eligible = (
            invoice.invoice_type == "purchase"
            and validation.is_valid
            and invoice.tax_amount > 0
            and invoice.seller_ntn
        )

        # Tax impact
        tax_impact = invoice.tax_amount if itc_eligible else -invoice.tax_amount

        # Summary
        summary = self._build_summary(invoice, validation, is_duplicate)

        # Format
        formatted = self._format_analysis(invoice, validation)

        duration_ms = (time.time() - start_time) * 1000

        # Audit
        self.audit_log.append({
            "analysis_id": analysis_id,
            "timestamp": timestamp,
            "invoice_number": invoice.invoice_number,
            "invoice_type": invoice.invoice_type,
            "total": invoice.total,
            "duration_ms": round(duration_ms, 3),
        })

        return InvoiceAnalysis(
            analysis_id=analysis_id,
            timestamp=timestamp,
            duration_ms=round(duration_ms, 3),
            invoice=invoice,
            validation=validation,
            is_duplicate=is_duplicate,
            duplicate_of=duplicate_of,
            itc_eligible=itc_eligible,
            tax_impact=tax_impact,
            summary=summary,
            formatted_text=formatted,
        )

    def reconcile(
        self,
        purchase_invoices: list[ExtractedInvoice],
        sales_invoices: list[ExtractedInvoice],
    ) -> ReconciliationReport:
        """Reconcile multiple invoices."""
        return self.reconciler.reconcile(purchase_invoices, sales_invoices)

    def _build_summary(
        self,
        invoice: ExtractedInvoice,
        validation: ValidationResult,
        is_duplicate: bool,
    ) -> str:
        """Build concise summary."""
        parts = []

        parts.append(f"Type: {invoice.invoice_type.title()}")
        parts.append(f"Inv#: {invoice.invoice_number or 'N/A'}")

        if invoice.total:
            parts.append(f"PKR {invoice.total:,.0f}")

        if invoice.tax_amount:
            parts.append(f"Tax: PKR {invoice.tax_amount:,.0f} ({invoice.tax_rate}%)")

        if validation.is_valid:
            parts.append("✓ Valid")
        else:
            parts.append(f"✗ {validation.errors_count} errors")

        if is_duplicate:
            parts.append("⚠️ DUPLICATE")

        if invoice.invoice_type == "purchase" and invoice.tax_amount > 0:
            parts.append("📋 ITC Eligible")

        return " | ".join(parts)

    def _format_analysis(
        self,
        invoice: ExtractedInvoice,
        validation: ValidationResult,
    ) -> str:
        """Format as readable text."""
        lines = [
            "=" * 60,
            "INVOICE ANALYSIS",
            "=" * 60,
            "",
            f"Invoice #: {invoice.invoice_number or 'N/A'}",
            f"Date: {invoice.invoice_date or 'N/A'}",
            f"Type: {invoice.invoice_type.title()}",
            "",
            "--- Parties ---",
            f"Seller NTN: {invoice.seller_ntn or 'N/A'}",
            f"Buyer NTN: {invoice.buyer_ntn or 'N/A'}",
            "",
            "--- Amounts ---",
            f"Subtotal: PKR {invoice.subtotal:,.2f}" if invoice.subtotal else "Subtotal: N/A",
            f"Tax ({invoice.tax_rate}%): PKR {invoice.tax_amount:,.2f}" if invoice.tax_amount else "Tax: N/A",
            f"Total: PKR {invoice.total:,.2f}" if invoice.total else "Total: N/A",
            "",
            "--- Validation ---",
            f"Valid: {'YES' if validation.is_valid else 'NO'}",
            f"Score: {int(validation.score * 100)}%",
            f"Errors: {validation.errors_count}",
            f"Warnings: {validation.warnings_count}",
            "",
        ]

        if validation.issues:
            lines.append("Issues:")
            for issue in validation.issues:
                icon = "✗" if issue.severity == "error" else "⚠"
                lines.append(f"  {icon} {issue.field}: {issue.message}")

        lines.append("=" * 60)
        return "\n".join(lines)


# Singleton
_analyzer: Optional[InvoiceAnalyzer] = None


def get_invoice_analyzer() -> InvoiceAnalyzer:
    """Get singleton invoice analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = InvoiceAnalyzer()
    return _analyzer
