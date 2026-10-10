"""
OCR Engine
==========

Optical Character Recognition for image-based documents.

Real paths:
- PDFs: text-layer extraction with PyMuPDF, falling back to pypdf (OCR-free).
  Scanned PDFs are rendered page-by-page and OCR'd with pytesseract when
  Tesseract is installed.
- Images: pytesseract + Pillow when Tesseract is installed.
- Image preprocessing (grayscale + autocontrast) via Pillow when installed.

Simulated OCR is never silent and never the default: it only runs when
explicitly requested through ``OCREngineType.SIMULATED`` or the
``FBR_OCR_SIMULATE=1`` environment variable, and every simulated result is
marked ``ocr_simulated=True`` with ``confidence=0.0``. When no OCR engine is
installed the result is an honest failure (empty text, explicit warning,
``ocr_simulated=False``) instead of a fake success.
"""

import io
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("document_intelligence")

# Simulated OCR is opt-in only.
SIMULATE_ENV_VAR = "FBR_OCR_SIMULATE"

_TRUTHY = {"1", "true", "yes", "on"}


class OCREngineType(str, Enum):
    """Type of OCR engine."""
    TESSERACT = "tesseract"
    GOOGLE_VISION = "google_vision"
    AWS_TEXTRACT = "aws_textract"
    AZURE_FORM = "azure_form"
    SIMULATED = "simulated"  # For development/testing only, opt-in


@dataclass
class TextBlock:
    """Block of text from OCR."""
    text: str
    confidence: float
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    page_number: int = 1


@dataclass
class OCRResult:
    """Result of OCR processing."""
    full_text: str
    confidence: float
    blocks: list[TextBlock] = field(default_factory=list)
    page_count: int = 1
    language_detected: str = "eng"
    processing_time_ms: float = 0.0
    engine_used: str = "simulated"
    error: Optional[str] = None
    warning: Optional[str] = None
    ocr_simulated: bool = False


