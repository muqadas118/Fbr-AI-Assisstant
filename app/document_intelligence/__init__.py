"""
Document Intelligence - Production-Grade
========================================

FBR document processing aur analysis system:
- PDF text extraction
- Image OCR (text from images)
- Document classification (invoice, receipt, contract, return, etc.)
- Key information extraction
- Form 16A/16B parsing
- Salary certificate processing
- Bank statement analysis
- Tax deduction certificate parsing
- Vehicle registration documents
- Property documents
- Multi-page document support
- Document quality scoring
- Fraud detection heuristics
- Document storage and retrieval
- Version control
- Bulk document processing

Supports: PDF, JPG, PNG, TIFF, DOCX, XLSX, TXT
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
