"""
Document Analyzer - Unified Engine
=================================

Combines classification, extraction, and parsing into one workflow.
"""

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.document_intelligence.classifier import (
    DocumentClassifier, DocumentType, ClassificationResult,
)
from app.document_intelligence.extractor import DocumentExtractor, ExtractedDocument
from app.document_intelligence.ocr import OCREngine
from app.document_intelligence.parser import FormParser, ParsedForm, FormType

logger = logging.getLogger("document_intelligence")

# Audit log is capped so the long-lived analyzer singleton cannot grow forever
AUDIT_LOG_MAX_ENTRIES = 1000


@dataclass
class DocumentAnalysis:
    """Complete document analysis result."""
    analysis_id: str
    timestamp: str
    duration_ms: float

    # Classification
    document_type: str
    document_category: str
    classification_confidence: float

    # Extraction
    extracted_info: ExtractedDocument

    # Parsing (if applicable)
    parsed_form: Optional[ParsedForm] = None

    matched_signals: list[str] = field(default_factory=list)

    # Quality
    overall_quality_score: float = 0.0
    is_readable: bool = True
    needs_ocr: bool = False

    # Formatted output
    formatted_text: str = ""
    summary: str = ""
    ocr_simulated: bool = False
    ocr_warning: Optional[str] = None


