"""
File Upload Router
==================

FastAPI router for file-based document, invoice, and verification flows.

Accepts real file uploads (multipart/form-data) for:
- PDF (text layer extracted with pymupdf; falls back to pypdf)
- Images (jpg/png/webp/bmp/tiff) — OCR'd with tesseract when installed,
  otherwise an explicit "simulated OCR" placeholder is returned so the UI
  can surface the provenance honestly
- Plain text / markdown / CSV — decoded directly

The extracted text is then routed through the existing, verified pipelines:
- /uploads/documents/analyze  -> DocumentAnalyzer.analyze
- /uploads/documents/verify   -> DocumentAnalyzer.analyze + format checks
- /uploads/invoices/process   -> InvoiceAPI.process_invoice
"""

import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.language import localize
from app.quotas import get_quota_store
from app.supabase_auth import require_user

logger = logging.getLogger("fbr_api.uploads")

router = APIRouter(prefix="/uploads", tags=["File Upload"])

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

# Extension -> (family, content-type prefix check)
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".rtf", ".json"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _file_family(filename: str) -> str:
    """Classify an uploaded filename into pdf | image | text (raises 400 otherwise)."""
    lower = (filename or "").lower()
    dot = lower.rfind(".")
    ext = lower[dot:] if dot != -1 else ""
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS or ext == "":
        return "text"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file type: {ext or '(no extension)'}. "
               f"Supported: PDF, images ({', '.join(sorted(IMAGE_EXTENSIONS))}), "
               f"text ({', '.join(sorted(TEXT_EXTENSIONS))}).",
    )


def _extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Extract text from a PDF using pymupdf, falling back to pypdf."""
    pages = 0
    text = ""
    try:
        import pymupdf  # type: ignore

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = doc.page_count
            text = "\n".join(page.get_text() for page in doc)
    except Exception as exc:  # noqa: BLE001 — fall through to pypdf
        logger.warning("pymupdf extraction failed (%s); trying pypdf", exc)
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(data))
            pages = len(reader.pages)
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc2:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not read PDF: {exc2}",
            ) from exc2
    return text.strip(), pages


def _extract_image_text(data: bytes, filename: str) -> tuple[str, Optional[str]]:
    """
    Extract text from an image. Uses tesseract when available; otherwise
    returns an explicit simulated-OCR placeholder (never silent garbage).
    """
    # Validate that the bytes really are an image before running OCR.
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {exc}",
        ) from exc

    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as img:
            text = pytesseract.image_to_string(img)
        return text.strip(), None
    except ImportError:
        logger.info("pytesseract not installed; using simulated OCR for %s", filename)
        return (
            "[OCR simulated - no text extracted] "
            "Scanned image - OCR simulated, install tesseract for real text",
            "Image OCR simulated — install tesseract (or use a PDF with a text "
            "layer) for real text extraction.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image OCR failed for %s: %s", filename, exc)
        return (
            "[OCR simulated - no text extracted] "
            f"Image OCR failed: {exc}",
            "Image OCR failed — the file was accepted, but no text could be extracted.",
        )


def _extract_text(data: bytes, filename: str) -> str:
    """Decode a text file, tolerating common encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Could not decode {filename} as text. Is it really a text file?",
    )


def _read_and_extract(
    file: UploadFile,
) -> tuple[str, str, Optional[str]]:
    """
    Read the uploaded file and extract text.

    Returns (text, family, ocr_warning).
    """
    filename = file.filename or "upload"
    family = _file_family(filename)

    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is larger than the 10 MB limit.",
        )

    ocr_warning: Optional[str] = None
    if family == "pdf":
        text, _pages = _extract_pdf_text(data)
        if not text:
            ocr_warning = (
                "PDF has no extractable text layer (likely scanned) — "
                "install tesseract for OCR, or use a text-based PDF."
            )
            text = "[OCR simulated - no text extracted] Scanned PDF - OCR simulated, install tesseract for real text"
    elif family == "image":
        text, ocr_warning = _extract_image_text(data, filename)
    else:
        text = _extract_text(data, filename)

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from the file.",
        )
    return text, family, ocr_warning


