"""
Invoice Matcher - Production-Grade
===================================

Match invoices for ITC reconciliation:
- Match sales invoice with corresponding purchase invoice
- Find duplicate invoices
- Match PO to invoice
- Match delivery challan to invoice
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime

from app.invoice_intelligence.extractor import ExtractedInvoice


@dataclass
class MatchResult:
    """Result of matching operation."""
    is_match: bool
    match_type: str  # "exact", "fuzzy", "partial", "no_match"
    confidence: float
    matched_invoice_id: Optional[str] = None
    reason: str = ""
    amount_difference: float = 0.0
    date_difference_days: int = 0


class InvoiceMatcher:
    """Match invoices for various purposes."""

    @staticmethod
    def find_duplicate(
        invoice: ExtractedInvoice,
        invoice_list: list[ExtractedInvoice],
    ) -> Optional[MatchResult]:
        """
        Find duplicate invoice based on:
        - Same invoice number + same seller
        - Same amount + same date
        """
        if not invoice.invoice_number or not invoice.seller_ntn:
            return None

        for other in invoice_list:
            if other.invoice_id == invoice.invoice_id:
                continue

            # Same seller + same invoice number = duplicate
            if (
                invoice.seller_ntn == other.seller_ntn
                and invoice.invoice_number == other.invoice_number
            ):
                return MatchResult(
                    is_match=True,
                    match_type="exact",
                    confidence=0.99,
                    matched_invoice_id=other.invoice_id,
                    reason="Same seller and invoice number",
                )

            # Same amount + same date + similar seller = potential duplicate
            if (
                invoice.seller_ntn == other.seller_ntn
                and invoice.invoice_date == other.invoice_date
                and invoice.total == other.total
                and abs(invoice.total) > 0
            ):
                return MatchResult(
                    is_match=True,
                    match_type="fuzzy",
                    confidence=0.85,
                    matched_invoice_id=other.invoice_id,
                    reason="Same seller, date, and amount",
                )

        return None

    @staticmethod
    def match_purchase_to_sales(
        purchase: ExtractedInvoice,
        sales_invoice: ExtractedInvoice,
    ) -> MatchResult:
        """
        Match a purchase invoice to a sales invoice.
        Both should reference the same transaction.
        """
        if not purchase.buyer_ntn or not sales_invoice.seller_ntn:
            return MatchResult(
                is_match=False,
                match_type="no_match",
                confidence=0.0,
                reason="Missing NTN",
            )

        # Different parties required (purchase is BUYER, sales is SELLER)
        if purchase.buyer_ntn != sales_invoice.seller_ntn:
            return MatchResult(
                is_match=False,
                match_type="no_match",
                confidence=0.0,
                reason="NTN mismatch",
            )

        # Check amount match
        amount_diff = abs(purchase.total - sales_invoice.total)
        if amount_diff < 1:
            amount_score = 1.0
        elif amount_diff / max(purchase.total, 1) < 0.05:
            amount_score = 0.8
        else:
            amount_score = 0.3

        # Date proximity
        try:
            d1 = datetime.strptime(purchase.invoice_date, "%d-%m-%Y")
            d2 = datetime.strptime(sales_invoice.invoice_date, "%d-%m-%Y")
            date_diff = abs((d1 - d2).days)
            date_score = max(0, 1 - date_diff / 30)  # 30-day window
        except (ValueError, TypeError):
            date_score = 0.5
            date_diff = 0

        # Invoice number similarity
        inv_score = 0.5
        if purchase.invoice_number and sales_invoice.invoice_number:
            if purchase.invoice_number == sales_invoice.invoice_number:
                inv_score = 1.0
            elif purchase.invoice_number in sales_invoice.invoice_number:
                inv_score = 0.8

        # Overall confidence
        confidence = (amount_score * 0.5) + (date_score * 0.3) + (inv_score * 0.2)

        return MatchResult(
            is_match=confidence > 0.6,
            match_type="exact" if confidence > 0.9 else "fuzzy" if confidence > 0.6 else "partial",
            confidence=round(confidence, 3),
            matched_invoice_id=sales_invoice.invoice_id,
            reason=f"Amount diff: {amount_diff:.0f}, Date diff: {date_diff} days",
            amount_difference=amount_diff,
            date_difference_days=date_diff,
        )

    @staticmethod
    def match_po_to_invoice(
        po_number: str,
        invoice: ExtractedInvoice,
    ) -> MatchResult:
        """Match purchase order to invoice."""
        if not po_number or not invoice.po_number:
            return MatchResult(
                is_match=False,
                match_type="no_match",
                confidence=0.0,
                reason="Missing PO number",
            )

        if po_number == invoice.po_number:
            return MatchResult(
                is_match=True,
                match_type="exact",
                confidence=1.0,
                reason="PO numbers match",
            )

        return MatchResult(
            is_match=False,
            match_type="no_match",
            confidence=0.0,
            reason="PO numbers don't match",
        )

    @staticmethod
    def reconcile_itc(
        purchase_invoices: list[ExtractedInvoice],
        sales_invoices: list[ExtractedInvoice],
    ) -> list[MatchResult]:
        """
        Reconcile Input Tax Credit (ITC).
        For each purchase invoice, find matching sales invoice.
        """
        results = []
        for purchase in purchase_invoices:
            if purchase.invoice_type != "purchase":
                continue

            best_match = None
            best_confidence = 0.0

            for sales in sales_invoices:
                if sales.invoice_type != "sales":
                    continue
                match = InvoiceMatcher.match_purchase_to_sales(purchase, sales)
                if match.confidence > best_confidence:
                    best_confidence = match.confidence
                    best_match = match

            if best_match:
                results.append(best_match)
            else:
                results.append(MatchResult(
                    is_match=False,
                    match_type="no_match",
                    confidence=0.0,
                    matched_invoice_id=purchase.invoice_id,
                    reason="No matching sales invoice found",
                ))

        return results
