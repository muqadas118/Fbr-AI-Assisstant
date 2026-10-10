"""
Invoice Intelligence
====================

Invoice extraction, validation and reconciliation:
- Invoice data extraction (sales, purchase, service)
- FBR rule validation (required fields, NTN format, amount and date checks)
- Duplicate detection on invoice content (seller + number + total + date)
- Purchase-to-sales matching for ITC reconciliation
- Vendor-wise and monthly reconciliation summaries
- Net tax payable and reconciliation recommendations
- High-level API: process, reconcile, dashboard and export

Storage is in-memory only (no persistence, customer/anomaly analytics or
bulk processing).
"""

from app.invoice_intelligence.extractor import InvoiceExtractor, ExtractedInvoice
from app.invoice_intelligence.validator import InvoiceValidator, ValidationResult
from app.invoice_intelligence.matcher import InvoiceMatcher, MatchResult
from app.invoice_intelligence.reconciler import InvoiceReconciler, ReconciliationReport
from app.invoice_intelligence.analyzer import InvoiceAnalyzer, get_invoice_analyzer
from app.invoice_intelligence.api import InvoiceAPI, get_invoice_api

__all__ = [
    "InvoiceExtractor",
    "ExtractedInvoice",
    "InvoiceValidator",
    "ValidationResult",
    "InvoiceMatcher",
    "MatchResult",
    "InvoiceReconciler",
    "ReconciliationReport",
    "InvoiceAnalyzer",
    "get_invoice_analyzer",
    "InvoiceAPI",
    "get_invoice_api",
]