# =============================================================================
# Response models
# =============================================================================

class UploadMeta(BaseModel):
    """Provenance metadata about the uploaded file."""
    filename: str
    content_family: str  # pdf | image | text
    size_bytes: int
    pages: Optional[int] = None
    ocr_simulated: bool = False
    ocr_warning: Optional[str] = None


class UploadDocumentAnalysisResponse(BaseModel):
    """Document analysis of an uploaded file."""
    meta: UploadMeta
    analysis: dict


class UploadDocumentVerifyResponse(BaseModel):
    """Identity verification over an uploaded file."""
    meta: UploadMeta
    ntn: Optional[str] = None
    cnic: Optional[str] = None
    name: Optional[str] = None
    confidence: float
    extraction_quality: float
    ntn_format_valid: bool
    cnic_format_valid: bool


class UploadInvoiceProcessResponse(BaseModel):
    """Invoice processing over an uploaded file."""
    meta: UploadMeta
    result: dict


# =============================================================================
# Shared helper
# =============================================================================

def _analyze_uploaded_document(file: UploadFile, document_type_hint: Optional[str]):
    from app.document_intelligence import get_document_analyzer

    text, family, ocr_warning = _read_and_extract(file)
    analyzer = get_document_analyzer()
    analysis = analyzer.analyze(
        text,
        filename=file.filename,
        is_image=(family == "image"),
    )
    # The router layer (POST /documents/analyze) overrides these from the
    # request payload; here we know the real provenance from the file bytes.
    analysis.ocr_simulated = ocr_warning is not None or "OCR simulated" in text
    analysis.ocr_warning = ocr_warning
    return analysis, file.filename or "upload", family, ocr_warning


def _analysis_to_dict(analysis) -> dict:
    """Convert a DocumentAnalysis dataclass to a JSON-safe dict."""
    if hasattr(analysis, "to_dict"):
        return analysis.to_dict()
    import dataclasses

    return dataclasses.asdict(analysis)


def _format_invoice_result(result) -> dict:
    """Convert the InvoiceAPI.process_invoice dict into a JSON-safe payload."""
    out = dict(result)
    validation = dict(out.get("validation") or {})
    issues = []
    for issue in validation.get("issues") or []:
        if hasattr(issue, "__dict__"):
            issues.append(dict(issue.__dict__))
        else:
            issues.append(issue)
    validation["issues"] = issues
    out["validation"] = validation
    invoice = out.get("invoice")
    if invoice is not None and hasattr(invoice, "__dict__"):
        out["invoice"] = dict(invoice.__dict__)
    return out


def _ntn_format_valid(ntn: Optional[str]) -> bool:
    """NTN is 7 or 9 digits (individuals 7, companies 9)."""
    if not ntn:
        return False
    digits = ntn.replace("-", "").strip()
    return digits.isdigit() and len(digits) in (7, 9)


def _cnic_format_valid(cnic: Optional[str]) -> bool:
    """CNIC is 13 digits, conventionally 5-7-1 with dashes."""
    if not cnic:
        return False
    digits = cnic.replace("-", "").strip()
    return digits.isdigit() and len(digits) == 13


# Daily upload budget: PER ACCOUNT and intentionally shared across every page
# that accepts an uploaded file (documents/analyze, documents/verify,
# invoices/process and any future upload route) — one pool, so the cap cannot
# be sidestepped by hopping endpoints. Under FBR_AUTH_REQUIRED=false there is
# no caller, so calls meter against one shared "dev-user" scope (the same
# fallback /quota and vault use) rather than crashing on a None id.
_DEV_USER_SCOPE = "dev-user"


