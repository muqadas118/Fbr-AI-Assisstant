"""
Invoice Reconciler - Production-Grade
======================================

Comprehensive reconciliation reporting:
- ITC (Input Tax Credit) reconciliation
- Vendor-wise reconciliation
- Monthly summaries
- Mismatch reports
- Cash flow impact
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime

from app.invoice_intelligence.extractor import ExtractedInvoice
from app.invoice_intelligence.matcher import InvoiceMatcher, MatchResult


@dataclass
class VendorSummary:
    """Summary for a single vendor."""
    vendor_ntn: str
    vendor_name: Optional[str] = None
    invoice_count: int = 0
    total_purchases: float = 0.0
    total_tax: float = 0.0
    matched_count: int = 0
    unmatched_count: int = 0


@dataclass
class MonthlySummary:
    """Summary for a single month."""
    year: int
    month: int
    invoice_count: int = 0
    total_sales: float = 0.0
    total_purchases: float = 0.0
    output_tax: float = 0.0
    input_tax: float = 0.0
    net_payable: float = 0.0


@dataclass
class ReconciliationReport:
    """Comprehensive reconciliation report."""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    total_invoices: int = 0

    # Totals
    total_sales: float = 0.0
    total_purchases: float = 0.0
    total_output_tax: float = 0.0
    total_input_tax: float = 0.0
    net_payable: float = 0.0

    # By vendor
    vendor_summaries: list[VendorSummary] = field(default_factory=list)

    # By month
    monthly_summaries: list[MonthlySummary] = field(default_factory=list)

    # Mismatches
    unmatched_purchases: int = 0
    duplicate_count: int = 0
    total_unclaimed_itc: float = 0.0

    # Quality
    confidence_score: float = 0.0

    # Notes
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""


class InvoiceReconciler:
    """Reconcile invoices for tax filing."""

    @staticmethod
    def reconcile(
        purchase_invoices: list[ExtractedInvoice],
        sales_invoices: list[ExtractedInvoice],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ReconciliationReport:
        """Generate reconciliation report."""
        sales_invoices = list(sales_invoices)
        purchase_invoices = list(purchase_invoices)
        all_invoices = sales_invoices + purchase_invoices

        report = ReconciliationReport(
            total_invoices=len(purchase_invoices) + len(sales_invoices),
            generated_at=datetime.utcnow().isoformat(),
        )

        # Period boundaries come from the invoices actually reconciled
        parsed_dates = [
            d for d in (
                InvoiceReconciler._parse_date(inv.invoice_date)
                for inv in all_invoices
            ) if d is not None
        ]
        report.period_start = (
            start_date or (min(parsed_dates) if parsed_dates else None)
        )
        report.period_start = (
            report.period_start.isoformat() if report.period_start else None
        )
        report.period_end = (
            end_date or (max(parsed_dates) if parsed_dates else None)
        )
        report.period_end = (
            report.period_end.isoformat() if report.period_end else None
        )

        # Sales totals
        for inv in sales_invoices:
            report.total_sales += inv.total
            report.total_output_tax += inv.tax_amount

        # Purchase totals
        for inv in purchase_invoices:
            report.total_purchases += inv.total
            report.total_input_tax += inv.tax_amount

        # Net payable = output - input
        report.net_payable = report.total_output_tax - report.total_input_tax

        # By vendor
        vendor_data: dict[str, VendorSummary] = {}
        for inv in purchase_invoices:
            ntn = inv.seller_ntn or "unknown"
            if ntn not in vendor_data:
                vendor_data[ntn] = VendorSummary(
                    vendor_ntn=ntn,
                    vendor_name=inv.seller_name,
                )
            v = vendor_data[ntn]
            v.invoice_count += 1
            v.total_purchases += inv.total
            v.total_tax += inv.tax_amount

        report.vendor_summaries = list(vendor_data.values())

        # ITC matching: which purchases have a matching sales invoice
        matched_purchases: list[ExtractedInvoice] = []
        unmatched_purchases = 0
        total_unclaimed_itc = 0.0

        sales_only = [inv for inv in sales_invoices if inv.invoice_type == "sales"]
        for purchase in purchase_invoices:
            best_match: Optional[MatchResult] = None
            best_confidence = 0.0
            for sales in sales_only:
                match = InvoiceMatcher.match_purchase_to_sales(purchase, sales)
                if match.confidence > best_confidence:
                    best_confidence = match.confidence
                    best_match = match

            if best_match is not None and best_match.is_match:
                matched_purchases.append(purchase)
            else:
                unmatched_purchases += 1
                total_unclaimed_itc += purchase.tax_amount

        report.unmatched_purchases = unmatched_purchases
        report.total_unclaimed_itc = round(total_unclaimed_itc, 2)

        for v in report.vendor_summaries:
            v.matched_count = sum(
                1 for p in matched_purchases
                if (p.seller_ntn or "unknown") == v.vendor_ntn
            )
            v.unmatched_count = v.invoice_count - v.matched_count

        # Duplicate detection: each invoice that repeats an earlier record
        duplicate_count = 0
        seen: list[ExtractedInvoice] = []
        for inv in all_invoices:
            if InvoiceMatcher.find_duplicate(inv, seen):
                duplicate_count += 1
            seen.append(inv)
        report.duplicate_count = duplicate_count

        # By month
        monthly_data: dict[tuple[int, int], MonthlySummary] = {}
        for inv in all_invoices:
            d = InvoiceReconciler._parse_date(inv.invoice_date)
            if d is None:
                continue
            key = (d.year, d.month)
            if key not in monthly_data:
                monthly_data[key] = MonthlySummary(year=d.year, month=d.month)
            m = monthly_data[key]
            m.invoice_count += 1
            if inv.invoice_type == "purchase":
                m.total_purchases += inv.total
                m.input_tax += inv.tax_amount
            else:
                m.total_sales += inv.total
                m.output_tax += inv.tax_amount

        # Net payable by month
        for m in monthly_data.values():
            m.net_payable = m.output_tax - m.input_tax

        report.monthly_summaries = sorted(
            monthly_data.values(),
            key=lambda x: (x.year, x.month)
        )

        # Calculate confidence
        if report.total_invoices > 0:
            valid_invoices = sum(
                1 for inv in purchase_invoices + sales_invoices
                if inv.invoice_number and inv.total > 0
            )
            report.confidence_score = round(
                valid_invoices / report.total_invoices, 2
            )

        # Recommendations
        report.recommendations = InvoiceReconciler._build_recommendations(report)

        return report

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        """Parse an invoice date, returning None when it is missing or invalid."""
        if not value:
            return None
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _build_recommendations(report: ReconciliationReport) -> list[str]:
        """Build recommendations based on reconciliation."""
        recs = []

        if report.net_payable > 0:
            recs.append(
                f"💰 You have net tax payable of PKR {report.net_payable:,.2f}. "
                f"Deposit by the 15th of next month."
            )
        elif report.net_payable < 0:
            recs.append(
                f"📋 You have net tax credit of PKR {abs(report.net_payable):,.2f}. "
                f"File refund claim or carry forward."
            )
        else:
            recs.append("✓ Sales and purchases are balanced this period.")

        if report.unmatched_purchases > 0:
            recs.append(
                f"⚠️ {report.unmatched_purchases} purchase invoices have no matching sales. "
                f"ITC may be disallowed."
            )

        if report.duplicate_count > 0:
            recs.append(
                f"🔴 {report.duplicate_count} duplicate invoices detected. "
                f"Review and remove before filing."
            )

        recs.append("💡 File monthly/quarterly sales tax return on time.")
        recs.append("💡 Reconcile bank statements with invoice payments.")

        return recs
