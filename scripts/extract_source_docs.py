from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from docx import Document
import openpyxl
import xlrd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = PROJECT_ROOT / "data" / "raw" / "04-source-docs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "profile" / "source_docs"
EXTRACTED_DIR = OUTPUT_DIR / "extracted"
PROGRESS_FILE = PROJECT_ROOT / "PROGRESS.md"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".md",
    ".jsonl",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value)


def extract_pdf(path: Path) -> dict[str, Any]:
    """
    Extract text from a PDF.

    First attempt:
        strict=False

    This allows pypdf to tolerate some malformed PDF structures.

    For very large PDFs, PyMuPDF is used to avoid excessive memory
    usage from retaining every page object before serialization.
    """
    reader = PdfReader(
        str(path),
        strict=False,
    )

    if len(reader.pages) > 1000:
        import pymupdf

        document = pymupdf.open(str(path))
        pages = []
        total_chars = 0

        try:
            for page_number, page in enumerate(
                document,
                start=1,
            ):
                text = page.get_text() or ""
                total_chars += len(text)
                pages.append(
                    {
                        "page": page_number,
                        "text": text,
                        "characters": len(text),
                    }
                )
        finally:
            document.close()

        return {
            "format": "pdf",
            "pages": len(pages),
            "text_characters": total_chars,
            "pages_data": pages,
        }

    pages = []
    total_chars = 0

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        total_chars += len(text)

        pages.append(
            {
                "page": page_number,
                "text": text,
                "characters": len(text),
            }
        )

    return {
        "format": "pdf",
        "pages": len(reader.pages),
        "text_characters": total_chars,
        "pages_data": pages,
    }


def extract_docx(path: Path) -> dict[str, Any]:
    document = Document(str(path))

    paragraphs = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if text:
            paragraphs.append(text)

    tables = []

    for table_index, table in enumerate(
        document.tables,
        start=1,
    ):
        rows = []

        for row in table.rows:
            rows.append(
                [
                    cell.text.strip()
                    for cell in row.cells
                ]
            )

        tables.append(
            {
                "table": table_index,
                "rows": rows,
            }
        )

    paragraph_chars = sum(
        len(item)
        for item in paragraphs
    )

    return {
        "format": "docx",
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
        "text_characters": paragraph_chars,
        "paragraphs": paragraphs,
        "tables": tables,
    }


