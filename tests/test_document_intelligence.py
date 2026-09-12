"""
Test Suite for Document Intelligence
=====================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.document_intelligence import (
    DocumentClassifier, DocumentType, DocumentCategory, ClassificationResult,
    DocumentExtractor, ExtractedDocument,
    OCREngine, OCREngineType, OCRResult, TextBlock,
    FormParser, ParsedForm, FormType,
    DocumentAnalyzer, get_document_analyzer,
    DocumentStore, StoredDocument, get_document_store,
)


class TestDocumentClassifier(unittest.TestCase):
    """Test document classifier."""

    def test_classify_invoice(self):
        text = "Sales Invoice\nInvoice Number: INV-001\nBuyer: ABC Corp\nGST 18%"
        result = DocumentClassifier.classify(text)
        self.assertEqual(result.document_type, DocumentType.SALES_INVOICE)
        self.assertGreater(result.confidence, 0.3)

    def test_classify_bank_statement(self):
        text = "Bank Statement\nAccount Number: 1234567890\nOpening Balance\nClosing Balance"
        result = DocumentClassifier.classify(text)
        self.assertEqual(result.document_type, DocumentType.BANK_STATEMENT)

    def test_classify_form_16a(self):
        text = "Form 16A\nCertificate of Salary\nTax Year 2024\nGross Salary: PKR 1,200,000"
        result = DocumentClassifier.classify(text)
        self.assertEqual(result.document_type, DocumentType.FORM_16A)

    def test_classify_form_16b(self):
        text = "Form 16B\nWithholding Tax Certificate\nSection 149\nTax Deducted: PKR 50,000"
        result = DocumentClassifier.classify(text)
        self.assertEqual(result.document_type, DocumentType.FORM_16B)

    def test_classify_fbr_notice(self):
        text = "Show Cause Notice under Section 114 of the Income Tax Ordinance 2001"
        result = DocumentClassifier.classify(text)
        self.assertEqual(result.document_type, DocumentType.FBR_NOTICE)

    def test_classify_empty(self):
        result = DocumentClassifier.classify("")
        self.assertEqual(result.document_type, DocumentType.UNKNOWN)

    def test_classify_by_filename(self):
        result = DocumentClassifier.classify_by_filename("invoice_2024.pdf")
        self.assertEqual(result, DocumentType.SALES_INVOICE)


class TestDocumentExtractor(unittest.TestCase):
    """Test document extractor."""

    def test_extract_ntn(self):
        text = "NTN: 1234567-8"
        doc = DocumentExtractor.extract(text, "sales_invoice")
        self.assertEqual(doc.person_ntn, "1234567-8")

    def test_extract_cnic(self):
        text = "CNIC: 12345-1234567-1"
        doc = DocumentExtractor.extract(text, "form_16a")
        self.assertEqual(doc.person_cnic, "12345-1234567-1")

    def test_extract_amount(self):
        text = "Total: PKR 150,000"
        doc = DocumentExtractor.extract(text, "sales_invoice")
        self.assertEqual(doc.total_amount, 150000)

    def test_extract_invoice_specific(self):
        text = """
        Sales Invoice
        GST 18%
        Quantity: 10
        Subtotal: PKR 50,000
        """
        doc = DocumentExtractor.extract(text, "sales_invoice")
        self.assertEqual(doc.tax_rate, 18.0)
        self.assertEqual(doc.fields.get("quantity"), 10)
        self.assertEqual(doc.fields.get("subtotal"), 50000.0)

    def test_extract_form_16a_specific(self):
        text = """
        Form 16A
        Tax Year: 2024
        Employer: ABC Ltd
        NTN: 1234567-8
        Employee: Ahmed Khan
        CNIC: 12345-1234567-1
        Gross Salary: PKR 1,200,000
        Net Salary: PKR 950,000
        Tax Deducted: PKR 100,000
        """
        doc = DocumentExtractor.extract(text, "form_16a")
        self.assertEqual(doc.fields.get("gross_salary"), 1200000)
        self.assertEqual(doc.fields.get("net_salary"), 950000)
        self.assertEqual(doc.fields.get("tax_deducted"), 100000)

    def test_extract_empty(self):
        doc = DocumentExtractor.extract("", "unknown")
        self.assertEqual(doc.extraction_quality, 0.0)


class TestOCREngine(unittest.TestCase):
    """Test OCR engine."""

    def setUp(self):
        self.engine = OCREngine(OCREngineType.SIMULATED)

    def test_extract_text(self):
        result = self.engine.extract_text(b"fake image data")
        self.assertIsInstance(result, OCRResult)
        self.assertEqual(result.engine_used, "simulated")

    def test_extract_from_pdf(self):
        result = self.engine.extract_from_pdf(b"fake pdf data")
        self.assertIsInstance(result, OCRResult)

    def test_detect_language(self):
        self.assertEqual(self.engine.detect_language("Hello World"), "eng")
        self.assertEqual(self.engine.detect_language("ہیلو ورلڈ"), "urd")


class TestFormParser(unittest.TestCase):
    """Test form parser."""

    def test_parse_form_16a(self):
        text = """
        Form 16A
        Tax Year: 2024
        Employer: ABC Ltd
        NTN: 1234567-8
        Employee: Ahmed Khan
        CNIC: 12345-1234567-1
        Gross Salary: PKR 1,200,000
        Taxable Salary: PKR 1,000,000
        Tax Paid: PKR 100,000
        """
        form = FormParser.parse(text, FormType.FORM_16A)
        self.assertEqual(form.form_number, "16A")
        self.assertEqual(form.tax_year, "2024")
        self.assertIn("name", form.employer_info)
        self.assertEqual(form.salary_details.get("gross_salary"), 1200000)

    def test_parse_form_16b(self):
        text = """
        Form 16B
        Tax Year: 2024
        Withholder: ABC Company
        Recipient: John Doe
        Section: 149
        Amount Paid: PKR 500,000
        Tax Deducted: PKR 7,500
        """
        form = FormParser.parse(text, FormType.FORM_16B)
        self.assertEqual(form.form_number, "16B")
        self.assertEqual(form.wht_details.get("section"), "149")
        self.assertEqual(form.wht_details.get("tax_deducted"), 7500)

    def test_parse_wealth_statement(self):
        text = """
        Wealth Statement
        Tax Year: 2024
        Total Assets: PKR 10,000,000
        Total Liabilities: PKR 3,000,000
        Net Wealth: PKR 7,000,000
        """
        form = FormParser.parse(text, FormType.WEALTH_STATEMENT)
        self.assertEqual(form.income_details.get("total_assets"), 10000000)
        self.assertEqual(form.income_details.get("net_wealth"), 7000000)


class TestDocumentAnalyzer(unittest.TestCase):
    """Test unified document analyzer."""

    def setUp(self):
        self.analyzer = get_document_analyzer()

    def test_complete_analysis(self):
        text = """
        Form 16A
        Tax Year: 2024
        Employer: ABC Company
        NTN: 1234567-8
        Employee: Ahmed Khan
        CNIC: 12345-1234567-1
        Gross Salary: PKR 1,200,000
        """
        result = self.analyzer.analyze(text, filename="form_16a_2024.pdf")
        self.assertEqual(result.document_type, "form_16a")
        self.assertIsNotNone(result.parsed_form)
        self.assertGreater(len(result.formatted_text), 0)
        self.assertGreater(result.overall_quality_score, 0)

    def test_analyze_invoice(self):
        text = "Sales Invoice INV-001 GST 18% Total: PKR 50,000"
        result = self.analyzer.analyze(text)
        self.assertEqual(result.document_type, "sales_invoice")

    def test_audit_log(self):
        self.analyzer.analyze("Test document")
        self.analyzer.analyze("Another document")
        self.assertGreaterEqual(len(self.analyzer.audit_log), 2)


class TestDocumentStore(unittest.TestCase):
    """Test document store."""

    def setUp(self):
        # Create fresh store for each test
        from app.document_intelligence.storage import DocumentStore
        self.store = DocumentStore()

    def test_store_document(self):
        doc = self.store.store(
            user_id="user1",
            filename="test.pdf",
            file_size=1024,
            file_type="pdf",
            content_hash="abc123",
            document_type="sales_invoice",
        )
        self.assertIsNotNone(doc.id)
        self.assertEqual(doc.user_id, "user1")

    def test_get_document(self):
        doc = self.store.store("user1", "test.pdf", 1024, "pdf", "hash")
        retrieved = self.store.get(doc.id)
        self.assertEqual(retrieved.id, doc.id)
        self.assertEqual(retrieved.access_count, 1)

    def test_search_by_user(self):
        self.store.store("user1", "doc1.pdf", 1024, "pdf", "h1")
        self.store.store("user1", "doc2.pdf", 1024, "pdf", "h2")
        self.store.store("user2", "doc3.pdf", 1024, "pdf", "h3")

        user1_docs = self.store.get_by_user("user1")
        self.assertEqual(len(user1_docs), 2)

    def test_search_by_type(self):
        self.store.store("u1", "inv.pdf", 1024, "pdf", "h", document_type="sales_invoice")
        invoices = self.store.get_by_type("sales_invoice")
        self.assertEqual(len(invoices), 1)

    def test_search_with_filters(self):
        self.store.store("u1", "inv.pdf", 1024, "pdf", "h", document_type="sales_invoice", amount=100000)
        results = self.store.search(user_id="u1", min_amount=50000)
        self.assertEqual(len(results), 1)

    def test_delete_document(self):
        doc = self.store.store("u1", "test.pdf", 1024, "pdf", "h")
        success = self.store.delete(doc.id)
        self.assertTrue(success)
        self.assertIsNone(self.store.get(doc.id))

    def test_get_stats(self):
        self.store.store("u1", "doc.pdf", 1024, "pdf", "h", amount=100000)
        stats = self.store.get_stats("u1")
        self.assertEqual(stats["total_documents"], 1)
        self.assertEqual(stats["total_value"], 100000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
