"""
Document Intelligence Router
============================

FastAPI router for document analysis operations.
Exposes DocumentAnalyzer as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.document_intelligence import get_document_analyzer

logger = logging.getLogger("fbr_api.documents")

router = APIRouter(prefix="/documents", tags=["Document Intelligence"])


# =============================================================================
# Request Models
# =============================================================================

class DocumentAnalysisRequest(BaseModel):
    """Request to analyze a document."""
    text: str = Field(
        ...,
        min_length=5,
        max_length=500000,
        description="Document text (extracted from PDF/image, or typed)"
    )
    filename: Optional[str] = Field(
        default=None,
        description="Original filename (helps with classification)"
    )
    document_type_hint: Optional[str] = Field(
        default=None,
        description="Hint about document type (e.g. 'invoice', 'form', 'contract')"
    )


# =============================================================================
# Response Models
# =============================================================================

class ExtractedInfoResponse(BaseModel):
    """Extracted document information."""
    person_name: Optional[str] = None
    person_cnic: Optional[str] = None
    person_ntn: Optional[str] = None
    company_name: Optional[str] = None
    company_ntn: Optional[str] = None
    reference_number: Optional[str] = None
    issue_date: Optional[str] = None
    total_amount: Optional[float] = None
    net_amount: Optional[float] = None
    currency: str = "PKR"
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_section: Optional[str] = None
    fbr_reference: Optional[str] = None
    address: Optional[str] = None
    extraction_quality: float


class ParsedFormResponse(BaseModel):
    """Parsed form data."""
    form_type: str
    form_number: Optional[str] = None
    tax_year: Optional[str] = None
    employer_info: dict
    employee_info: dict
    salary_details: dict
    tax_details: dict
    wht_details: dict
    income_details: dict
    deductions: dict
    fields_extracted: int
    total_fields: int
    extraction_rate: float
    notes: list[str]


class DocumentAnalysisResponse(BaseModel):
    """Complete document analysis response."""
    analysis_id: str
    timestamp: str
    duration_ms: float

    # Classification
    document_type: str
    document_category: str
    classification_confidence: float
    matched_signals: list[str]

    # Extraction
    extracted_info: ExtractedInfoResponse

    # Parsing
    parsed_form: Optional[ParsedFormResponse] = None

    # Quality
    overall_quality_score: float
    is_readable: bool
    needs_ocr: bool

    # Text
    formatted_text: str
    summary: str

    # OCR provenance (simulated vs real tesseract)
    ocr_simulated: bool = False
    ocr_warning: Optional[str] = None


class DocumentVerifyRequest(BaseModel):
    """Request to verify NTN/CNIC from document."""
    text: str = Field(..., min_length=5, max_length=500000)


class DocumentVerifyResponse(BaseModel):
    """Document verification result."""
    ntn: Optional[str] = None
    cnic: Optional[str] = None
    name: Optional[str] = None
    confidence: float
    extraction_quality: float


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/analyze", response_model=DocumentAnalysisResponse, dependencies=[Depends(require_user)])
async def analyze_document(request: DocumentAnalysisRequest) -> DocumentAnalysisResponse:
    """
    Analyze a document (PDF, image, or text).

    Classifies the document type, extracts structured information,
    and parses form data if applicable. Supports:
    - Invoices (sales, purchase, credit/debit)
    - Tax forms (Form 16A, 16B, salary certificates)
    - Contracts and agreements
    - Receipts
    - Bank statements
    - FBR correspondence
    """
    try:
        analyzer = get_document_analyzer()
        result = analyzer.analyze(
            text=request.text,
            filename=request.filename,
            is_image=False,
        )

        return DocumentAnalysisResponse(
            analysis_id=result.analysis_id,
            timestamp=result.timestamp,
            duration_ms=result.duration_ms,
            document_type=result.document_type,
            document_category=result.document_category,
            classification_confidence=result.classification_confidence,
            matched_signals=result.matched_signals,
            extracted_info=ExtractedInfoResponse(
                person_name=result.extracted_info.person_name,
                person_cnic=result.extracted_info.person_cnic,
                person_ntn=result.extracted_info.person_ntn,
                company_name=result.extracted_info.company_name,
                company_ntn=result.extracted_info.company_ntn,
                reference_number=result.extracted_info.reference_number,
                issue_date=result.extracted_info.issue_date,
                total_amount=result.extracted_info.total_amount,
                net_amount=result.extracted_info.net_amount,
                currency=getattr(result.extracted_info, 'currency', 'PKR'),
                tax_rate=result.extracted_info.tax_rate,
                tax_amount=result.extracted_info.tax_amount,
                tax_section=getattr(result.extracted_info, 'tax_section', None),
                fbr_reference=getattr(result.extracted_info, 'fbr_reference', None),
                address=getattr(result.extracted_info, 'address', None),
                extraction_quality=result.extracted_info.extraction_quality,
            ),
            parsed_form=ParsedFormResponse(
                form_type=result.parsed_form.form_type.value if result.parsed_form and hasattr(result.parsed_form.form_type, 'value') else str(result.parsed_form.form_type) if result.parsed_form else "unknown",
                form_number=result.parsed_form.form_number if result.parsed_form else None,
                tax_year=result.parsed_form.tax_year if result.parsed_form else None,
                employer_info=getattr(result.parsed_form, 'employer_info', {}) or {} if result.parsed_form else {},
                employee_info=getattr(result.parsed_form, 'employee_info', {}) or {} if result.parsed_form else {},
                salary_details=getattr(result.parsed_form, 'salary_details', {}) or {} if result.parsed_form else {},
                tax_details=getattr(result.parsed_form, 'tax_details', {}) or {} if result.parsed_form else {},
                wht_details=getattr(result.parsed_form, 'wht_details', {}) or {} if result.parsed_form else {},
                income_details=getattr(result.parsed_form, 'income_details', {}) or {} if result.parsed_form else {},
                deductions=getattr(result.parsed_form, 'deductions', {}) or {} if result.parsed_form else {},
                fields_extracted=result.parsed_form.fields_extracted if result.parsed_form else 0,
                total_fields=result.parsed_form.total_fields if result.parsed_form else 0,
                extraction_rate=result.parsed_form.extraction_rate if result.parsed_form else 0.0,
                notes=getattr(result.parsed_form, 'notes', []) or [] if result.parsed_form else [],
            ) if result.parsed_form else None,
            overall_quality_score=result.overall_quality_score,
            is_readable=result.is_readable,
            needs_ocr=result.needs_ocr,
            formatted_text=result.formatted_text,
            summary=result.summary,
            ocr_simulated=getattr(result, "ocr_simulated", False) or "OCR simulated" in request.text,
            ocr_warning=getattr(result, "ocr_warning", None),
        )
    except Exception:
        logger.exception("Error analyzing document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze document"
        )


@router.post("/verify", response_model=DocumentVerifyResponse, dependencies=[Depends(require_user)])
async def verify_document_identity(request: DocumentVerifyRequest) -> DocumentVerifyResponse:
    """
    Verify NTN/CNIC from a document.

    Extracts and validates taxpayer identification from any document.
    Useful for verifying identity on uploaded documents.
    """
    try:
        analyzer = get_document_analyzer()
        result = analyzer.analyze(text=request.text, filename="verify")

        return DocumentVerifyResponse(
            ntn=result.extracted_info.person_ntn,
            cnic=result.extracted_info.person_cnic,
            name=result.extracted_info.person_name,
            confidence=result.classification_confidence,
            extraction_quality=result.extracted_info.extraction_quality,
        )
    except Exception:
        logger.exception("Error verifying document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify document"
        )


# PUBLIC - intentionally no auth: static metadata for UI
@router.get("/types")
async def get_document_types() -> dict:
    """
    List all supported document types.

    Returns all document types the classifier can recognize.
    """
    try:
        from app.document_intelligence.classifier import DocumentType, DocumentCategory
        return {
            "document_types": [dt.value for dt in DocumentType],
            "categories": [dc.value for dc in DocumentCategory],
        }
    except Exception:
        logger.exception("Error listing document types")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document types"
        )
