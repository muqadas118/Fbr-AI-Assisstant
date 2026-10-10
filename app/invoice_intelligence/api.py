"""
Invoice Intelligence API - Production-Grade
==========================================

High-level API for invoice operations.
"""

import logging
import json
from dataclasses import dataclass
from typing import Optional

from app.invoice_intelligence.extractor import ExtractedInvoice
from app.invoice_intelligence.analyzer import get_invoice_analyzer

logger = logging.getLogger("invoice_intelligence")


@dataclass
class InvoiceAPI:
    """High-level API for invoice operations."""

    def __init__(self):
        self.analyzer = get_invoice_analyzer()
        # Keyed by the invoice content key, never by the caller-supplied
        # invoice_id, so a re-sent invoice updates its own entry instead of
        # overwriting an unrelated one.
        self.invoice_store: dict[str, ExtractedInvoice] = {}
        # Every processed invoice, valid or rejected, so results are always
        # reportable (validation errors included).
        self.analysis_store: dict[str, dict] = {}

    @staticmethod
    def content_key(invoice: ExtractedInvoice) -> str:
        """Content key (seller + number + total + date) used as the store key."""
        return invoice.content_key()

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        """Retrieve a stored analysis payload, valid or rejected."""
        return self.analysis_store.get(analysis_id)

    def process_invoice(
        self,
        text: str,
        invoice_id: Optional[str] = None,
    ) -> dict:
        """Process single invoice and return result."""
        all_invoices = list(self.invoice_store.values())
        result = self.analyzer.analyze(text, invoice_id, all_invoices)

        # Store every result, valid or not; a rejected invoice is unreportable
        # if it is dropped here.
        store_key = self.content_key(result.invoice)
        self.invoice_store[store_key] = result.invoice

        payload = {
            "analysis_id": result.analysis_id,
            "content_key": store_key,
            "is_valid": result.validation.is_valid,
            "invoice": {
                "id": result.invoice.invoice_id,
                "number": result.invoice.invoice_number,
                "date": result.invoice.invoice_date,
                "type": result.invoice.invoice_type,
                "seller_ntn": result.invoice.seller_ntn,
                "buyer_ntn": result.invoice.buyer_ntn,
                "subtotal": result.invoice.subtotal,
                "tax_rate": result.invoice.tax_rate,
                "tax_amount": result.invoice.tax_amount,
                "total": result.invoice.total,
            },
            "validation": {
                "is_valid": result.validation.is_valid,
                "score": result.validation.score,
                "errors": result.validation.errors_count,
                "warnings": result.validation.warnings_count,
                "issues": [
                    {"field": i.field, "message": i.message, "severity": i.severity}
                    for i in result.validation.issues
                ],
            },
            "is_duplicate": result.is_duplicate,
            "duplicate_of": result.duplicate_of,
            "itc_eligible": result.itc_eligible,
            "tax_impact": result.tax_impact,
            "summary": result.summary,
            "duration_ms": result.duration_ms,
        }
        self.analysis_store[result.analysis_id] = payload

        return payload

    def reconcile_period(
        self,
        purchase_invoices: Optional[list[ExtractedInvoice]] = None,
        sales_invoices: Optional[list[ExtractedInvoice]] = None,
    ) -> dict:
        """Reconcile a period's invoices."""
        if purchase_invoices is None:
            purchase_invoices = [
                inv for inv in self.invoice_store.values()
                if inv.invoice_type == "purchase"
            ]
        if sales_invoices is None:
            sales_invoices = [
                inv for inv in self.invoice_store.values()
                if inv.invoice_type == "sales"
            ]

        report = self.analyzer.reconcile(purchase_invoices, sales_invoices)

        return {
            "total_invoices": report.total_invoices,
            "total_sales": report.total_sales,
            "total_purchases": report.total_purchases,
            "total_output_tax": report.total_output_tax,
            "total_input_tax": report.total_input_tax,
            "net_payable": report.net_payable,
            "vendor_count": len(report.vendor_summaries),
            "month_count": len(report.monthly_summaries),
            "confidence_score": report.confidence_score,
            "recommendations": report.recommendations,
        }

    def get_dashboard(self) -> dict:
        """Get invoice dashboard data."""
        invoices = list(self.invoice_store.values())
        sales = [i for i in invoices if i.invoice_type == "sales"]
        purchases = [i for i in invoices if i.invoice_type == "purchase"]

        total_sales = sum(i.total for i in sales)
        total_purchases = sum(i.total for i in purchases)
        total_output_tax = sum(i.tax_amount for i in sales)
        total_input_tax = sum(i.tax_amount for i in purchases)
        net_payable = total_output_tax - total_input_tax

        return {
            "total_invoices": len(invoices),
            "sales_count": len(sales),
            "purchases_count": len(purchases),
            "total_sales": total_sales,
            "total_purchases": total_purchases,
            "total_output_tax": total_output_tax,
            "total_input_tax": total_input_tax,
            "net_payable": net_payable,
            "payable_status": "payable" if net_payable > 0 else "refundable" if net_payable < 0 else "balanced",
        }

    def export_invoices(self, format: str = "json") -> str:
        """Export all stored invoices."""
        invoices = list(self.invoice_store.values())

        if format == "json":
            data = [
                {
                    "id": inv.invoice_id,
                    "number": inv.invoice_number,
                    "date": inv.invoice_date,
                    "type": inv.invoice_type,
                    "seller_ntn": inv.seller_ntn,
                    "buyer_ntn": inv.buyer_ntn,
                    "subtotal": inv.subtotal,
                    "tax_rate": inv.tax_rate,
                    "tax_amount": inv.tax_amount,
                    "total": inv.total,
                }
                for inv in invoices
            ]
            return json.dumps(data, indent=2)

        elif format == "csv":
            import csv
            import io
            output = io.StringIO()
            if invoices:
                writer = csv.DictWriter(
                    output,
                    fieldnames=["id", "number", "date", "type", "seller_ntn", "buyer_ntn", "subtotal", "tax_rate", "tax_amount", "total"],
                )
                writer.writeheader()
                for inv in invoices:
                    writer.writerow({
                        "id": inv.invoice_id,
                        "number": inv.invoice_number,
                        "date": inv.invoice_date,
                        "type": inv.invoice_type,
                        "seller_ntn": inv.seller_ntn or "",
                        "buyer_ntn": inv.buyer_ntn or "",
                        "subtotal": inv.subtotal,
                        "tax_rate": inv.tax_rate,
                        "tax_amount": inv.tax_amount,
                        "total": inv.total,
                    })
            return output.getvalue()

        else:
            raise ValueError(f"Unsupported format: {format}")


# Singleton
_api: Optional[InvoiceAPI] = None


def get_invoice_api() -> InvoiceAPI:
    """Get singleton invoice API."""
    global _api
    if _api is None:
        _api = InvoiceAPI()
    return _api