class DocumentAnalyzer:
    """
    Unified document analysis engine.

    Workflow:
    1. Take document (text, PDF bytes, or image bytes)
    2. Classify document type
    3. Extract structured information
    4. Parse as form (if applicable)
    5. Return comprehensive analysis
    """

    def __init__(self):
        self.classifier = DocumentClassifier()
        self.extractor = DocumentExtractor()
        self.ocr_engine = OCREngine()
        self.form_parser = FormParser()
        self.audit_log: deque[dict] = deque(maxlen=AUDIT_LOG_MAX_ENTRIES)

    def analyze(
        self,
        text: str,
        filename: Optional[str] = None,
        is_image: bool = False,
    ) -> DocumentAnalysis:
        """Analyze a document."""
        start_time = time.time()
        analysis_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Step 1: Classify
        classification = self.classifier.classify(text, filename)

        # Step 2: Extract info
        extracted = self.extractor.extract(text, classification.document_type.value)

        # Step 3: Parse as form
        parsed_form = None
        if classification.document_type in {
            DocumentType.FORM_16A,
            DocumentType.FORM_16B,
            DocumentType.SALARY_CERTIFICATE,
        }:
            form_type_map = {
                DocumentType.FORM_16A: FormType.FORM_16A,
                DocumentType.FORM_16B: FormType.FORM_16B,
                # A salary certificate is not a Form 16A: parsing it as one
                # invents 16A-only fields and inflates fields_extracted.
                DocumentType.SALARY_CERTIFICATE: FormType.GENERIC,
            }
            parsed_form = self.form_parser.parse(
                text,
                form_type_map.get(classification.document_type, FormType.GENERIC)
            )

        # Step 4: Calculate overall quality
        quality = self._calculate_quality(classification, extracted, parsed_form)

        # Step 5: Format output
        formatted = self._format_analysis(
            classification, extracted, parsed_form, quality
        )
        summary = self._build_summary(classification, extracted, quality)

        duration_ms = (time.time() - start_time) * 1000

        # Flag simulated-OCR input so POST /documents/analyze can surface it.
        ocr_simulated = "OCR simulated" in text
        ocr_warning = (
            "Scanned PDF - OCR simulated, install tesseract for real text"
            if ocr_simulated else None
        )

        # Log to audit
        self.audit_log.append({
            "analysis_id": analysis_id,
            "timestamp": timestamp,
            "doc_type": classification.document_type.value,
            "confidence": classification.confidence,
            "duration_ms": round(duration_ms, 3),
        })

        return DocumentAnalysis(
            analysis_id=analysis_id,
            timestamp=timestamp,
            duration_ms=round(duration_ms, 3),
            document_type=classification.document_type.value,
            document_category=classification.category.value,
            classification_confidence=classification.confidence,
            matched_signals=classification.matched_signals,
            extracted_info=extracted,
            parsed_form=parsed_form,
            overall_quality_score=quality,
            is_readable=len(text.strip()) > 50,
            needs_ocr=is_image and len(text.strip()) < 50,
            formatted_text=formatted,
            summary=summary,
            ocr_simulated=ocr_simulated,
            ocr_warning=ocr_warning,
        )

    def analyze_from_pdf(self, pdf_data: bytes, filename: str = "document.pdf") -> DocumentAnalysis:
        """Analyze PDF document (text layer, then OCR when an engine is installed)."""
        ocr_result = self.ocr_engine.extract_from_pdf(pdf_data)
        analysis = self.analyze(
            ocr_result.full_text,
            filename=filename,
            is_image=False,
        )
        # Report the real OCR outcome, never an assumed one.
        analysis.ocr_simulated = ocr_result.ocr_simulated
        analysis.ocr_warning = ocr_result.warning
        analysis.needs_ocr = analysis.needs_ocr or not ocr_result.full_text.strip()
        return analysis

    def analyze_from_image(self, image_data: bytes, filename: str = "image.jpg") -> DocumentAnalysis:
        """Analyze image document (requires OCR)."""
        ocr_result = self.ocr_engine.extract_text(image_data)
        analysis = self.analyze(
            ocr_result.full_text,
            filename=filename,
            is_image=True,
        )
        # Report the real OCR outcome, never an assumed one.
        analysis.ocr_simulated = ocr_result.ocr_simulated
        analysis.ocr_warning = ocr_result.warning
        analysis.needs_ocr = analysis.needs_ocr or not ocr_result.full_text.strip()
        return analysis

    def _calculate_quality(
        self,
        classification: ClassificationResult,
        extracted: ExtractedDocument,
        parsed_form: Optional[ParsedForm],
    ) -> float:
        """Calculate overall document quality score."""
        scores = [
            classification.confidence * 0.3,
            extracted.extraction_quality * 0.4,
        ]
        if parsed_form:
            scores.append(parsed_form.extraction_rate * 0.3)
        return round(sum(scores), 2)

    def _format_analysis(
        self,
        classification: ClassificationResult,
        extracted: ExtractedDocument,
        parsed_form: Optional[ParsedForm],
        quality: float,
    ) -> str:
        """Format analysis as readable text."""
        lines = [
            "=" * 60,
            "DOCUMENT ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Document Type: {classification.document_type.value}",
            f"Category: {classification.category.value}",
            f"Confidence: {int(classification.confidence * 100)}%",
            f"Quality Score: {int(quality * 100)}%",
            "",
        ]

        if classification.matched_signals:
            lines.append("Matched Signals:")
            for sig in classification.matched_signals[:5]:
                lines.append(f"  • {sig}")
            lines.append("")

        lines.append("--- Extracted Information ---")
        if extracted.person_ntn:
            lines.append(f"  NTN: {extracted.person_ntn}")
        if extracted.person_cnic:
            lines.append(f"  CNIC: {extracted.person_cnic}")
        if extracted.reference_number:
            lines.append(f"  Reference: {extracted.reference_number}")
        if extracted.issue_date:
            lines.append(f"  Date: {extracted.issue_date}")
        if extracted.total_amount:
            lines.append(f"  Amount: PKR {extracted.total_amount:,.2f}")
        if extracted.tax_rate:
            lines.append(f"  Tax Rate: {extracted.tax_rate}%")
        lines.append("")

        if parsed_form:
            lines.append("--- Form Data ---")
            if parsed_form.tax_year:
                lines.append(f"  Tax Year: {parsed_form.tax_year}")
            if parsed_form.employer_info:
                lines.append(f"  Employer: {parsed_form.employer_info.get('name', 'N/A')}")
            if parsed_form.employee_info:
                lines.append(f"  Employee: {parsed_form.employee_info.get('name', 'N/A')}")
            if parsed_form.salary_details:
                lines.append(f"  Gross Salary: PKR {parsed_form.salary_details.get('gross_salary', 0):,.0f}")
            lines.append("")

        lines.append(f"Extraction Quality: {int(extracted.extraction_quality * 100)}%")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _build_summary(
        self,
        classification: ClassificationResult,
        extracted: ExtractedDocument,
        quality: float,
    ) -> str:
        """Build concise summary."""
        parts = []

        parts.append(
            f"Document: {classification.document_type.value.replace('_', ' ').title()}"
        )

        if extracted.person_ntn:
            parts.append(f"NTN: {extracted.person_ntn}")
        if extracted.person_cnic:
            parts.append(f"CNIC: {extracted.person_cnic}")
        if extracted.total_amount:
            parts.append(f"PKR {extracted.total_amount:,.0f}")
        if extracted.issue_date:
            parts.append(f"Date: {extracted.issue_date}")

        parts.append(f"Confidence: {int(classification.confidence * 100)}%")

        return " | ".join(parts)


# Singleton
_analyzer: Optional[DocumentAnalyzer] = None


def get_document_analyzer() -> DocumentAnalyzer:
    """Get singleton document analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = DocumentAnalyzer()
    return _analyzer
