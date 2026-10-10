"""
Document Intelligence
=====================

Document classification, extraction and parsing for FBR workflows:
- Document classification (invoice, receipt, certificate, return, ...)
- Key information extraction (NTN, CNIC, dates, amounts, tax fields)
- Form 16A / 16B / wealth statement parsing
- Salary certificate, bank statement and tax return field extraction
- OCR via pytesseract + Tesseract when installed (simulation is opt-in
  only: OCREngineType.SIMULATED or FBR_OCR_SIMULATE=1)
- PDFs through OCREngine.extract_from_pdf use OCR-free text-layer
  extraction (PyMuPDF, pypdf fallback); scanned PDFs are OCR'd only
  when Tesseract is installed, otherwise reported as "no text extracted"
- In-memory document store (no persistence, versioning or bulk jobs)

Input is text, PDF bytes (OCREngine.extract_from_pdf) or image bytes
(OCREngine.extract_text).
"""

from app.document_intelligence.classifier import (
    DocumentClassifier, DocumentType, DocumentCategory,
    ClassificationResult,
)
from app.document_intelligence.extractor import (
    DocumentExtractor, ExtractedDocument, ExtractionField,
)
from app.document_intelligence.ocr import (
    OCREngine, OCRResult, TextBlock, OCREngineType,
)
from app.document_intelligence.parser import (
    FormParser, ParsedForm, FormType,
)
from app.document_intelligence.analyzer import (
    DocumentAnalyzer, DocumentAnalysis, get_document_analyzer,
)
from app.document_intelligence.storage import (
    DocumentStore, StoredDocument, get_document_store,
)

__all__ = [
    "DocumentClassifier",
    "DocumentType",
    "DocumentCategory",
    "ClassificationResult",
    "DocumentExtractor",
    "ExtractedDocument",
    "ExtractionField",
    "OCREngine",
    "OCRResult",
    "TextBlock",
    "OCREngineType",
    "FormParser",
    "ParsedForm",
    "FormType",
    "DocumentAnalyzer",
    "DocumentAnalysis",
    "get_document_analyzer",
    "DocumentStore",
    "StoredDocument",
    "get_document_store",
]