def extract_xlsx(path: Path) -> dict[str, Any]:
    workbook = openpyxl.load_workbook(
        filename=str(path),
        read_only=True,
        data_only=True,
    )

    sheets = []

    for worksheet in workbook.worksheets:
        rows = []

        for row in worksheet.iter_rows(
            values_only=True
        ):
            rows.append(
                [
                    safe_text(value)
                    for value in row
                ]
            )

        sheets.append(
            {
                "sheet": worksheet.title,
                "rows": rows,
                "row_count": len(rows),
            }
        )

    workbook.close()

    return {
        "format": "xlsx",
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def extract_xls(path: Path) -> dict[str, Any]:
    workbook = xlrd.open_workbook(
        str(path),
        on_demand=True,
    )

    sheets = []

    for sheet in workbook.sheets():
        rows = []

        for row_index in range(
            sheet.nrows
        ):
            row_values = sheet.row_values(
                row_index
            )

            rows.append(
                [
                    safe_text(value)
                    for value in row_values
                ]
            )

        sheets.append(
            {
                "sheet": sheet.name,
                "rows": rows,
                "row_count": len(rows),
            }
        )

    workbook.release_resources()

    return {
        "format": "xls",
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def extract_markdown(path: Path) -> dict[str, Any]:
    """
    Extract a Markdown knowledge file.

    The document is split into heading-delimited sections
    (lines starting with '#'). Each section keeps its heading
    and the raw text below it. Wording is never rewritten.
    """
    text = path.read_text(
        encoding="utf-8",
    )

    sections = []

    current_heading = None
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.lstrip()

        if stripped.startswith("#"):
            if any(
                item.strip()
                for item in current_lines
            ):
                sections.append(
                    {
                        "heading": current_heading,
                        "text": "\n".join(
                            current_lines,
                        ).strip(),
                    }
                )

            current_heading = stripped.lstrip(
                "#",
            ).strip()

            current_lines = []
        else:
            current_lines.append(line)

    if any(
        item.strip()
        for item in current_lines
    ):
        sections.append(
            {
                "heading": current_heading,
                "text": "\n".join(
                    current_lines,
                ).strip(),
            }
        )

    return {
        "format": "markdown",
        "text_characters": len(text),
        "section_count": len(sections),
        "sections": sections,
    }


def extract_jsonl(path: Path) -> dict[str, Any]:
    """
    Extract a JSONL question/answer knowledge file.

    Every line must be a JSON object with a non-empty
    "question" and "answer". Malformed lines abort the
    extraction of that file (visible failure, no guessing).
    """
    entries = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON at line "
                    f"{line_number}: {exc}"
                ) from exc

            if not isinstance(entry, dict):
                raise ValueError(
                    f"Line {line_number} is not a "
                    f"JSON object"
                )

            question = safe_text(
                entry.get("question"),
            ).strip()

            answer = safe_text(
                entry.get("answer"),
            ).strip()

            if not question or not answer:
                raise ValueError(
                    f"Line {line_number} is missing "
                    f"question or answer"
                )

            entries.append(
                {
                    "id": safe_text(
                        entry.get("id"),
                    ),
                    "category": safe_text(
                        entry.get("category"),
                    ),
                    "question": question,
                    "answer": answer,
                    "source": safe_text(
                        entry.get("source"),
                    ),
                    "section": safe_text(
                        entry.get("section"),
                    ),
                    "language": safe_text(
                        entry.get("language"),
                    ),
                    "difficulty": safe_text(
                        entry.get("difficulty"),
                    ),
                    "last_updated": safe_text(
                        entry.get("last_updated"),
                    ),
                }
            )

    return {
        "format": "jsonl",
        "entry_count": len(entries),
        "entries": entries,
    }


def output_path_for(source_path: Path) -> Path:
    relative_path = source_path.relative_to(
        SOURCE_DIR
    )

    output_relative = relative_path.with_suffix(
        ".json"
    )

    return EXTRACTED_DIR / output_relative


def extract_document(
    source_path: Path,
) -> tuple[dict[str, Any], str]:
    extension = source_path.suffix.lower()

    if extension == ".pdf":
        return (
            extract_pdf(source_path),
            "extracted",
        )

    if extension == ".docx":
        return (
            extract_docx(source_path),
            "extracted",
        )

    if extension == ".xlsx":
        return (
            extract_xlsx(source_path),
            "extracted",
        )

    if extension == ".xls":
        return (
            extract_xls(source_path),
            "extracted",
        )

    if extension == ".md":
        return (
            extract_markdown(source_path),
            "extracted",
        )

    if extension == ".jsonl":
        return (
            extract_jsonl(source_path),
            "extracted",
        )

    if extension == ".doc":
        return (
            {
                "format": "doc",
                "message": (
                    "Legacy .doc format detected. "
                    "Automatic extraction is not performed "
                    "because no DOC parser dependency is "
                    "installed."
                ),
            },
            "manual_review_required",
        )

    return (
        {
            "message": (
                "Unsupported file extension."
            ),
        },
        "unsupported",
    )


def write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def append_progress(
    total: int,
    extracted: int,
    manual_review: int,
    failed: int,
    output_files: int,
) -> None:
    """
    Append a single checkpoint to the existing PROGRESS.md.

    No new progress/report file is created.
    """
    if not PROGRESS_FILE.exists():
        print(
            "WARNING: PROGRESS.md not found. "
            "Skipping progress update."
        )
        return

    progress_entry = f"""

## Latest Update

### Source Document Extraction Audit

- Script: `scripts/extract_source_docs.py`
- Documents scanned: {total}
- Successfully extracted: {extracted}
- Manual review required: {manual_review}
- Failed extraction: {failed}
- Output files created: {output_files}
- Output directory: `data/profile/source_docs/extracted/`
- Raw source documents modified: NO
- Status: {"✅ COMPLETE" if failed == 0 else "⏳ INCOMPLETE"}

### Extraction Behavior

- PDF extraction uses `pypdf` with `strict=False`.
- Malformed PDFs no longer stop the complete extraction run.
- A file that cannot be recovered is recorded as failed and the next source file is processed.
- DOCX extraction uses `python-docx`.
- XLSX extraction uses `openpyxl`.
- XLS extraction uses `xlrd`.
- Markdown (`.md`) extraction splits the file into heading-delimited sections.
- JSONL (`.jsonl`) extraction reads question/answer entries line by line.
- Legacy DOC files are marked for manual review.
- No tax/source content is guessed.
- No raw source document is overwritten.

### Next

{"Review failed extraction files and validate successful extracted outputs before document normalization." if failed > 0 else "Validate all extracted outputs before document normalization."}
"""

    with PROGRESS_FILE.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(progress_entry)


def main() -> None:
    print("=" * 60)
    print("FBR SOURCE DOCUMENT EXTRACTION AUDIT")
    print("=" * 60)

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Source directory not found: {SOURCE_DIR}"
        )

    EXTRACTED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EXTENSIONS
        )
    )

    total = len(source_files)

    extracted_count = 0
    manual_review_count = 0
    failed_count = 0
    output_file_count = 0

    for index, source_path in enumerate(
        source_files,
        start=1,
    ):
        relative_path = source_path.relative_to(
            SOURCE_DIR
        )

        print(
            f"[{index}/{total}] {relative_path}"
        )

        file_hash = sha256_file(
            source_path
        )

        try:
            extracted_data, status = (
                extract_document(source_path)
            )

            if status == "extracted":
                output_path = output_path_for(
                    source_path
                )

                write_json(
                    output_path,
                    {
                        "source": str(
                            relative_path
                        ),
                        "sha256": file_hash,
                        "data": extracted_data,
                    },
                )

                extracted_count += 1
                output_file_count += 1

                print(
                    "    STATUS: EXTRACTED"
                )

            elif status == "manual_review_required":
                manual_review_count += 1

                print(
                    "    STATUS: MANUAL REVIEW REQUIRED"
                )

            else:
                failed_count += 1

                print(
                    "    STATUS: FAILED"
                )

        except Exception as exc:
            failed_count += 1

            print(
                "    STATUS: FAILED"
            )
            print(
                f"    ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

            # Continue to the next file.
            continue

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"Documents scanned        : {total}"
    )
    print(
        f"Successfully extracted   : "
        f"{extracted_count}"
    )
    print(
        f"Manual review required   : "
        f"{manual_review_count}"
    )
    print(
        f"Failed extraction        : "
        f"{failed_count}"
    )
    print(
        f"Output files created     : "
        f"{output_file_count}"
    )
    print(
        f"Output directory         : "
        f"{EXTRACTED_DIR}"
    )
    print("=" * 60)

    append_progress(
        total=total,
        extracted=extracted_count,
        manual_review=manual_review_count,
        failed=failed_count,
        output_files=output_file_count,
    )


if __name__ == "__main__":
    main()