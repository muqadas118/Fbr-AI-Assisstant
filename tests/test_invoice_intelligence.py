"""
Test Suite for Invoice Intelligence
====================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.invoice_intelligence import (
    InvoiceExtractor, ExtractedInvoice,
    InvoiceValidator, ValidationResult,
    InvoiceMatcher, MatchResult,
    InvoiceReconciler, ReconciliationReport,
    InvoiceAnalyzer, get_invoice_analyzer,
    InvoiceAPI, get_invoice_api,
)


class TestInvoiceExtractor(unittest.TestCase):
    """Test invoice extractor."""

    def test_extract_sales_invoice(self):
        text = """
        Sales Invoice
        Invoice No: INV-2024-001
        Invoice Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: PKR 100,000
        GST @ 18%
        Tax Amount: PKR 18,000
        Grand Total: 118,000
        """
        inv = InvoiceExtractor.extract(text)
        self.assertEqual(inv.invoice_number, "INV-2024-001")
        self.assertEqual(inv.seller_ntn, "1234567-8")
        self.assertEqual(inv.buyer_ntn, "8765432-1")
        self.assertEqual(inv.subtotal, 100000.0)
        self.assertEqual(inv.tax_rate, 18.0)
        self.assertEqual(inv.total, 118000.0)

    def test_extract_purchase_invoice(self):
        text = "Purchase Invoice\nVendor: ABC\nInvoice No: PI-001\nTotal: PKR 50,000"
        inv = InvoiceExtractor.extract(text)
        self.assertEqual(inv.invoice_type, "purchase")

    def test_extract_line_items(self):
        text = """
        Item Description       Qty   Price   Total
        Widget Type A         10    1000    10000
        Service Type B        5     2000    10000
        """
        items = InvoiceExtractor.extract_line_items(text)
        self.assertGreater(len(items), 0)


class TestInvoiceValidator(unittest.TestCase):
    """Test invoice validator."""

    def test_valid_invoice(self):
        inv = ExtractedInvoice(
            invoice_id="1",
            invoice_number="INV-001",
            invoice_date="15-03-2024",
            seller_ntn="1234567-8",
            buyer_ntn="8765432-1",
            subtotal=100000,
            tax_rate=18,
            tax_amount=18000,
            total=118000,
        )
        result = InvoiceValidator.validate(inv)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors_count, 0)

    def test_missing_required_fields(self):
        inv = ExtractedInvoice()
        result = InvoiceValidator.validate(inv)
        self.assertFalse(result.is_valid)
        self.assertGreater(result.errors_count, 0)

    def test_invalid_ntn(self):
        inv = ExtractedInvoice(
            invoice_number="INV-001",
            invoice_date="15-03-2024",
            seller_ntn="invalid",
            buyer_ntn="1234567-8",
            total=1000,
        )
        result = InvoiceValidator.validate(inv)
        self.assertFalse(result.is_valid)

    def test_tax_calculation_mismatch(self):
        inv = ExtractedInvoice(
            invoice_number="INV-001",
            invoice_date="15-03-2024",
            seller_ntn="1234567-8",
            buyer_ntn="8765432-1",
            subtotal=100000,
            tax_rate=18,
            tax_amount=9999,  # Should be 18000
            total=100000,
        )
        result = InvoiceValidator.validate(inv)
        self.assertGreater(result.warnings_count, 0)


class TestInvoiceMatcher(unittest.TestCase):
    """Test invoice matcher."""

    def test_find_duplicate(self):
        inv1 = ExtractedInvoice(
            invoice_id="1",
            invoice_number="INV-001",
            seller_ntn="1234567-8",
            total=100000,
        )
        inv2 = ExtractedInvoice(
            invoice_id="2",
            invoice_number="INV-001",
            seller_ntn="1234567-8",
            total=100000,
        )
        match = InvoiceMatcher.find_duplicate(inv1, [inv2])
        self.assertIsNotNone(match)
        self.assertTrue(match.is_match)

    def test_no_duplicate(self):
        inv1 = ExtractedInvoice(
            invoice_id="1",
            invoice_number="INV-001",
            seller_ntn="1234567-8",
            total=100000,
        )
        inv2 = ExtractedInvoice(
            invoice_id="2",
            invoice_number="INV-002",
            seller_ntn="1234567-8",
            total=200000,
        )
        match = InvoiceMatcher.find_duplicate(inv1, [inv2])
        self.assertIsNone(match)

    def test_match_purchase_to_sales(self):
        purchase = ExtractedInvoice(
            invoice_id="1",
            invoice_type="purchase",
            buyer_ntn="8765432-1",
            seller_ntn="1234567-8",
            invoice_number="INV-001",
            invoice_date="15-03-2024",
            total=118000,
        )
        sales = ExtractedInvoice(
            invoice_id="2",
            invoice_type="sales",
            seller_ntn="8765432-1",
            invoice_number="INV-001",
            invoice_date="15-03-2024",
            total=118000,
        )
        match = InvoiceMatcher.match_purchase_to_sales(purchase, sales)
        self.assertTrue(match.is_match)
        self.assertGreater(match.confidence, 0.8)


class TestInvoiceReconciler(unittest.TestCase):
    """Test invoice reconciler."""

    def test_basic_reconciliation(self):
        purchases = [
            ExtractedInvoice(
                invoice_id="p1",
                invoice_type="purchase",
                seller_ntn="1234567-8",
                seller_name="ABC Vendor",
                total=100000,
                tax_amount=18000,
            ),
        ]
        sales = [
            ExtractedInvoice(
                invoice_id="s1",
                invoice_type="sales",
                total=200000,
                tax_amount=36000,
            ),
        ]
        report = InvoiceReconciler.reconcile(purchases, sales)
        self.assertEqual(report.total_sales, 200000)
        self.assertEqual(report.total_purchases, 100000)
        self.assertEqual(report.total_output_tax, 36000)
        self.assertEqual(report.total_input_tax, 18000)
        self.assertEqual(report.net_payable, 18000)
        self.assertEqual(len(report.vendor_summaries), 1)


class TestInvoiceAnalyzer(unittest.TestCase):
    """Test unified analyzer."""

    def setUp(self):
        self.analyzer = get_invoice_analyzer()

    def test_analyze_valid_invoice(self):
        text = """
        Sales Invoice INV-001
        Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: 100000
        GST 18%
        Tax: 18000
        Total: 118000
        """
        result = self.analyzer.analyze(text)
        self.assertIsNotNone(result.analysis_id)
        self.assertGreater(result.validation.score, 0.5)

    def test_audit_log(self):
        self.analyzer.analyze("Invoice INV-001 Total PKR 100,000")
        self.assertGreater(len(self.analyzer.audit_log), 0)


class TestInvoiceAPI(unittest.TestCase):
    """Test invoice API."""

    def setUp(self):
        from app.invoice_intelligence.api import InvoiceAPI
        self.api = InvoiceAPI()

    def test_process_invoice(self):
        text = """
        Sales Invoice INV-001
        Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: 100000
        GST 18%
        Tax: 18000
        Total: 118000
        """
        result = self.api.process_invoice(text)
        self.assertIn("invoice", result)
        self.assertIn("validation", result)
        self.assertIn("summary", result)

    def test_dashboard_empty(self):
        dashboard = self.api.get_dashboard()
        self.assertEqual(dashboard["total_invoices"], 0)

    def test_dashboard_with_data(self):
        text = """
        Sales Invoice INV-001
        Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: 100000
        GST 18%
        Tax: 18000
        Total: 118000
        """
        self.api.process_invoice(text)
        dashboard = self.api.get_dashboard()
        self.assertGreaterEqual(dashboard["total_invoices"], 1)

    def test_export_json(self):
        text = """
        Sales Invoice INV-001
        Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: 100000
        GST 18%
        Tax: 18000
        Total: 118000
        """
        self.api.process_invoice(text)
        exported = self.api.export_invoices(format="json")
        self.assertIn("INV-001", exported)

    def test_export_csv(self):
        text = """
        Sales Invoice INV-001
        Date: 15-03-2024
        NTN: 1234567-8
        NTN: 8765432-1
        Subtotal: 100000
        GST 18%
        Tax: 18000
        Total: 118000
        """
        self.api.process_invoice(text)
        exported = self.api.export_invoices(format="csv")
        self.assertIn("INV-001", exported)


if __name__ == "__main__":
    unittest.main(verbosity=2)