def _consume_upload_quota(user: Optional[dict]) -> None:
    """Charge one uploaded file against the caller's daily upload budget.

    Raises HTTPException 429 (localized) once the daily budget is exhausted.
    A no-op when quotas are globally disabled (the store reports allowed).
    """
    scope = _DEV_USER_SCOPE
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                scope = str(user[key])
                break
    snap = get_quota_store().consume_upload(scope)
    if not snap.allowed_upload:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=localize("quota_upload_exceeded", "en"),
        )


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/documents/analyze",
    response_model=UploadDocumentAnalysisResponse,
    dependencies=[Depends(require_user)],
)
async def upload_and_analyze_document(
    file: UploadFile = File(...),
    document_type_hint: Optional[str] = None,
    user: Optional[dict] = Depends(require_user),
) -> UploadDocumentAnalysisResponse:
    """
    Upload a document file (PDF, image, or text) and run the full
    document analysis pipeline on its extracted text.
    """
    try:
        _consume_upload_quota(user)
        analysis, filename, family, ocr_warning = _analyze_uploaded_document(
            file, document_type_hint
        )

        size = file.size if file.size is not None else None
        return UploadDocumentAnalysisResponse(
            meta=UploadMeta(
                filename=filename,
                content_family=family,
                size_bytes=size if size is not None else 0,
                ocr_simulated=analysis.ocr_simulated,
                ocr_warning=analysis.ocr_warning,
            ),
            analysis=_analysis_to_dict(analysis),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error analyzing uploaded document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze uploaded document",
        )


@router.post(
    "/documents/verify",
    response_model=UploadDocumentVerifyResponse,
    dependencies=[Depends(require_user)],
)
async def upload_and_verify_document(
    file: UploadFile = File(...),
    user: Optional[dict] = Depends(require_user),
) -> UploadDocumentVerifyResponse:
    """
    Upload a document file (PDF, image, or text) and verify the taxpayer
    identity (NTN/CNIC) it contains, including format validation.
    """
    try:
        _consume_upload_quota(user)
        analysis, filename, family, ocr_warning = _analyze_uploaded_document(file, None)
        ntn = analysis.extracted_info.person_ntn
        cnic = analysis.extracted_info.person_cnic
        return UploadDocumentVerifyResponse(
            meta=UploadMeta(
                filename=filename,
                content_family=family,
                size_bytes=file.size if file.size is not None else 0,
                ocr_simulated=analysis.ocr_simulated,
                ocr_warning=analysis.ocr_warning,
            ),
            ntn=ntn,
            cnic=cnic,
            name=analysis.extracted_info.person_name,
            confidence=analysis.classification_confidence,
            extraction_quality=analysis.extracted_info.extraction_quality,
            ntn_format_valid=_ntn_format_valid(ntn),
            cnic_format_valid=_cnic_format_valid(cnic),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error verifying uploaded document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify uploaded document",
        )


@router.post(
    "/invoices/process",
    response_model=UploadInvoiceProcessResponse,
    dependencies=[Depends(require_user)],
)
async def upload_and_process_invoice(
    file: UploadFile = File(...),
    invoice_id: Optional[str] = None,
    user: Optional[dict] = Depends(require_user),
) -> UploadInvoiceProcessResponse:
    """
    Upload an invoice file (PDF, image, or text) and run the invoice
    processing pipeline: extraction, validation, duplicates, ITC.
    """
    try:
        _consume_upload_quota(user)
        text, family, ocr_warning = _read_and_extract(file)
        from app.invoice_intelligence import get_invoice_api

        result = get_invoice_api().process_invoice(text, invoice_id)
        return UploadInvoiceProcessResponse(
            meta=UploadMeta(
                filename=file.filename or "upload",
                content_family=family,
                size_bytes=file.size if file.size is not None else 0,
                ocr_simulated=ocr_warning is not None or "OCR simulated" in text,
                ocr_warning=ocr_warning,
            ),
            result=_format_invoice_result(result),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error processing uploaded invoice")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process uploaded invoice",
        )
