"""
Invoice Extractor - Production-Grade
====================================

Extract structured data from invoices (sales & purchase).
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineItem:
    """Single line item in an invoice."""
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    hs_code: Optional[str] = None  # Harmonized System code


@dataclass
class ExtractedInvoice:
    """Extracted invoice data."""
    invoice_id: str = ""
    invoice_number: str = ""
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None

    # Parties
    seller_name: Optional[str] = None
    seller_ntn: Optional[str] = None
    seller_address: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_ntn: Optional[str] = None
    buyer_address: Optional[str] = None

    # Amounts
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    discount: float = 0.0
    total: float = 0.0

    # Tax breakdown
    sales_tax: float = 0.0
    wht_amount: float = 0.0
    net_payable: float = 0.0

    # Type
    invoice_type: str = "sales"  # sales, purchase, service
    currency: str = "PKR"

    # Reference
    po_number: Optional[str] = None
    reference: Optional[str] = None

    # Line items
    line_items: list[LineItem] = field(default_factory=list)

    # Quality
    extraction_quality: float = 0.0
    raw_text: str = ""
    notes: list[str] = field(default_factory=list)

    def content_key(self) -> str:
        """
        Stable key built from the invoice content itself (seller NTN +
        invoice number + total + date), not from the caller-supplied
        invoice_id, so a re-sent invoice maps to the same key and two
        records with identical content are recognised as duplicates.
        """
        if not self.invoice_number and not self.seller_ntn:
            # Extraction failed: key on the raw text so distinct inputs
            # do not collide on an empty identity.
            return hashlib.sha1(
                (self.raw_text or "")[:2000].encode("utf-8", "replace")
            ).hexdigest()
        raw = "|".join([
            self.seller_ntn or "",
            self.invoice_number or "",
            f"{self.total:.2f}",
            self.invoice_date or "",
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class InvoiceExtractor:
    """Extract invoice data from text."""

    PATTERNS = {
        "invoice_no": r"(?:Invoice|Bill)\s*(?:No\.?|Number|#)[:\s]*([A-Z0-9/-]+)",
        "invoice_no_inline": r"(?:Sales\s+Invoice|Purchase\s+Invoice|Invoice)\s+([A-Z0-9/-]+)",
        "date": r"(?:Invoice\s+Date|Date|Bill\s+Date)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        "ntn": r"(?:NTN|National\s+Tax\s+No)[:\s]*(\d{5,8}-?\d?)",
        "amount": r"([\d,]+(?:\.\d{1,2})?)",
        "rate": r"(\d+(?:\.\d+)?)\s*%",
    }

    @staticmethod
    def extract(text: str) -> ExtractedInvoice:
        """Extract invoice data from text."""
        inv = ExtractedInvoice(raw_text=text[:2000])
        fields_found = 0
        total_fields = 10

        # Invoice number - try labeled first, then inline
        inv_no = re.search(InvoiceExtractor.PATTERNS["invoice_no"], text, re.IGNORECASE)
        if inv_no:
            inv.invoice_number = inv_no.group(1).strip()
            fields_found += 1
        else:
            # Try inline pattern like "Sales Invoice INV-001"
            inv_no2 = re.search(InvoiceExtractor.PATTERNS["invoice_no_inline"], text, re.IGNORECASE)
            if inv_no2:
                inv.invoice_number = inv_no2.group(1).strip()
                fields_found += 1

        # Date
        date_m = re.search(InvoiceExtractor.PATTERNS["date"], text, re.IGNORECASE)
        if date_m:
            inv.invoice_date = date_m.group(1)
            fields_found += 1

        # NTN
        ntns = re.findall(InvoiceExtractor.PATTERNS["ntn"], text, re.IGNORECASE)
        if len(ntns) >= 1:
            inv.seller_ntn = ntns[0]
            fields_found += 1
        if len(ntns) >= 2:
            inv.buyer_ntn = ntns[1]
            fields_found += 1

        # Subtotal
        sub_m = re.search(
            r"Sub\s*-?\s*Total[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
            text,
            re.IGNORECASE,
        )
        if sub_m:
            inv.subtotal = float(sub_m.group(1).replace(",", ""))
            fields_found += 1

        # Tax rate
        rate_m = re.search(
            r"(?:GST|Sales\s*Tax|Tax)\s*(?:\(|\@)?\s*(\d+(?:\.\d+)?)\s*%",
            text,
            re.IGNORECASE,
        )
        if rate_m:
            inv.tax_rate = float(rate_m.group(1))
            fields_found += 1

        # Tax amount - look for "Tax" not followed by "rate"
        tax_m = re.search(
            r"(?:Tax|GST|Sales\s*Tax)\s+Amount[:\s]*(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
            text,
            re.IGNORECASE,
        )
        if tax_m:
            inv.tax_amount = float(tax_m.group(1).replace(",", ""))
            fields_found += 1
        elif inv.subtotal and inv.tax_rate:
            # Calculate from subtotal and rate
            inv.tax_amount = round(inv.subtotal * inv.tax_rate / 100, 2)
            fields_found += 1

        # Total amount - try Grand Total first, then Total (avoid Sub Total)
        total_m = re.search(
            r"Grand\s+Total[:\s]+(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
            text,
            re.IGNORECASE,
        )
        if not total_m:
            # Match Total that is NOT preceded by "Sub" (lookbehind)
            total_m = re.search(
                r"(?<!Sub\s)(?<!Sub-)Total[:\s]+(?:PKR|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
                text,
                re.IGNORECASE,
            )
        if total_m:
            inv.total = float(total_m.group(1).replace(",", ""))
            fields_found += 1

        # Sales tax (same as tax)
        inv.sales_tax = inv.tax_amount

        # Determine type
        if "purchase" in text.lower() or "vendor" in text.lower():
            inv.invoice_type = "purchase"
        elif "service" in text.lower():
            inv.invoice_type = "service"
        else:
            inv.invoice_type = "sales"

        # Quality
        inv.extraction_quality = round(fields_found / total_fields, 2)

        if not fields_found:
            inv.notes.append("No invoice fields detected - check format")

        return inv

    @staticmethod
    def extract_line_items(text: str) -> list[LineItem]:
        """Extract line items from invoice text."""
        items = []
        # Look for lines with description, quantity, price pattern
        item_pattern = re.compile(
            r"([A-Za-z][A-Za-z0-9\s&\.,-]{5,50}?)\s+(\d+(?:\.\d+)?)\s+([\d,]+(?:\.\d{1,2})?)\s+([\d,]+(?:\.\d{1,2})?)"
        )

        for match in item_pattern.finditer(text):
            desc, qty, price, total = match.groups()
            try:
                item = LineItem(
                    description=desc.strip(),
                    quantity=float(qty),
                    unit_price=float(price.replace(",", "")),
                    amount=float(total.replace(",", "")),
                )
                items.append(item)
            except (ValueError, AttributeError):
                continue

        return items