class OCREngine:
    """
    OCR engine wrapper.

    Defaults to the real local engine (pytesseract + Tesseract). The
    simulated engine exists only for development and must be requested
    explicitly.
    """

    def __init__(self, engine_type: OCREngineType = OCREngineType.TESSERACT):
        self.engine_type = engine_type
        self.supported_languages = ["eng", "urd"]  # English, Urdu

    def extract_text(
        self,
        image_data: bytes,
        language: str = "eng",
    ) -> OCRResult:
        """Extract text from image bytes with a real OCR engine when installed."""
        started = time.time()

        if self._simulation_requested():
            return self._simulate_ocr(image_data, language)

        fallback_warning = self._engine_fallback_warning()

        try:
            import pytesseract  # noqa: F401
            from PIL import Image
        except ImportError:
            return self._no_engine_result(language, fallback_warning)

        try:
            with Image.open(io.BytesIO(image_data)) as img:
                text, blocks, confidence = self._run_tesseract(img, language)
        except Exception as exc:  # noqa: BLE001 - report honestly, never fake text
            logger.warning("Image OCR failed: %s", exc)
            return OCRResult(
                full_text="",
                confidence=0.0,
                blocks=[],
                page_count=1,
                language_detected=language,
                engine_used="tesseract",
                error=f"Image OCR failed: {exc}",
                warning=fallback_warning,
                processing_time_ms=(time.time() - started) * 1000,
                ocr_simulated=False,
            )

        warning = fallback_warning
        if not text.strip():
            warning = "OCR recognized no text in this image."

        return OCRResult(
            full_text=text,
            confidence=confidence,
            blocks=blocks,
            page_count=1,
            language_detected=language,
            engine_used="tesseract",
            warning=warning,
            processing_time_ms=(time.time() - started) * 1000,
            ocr_simulated=False,
        )

    def extract_from_pdf(self, pdf_data: bytes) -> OCRResult:
        """
        Extract text from a PDF.

        Uses the embedded text layer first (PyMuPDF, then pypdf). If the PDF
        has no text layer (scanned document), pages are OCR'd with
        pytesseract when Tesseract is installed; otherwise the result states
        plainly that no text could be extracted.
        """
        started = time.time()

        if self._simulation_requested():
            return self._simulate_ocr(pdf_data, "eng")

        text, page_count, engine = self._extract_text_layer(pdf_data)
        if text.strip():
            return OCRResult(
                full_text=text,
                confidence=self._estimate_text_confidence(text),
                blocks=[],
                page_count=max(page_count, 1),
                language_detected=self.detect_language(text),
                engine_used=engine,
                processing_time_ms=(time.time() - started) * 1000,
                ocr_simulated=False,
            )

        ocr_result = self._ocr_pdf_pages(pdf_data)
        if ocr_result is not None:
            ocr_result.processing_time_ms = (time.time() - started) * 1000
            return ocr_result

        return OCRResult(
            full_text="",
            confidence=0.0,
            blocks=[],
            page_count=max(page_count, 1),
            language_detected="eng",
            engine_used=engine,
            error="No text layer found and no OCR engine is installed",
            warning=(
                "PDF has no extractable text layer (scanned document) and "
                "pytesseract/Tesseract is not installed, so no text could be "
                "extracted."
            ),
            processing_time_ms=(time.time() - started) * 1000,
            ocr_simulated=False,
        )

    def _simulation_requested(self) -> bool:
        """Simulated OCR must be explicitly requested."""
        if self.engine_type == OCREngineType.SIMULATED:
            return True
        return os.environ.get(SIMULATE_ENV_VAR, "").strip().lower() in _TRUTHY

    def _engine_fallback_warning(self) -> Optional[str]:
        """Warn when a requested cloud engine is not configured."""
        if self.engine_type in (OCREngineType.TESSERACT, OCREngineType.SIMULATED):
            return None
        return (
            f"Requested OCR engine '{self.engine_type.value}' is not configured; "
            f"the local tesseract engine was used instead."
        )

    def _extract_text_layer(self, pdf_data: bytes) -> tuple[str, int, str]:
        """OCR-free text extraction: PyMuPDF first, pypdf as fallback."""
        try:
            import pymupdf  # type: ignore

            with pymupdf.open(stream=pdf_data, filetype="pdf") as doc:
                text = "\n".join(page.get_text() for page in doc)
                return text, doc.page_count, "pymupdf"
        except Exception as exc:  # noqa: BLE001 - fall through to pypdf
            logger.warning("pymupdf text extraction failed (%s); trying pypdf", exc)

        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(pdf_data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, len(reader.pages), "pypdf"
        except Exception as exc:  # noqa: BLE001
            logger.warning("pypdf text extraction failed (%s)", exc)
            return "", 0, "none"

    def _ocr_pdf_pages(
        self,
        pdf_data: bytes,
        language: str = "eng",
    ) -> Optional[OCRResult]:
        """OCR a scanned PDF page by page. None when no OCR engine exists."""
        try:
            import pymupdf  # type: ignore
            import pytesseract  # noqa: F401
            from PIL import Image
        except ImportError:
            return None

        try:
            page_texts: list[str] = []
            blocks: list[TextBlock] = []
            page_confidences: list[float] = []

            with pymupdf.open(stream=pdf_data, filetype="pdf") as doc:
                page_count = doc.page_count
                for page_number, page in enumerate(doc, start=1):
                    pixmap = page.get_pixmap(dpi=200)
                    with Image.open(io.BytesIO(pixmap.tobytes("png"))) as img:
                        page_text, page_blocks, page_conf = self._run_tesseract(
                            img, language
                        )
                    page_texts.append(page_text)
                    for block in page_blocks:
                        block.page_number = page_number
                    blocks.extend(page_blocks)
                    page_confidences.append(page_conf)

            text = "\n".join(page_texts).strip()
            confidence = (
                round(sum(page_confidences) / len(page_confidences), 2)
                if page_confidences else 0.0
            )
            return OCRResult(
                full_text=text,
                confidence=confidence,
                blocks=blocks,
                page_count=max(page_count, 1),
                language_detected=language,
                engine_used="tesseract",
                warning=None if text else "OCR recognized no text in this PDF.",
                ocr_simulated=False,
            )
        except Exception as exc:  # noqa: BLE001 - report honestly, never fake text
            logger.warning("PDF page OCR failed: %s", exc)
            return OCRResult(
                full_text="",
                confidence=0.0,
                blocks=[],
                page_count=1,
                language_detected=language,
                engine_used="tesseract",
                error=f"PDF OCR failed: {exc}",
                ocr_simulated=False,
            )

    @staticmethod
    def _run_tesseract(img, language: str = "eng") -> tuple[str, list[TextBlock], float]:
        """Run pytesseract on an open Pillow image; return text, blocks, confidence."""
        import pytesseract

        text = pytesseract.image_to_string(img, lang=language)

        blocks: list[TextBlock] = []
        confidences: list[float] = []
        try:
            tsv = pytesseract.image_to_data(img, lang=language)
        except Exception:  # noqa: BLE001 - text is still usable without per-word data
            tsv = ""

        for line in tsv.splitlines()[1:]:
            columns = line.split("\t")
            if len(columns) != 12:
                continue
            try:
                confidence = float(columns[10])
            except ValueError:
                continue
            if confidence < 0:
                continue
            confidences.append(confidence)
            try:
                blocks.append(TextBlock(
                    text=columns[11],
                    confidence=round(confidence / 100, 2),
                    x=int(columns[6]),
                    y=int(columns[7]),
                    width=int(columns[8]),
                    height=int(columns[9]),
                ))
            except ValueError:
                continue

        overall = (
            round(sum(confidences) / len(confidences) / 100, 2)
            if confidences else 0.0
        )
        return text, blocks, overall

    def _no_engine_result(
        self,
        language: str,
        extra_warning: Optional[str] = None,
    ) -> OCRResult:
        """Honest result when no OCR engine is installed."""
        warning = (
            "No OCR engine available: pytesseract/Tesseract is not installed, "
            "so no text could be extracted from this image."
        )
        if extra_warning:
            warning = f"{warning} {extra_warning}"
        return OCRResult(
            full_text="",
            confidence=0.0,
            blocks=[],
            page_count=1,
            language_detected=language,
            engine_used="none",
            warning=warning,
            ocr_simulated=False,
        )

    @staticmethod
    def _estimate_text_confidence(text: str) -> float:
        """Heuristic readability score for OCR-free text-layer extraction."""
        sample = text[:4000]
        if not sample.strip():
            return 0.0
        readable = sum(1 for ch in sample if ch.isalnum() or ch.isspace())
        return round(min(1.0, readable / len(sample)), 2)

    def _simulate_ocr(self, data: bytes, language: str) -> OCRResult:
        """
        Simulated OCR for development only.

        Returns a placeholder result with an explicit warning and
        ocr_simulated=True so callers can surface the provenance downstream.
        Never returns extracted text or a non-zero confidence.
        """
        logger.info(f"OCR processing {len(data)} bytes (engine: simulated)")
        warning = "Scanned PDF - OCR simulated, install tesseract for real text"
        return OCRResult(
            full_text=f"[OCR simulated - no text extracted] {warning}",
            confidence=0.0,
            blocks=[],
            page_count=1,
            language_detected=language,
            engine_used="simulated",
            warning=warning,
            ocr_simulated=True,
        )

    def preprocess_image(self, image_data: bytes) -> bytes:
        """Grayscale + autocontrast via Pillow when installed, else passthrough."""
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return image_data

        try:
            with Image.open(io.BytesIO(image_data)) as img:
                prepared = ImageOps.autocontrast(img.convert("L"))
                buffer = io.BytesIO()
                prepared.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Image preprocessing failed: %s", exc)
            return image_data

    def detect_language(self, text: str) -> str:
        """Detect language of text."""
        # Simple heuristic: check for Urdu-specific characters
        urdu_chars = set("ہےکھگھچھجھڈھتھددڑرڑزژسشصضطظعغفقگلمنںوہیۃءآأؤإئة")
        text_chars = set(text)
        if text_chars & urdu_chars:
            return "urd"
        return "eng"
