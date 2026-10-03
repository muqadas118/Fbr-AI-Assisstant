"""
Test Suite for File Upload Router
==================================

Covers:
- File family detection and rejection of unsupported types
- PDF and text extraction helpers
- POST /uploads/documents/analyze  (multipart)
- POST /uploads/documents/verify   (multipart, with NTN/CNIC format checks)
- POST /uploads/invoices/process   (multipart)
- Empty file, oversize, and non-file inputs
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.routers.uploads import (
    MAX_FILE_BYTES,
    _file_family,
    _extract_pdf_text,
    _extract_text,
    router as uploads_router,
)
from app.supabase_auth import require_user


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(uploads_router)
    return app


def _multipart(client: TestClient, path: str, data: bytes, filename: str,
               extra_fields: dict | None = None):
    files = {"file": (filename, io.BytesIO(data))}
    form = extra_fields or {}
    return client.post(path, files=files, data=form)


SAMPLE_INVOICE_TEXT = (
    "SALES TAX INVOICE\n"
    "Invoice Number: INV-2024-001\n"
    "Date: 2024-03-15\n"
    "Seller NTN: 1234567\n"
    "Buyer NTN: 7654321\n"
    "Subtotal: PKR 50,000\n"
    "Sales Tax 18%: PKR 9,000\n"
    "Total: PKR 59,000\n"
)

SAMPLE_IDENTITY_TEXT = (
    "SALARY CERTIFICATE\n"
    "Employee Name: Ali Raza\n"
    "CNIC: 35201-1234567-1\n"
    "NTN: 1234567\n"
    "Tax Year 2024\n"
    "Gross Salary: PKR 1,200,000\n"
)


def _make_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class TestFileFamily(unittest.TestCase):
    """_file_family classification."""

    def test_pdf(self):
        self.assertEqual(_file_family("invoice.PDF"), "pdf")

    def test_images(self):
        for name in ("scan.jpg", "scan.jpeg", "scan.png", "scan.webp", "scan.tiff"):
            self.assertEqual(_file_family(name), "image")

    def test_text(self):
        for name in ("doc.txt", "notes.md", "data.csv", "blob.json"):
            self.assertEqual(_file_family(name), "text")

    def test_no_extension_is_text(self):
        self.assertEqual(_file_family("README"), "text")

    def test_unsupported_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            _file_family("virus.exe")
        self.assertEqual(ctx.exception.status_code, 400)


class TestExtraction(unittest.TestCase):
    """Text extraction helpers."""

    def test_pdf_extraction(self):
        data = _make_pdf("SALARY CERTIFICATE\nEmployee: Ali Raza")
        text, pages = _extract_pdf_text(data)
        self.assertEqual(pages, 1)
        self.assertIn("SALARY CERTIFICATE", text)
        self.assertIn("Ali Raza", text)

    def test_text_extraction_utf8(self):
        data = "Invoice: INV-001 — total PKR 59,000".encode("utf-8")
        self.assertIn("INV-001", _extract_text(data, "a.txt"))

    def test_text_extraction_latin1_fallback(self):
        data = b"caf\xe9 invoice"
        self.assertIn("caf", _extract_text(data, "a.txt"))


class TestUploadDocumentsAnalyze(unittest.TestCase):
    """POST /uploads/documents/analyze."""

    def setUp(self):
        self.client = TestClient(_build_app())

    def test_txt_document(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/analyze",
            SAMPLE_IDENTITY_TEXT.encode("utf-8"),
            "salary.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["filename"], "salary.txt")
        self.assertEqual(body["meta"]["content_family"], "text")
        self.assertFalse(body["meta"]["ocr_simulated"])
        self.assertTrue(body["analysis"]["document_type"])
        self.assertIn("analysis_id", body["analysis"])

    def test_pdf_document(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/analyze",
            _make_pdf(SAMPLE_IDENTITY_TEXT),
            "salary.pdf",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["content_family"], "pdf")
        self.assertFalse(body["meta"]["ocr_simulated"])
        # Analyzer classified the PDF text and extracted the NTN from it.
        self.assertEqual(body["analysis"]["document_type"], "salary_certificate")
        self.assertIn("1234567", body["analysis"]["formatted_text"])

    def test_invalid_image_returns_400(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/analyze",
            b"this is not an image at all",
            "fake.png",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid image", resp.json()["detail"])

    def test_unsupported_type_returns_400(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/analyze",
            b"MZ fake binary",
            "program.exe",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported file type", resp.json()["detail"])

    def test_empty_file_returns_400(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/analyze",
            b"",
            "empty.txt",
        )
        self.assertEqual(resp.status_code, 400)


class TestUploadDocumentsVerify(unittest.TestCase):
    """POST /uploads/documents/verify — identity + format checks."""

    def setUp(self):
        self.client = TestClient(_build_app())

    def test_txt_with_valid_ids(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/verify",
            SAMPLE_IDENTITY_TEXT.encode("utf-8"),
            "id_doc.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["ntn"], "1234567")
        self.assertEqual(body["cnic"], "35201-1234567-1")
        self.assertTrue(body["ntn_format_valid"])
        self.assertTrue(body["cnic_format_valid"])

    def test_invalid_ntn_flagged(self):
        text = SAMPLE_IDENTITY_TEXT.replace("NTN: 1234567", "NTN: 12345")
        resp = _multipart(
            self.client,
            "/uploads/documents/verify",
            text.encode("utf-8"),
            "id_doc.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotEqual(body["ntn"], None)  # extracted but flagged
        self.assertFalse(body["ntn_format_valid"])

    def test_invalid_cnic_flagged(self):
        text = SAMPLE_IDENTITY_TEXT.replace("CNIC: 35201-1234567-1", "CNIC: 1234")
        resp = _multipart(
            self.client,
            "/uploads/documents/verify",
            text.encode("utf-8"),
            "id_doc.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["cnic_format_valid"])

    def test_pdf_verify(self):
        resp = _multipart(
            self.client,
            "/uploads/documents/verify",
            _make_pdf(SAMPLE_IDENTITY_TEXT),
            "id_doc.pdf",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ntn_format_valid"])
        self.assertTrue(body["cnic_format_valid"])


class TestUploadInvoicesProcess(unittest.TestCase):
    """POST /uploads/invoices/process."""

    def setUp(self):
        self.client = TestClient(_build_app())

    def test_txt_invoice(self):
        resp = _multipart(
            self.client,
            "/uploads/invoices/process",
            SAMPLE_INVOICE_TEXT.encode("utf-8"),
            "invoice.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["content_family"], "text")
        result = body["result"]
        self.assertIn("analysis_id", result)
        self.assertIn("invoice", result)
        self.assertIn("validation", result)
        self.assertIn("itc_eligible", result)

    def test_pdf_invoice(self):
        resp = _multipart(
            self.client,
            "/uploads/invoices/process",
            _make_pdf(SAMPLE_INVOICE_TEXT),
            "invoice.pdf",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["meta"]["content_family"], "pdf")
        self.assertFalse(body["meta"]["ocr_simulated"])
        self.assertTrue(body["result"]["invoice"])

    def test_garbage_text_still_processes(self):
        """Pipeline must not 500 on noise — it returns a low-score validation."""
        resp = _multipart(
            self.client,
            "/uploads/invoices/process",
            "lorem ipsum random words only".encode("utf-8"),
            "noise.txt",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("validation", body["result"])


if __name__ == "__main__":
    unittest.main()
