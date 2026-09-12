from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "04-source-docs"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / "source_docs"
)

MANIFEST_FILE = (
    OUTPUT_DIR
    / "source_doc_manifest.csv"
)

PROGRESS_FILE = PROJECT_ROOT / "PROGRESS.md"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"

    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.2f} KB"

    if size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"

    return f"{size_bytes / (1024 ** 3):.2f} GB"


def append_progress(
    total: int,
    pdf: int,
    doc: int,
    docx: int,
    xls: int,
    xlsx: int,
) -> None:
    if not PROGRESS_FILE.exists():
        print(
            "WARNING: PROGRESS.md not found."
        )
        return

    entry = f"""

## Latest Update

### Source Document Manifest

- Created: `scripts/build_source_doc_manifest.py`
- Source documents indexed: {total}
- PDF files: {pdf}
- DOC files: {doc}
- DOCX files: {docx}
- XLS files: {xls}
- XLSX files: {xlsx}
- Manifest: `data/profile/source_docs/source_doc_manifest.csv`
- Raw source documents modified: NO
- Status: ✅ MANIFEST COMPLETE

### Purpose

The manifest records source-document metadata for later extraction
validation and document normalization.

Only filesystem metadata was read. No tax/source content was changed.

### Current Parallel Task

Source document extraction remains running separately.

Do not begin document normalization, chunking, embeddings, vector database,
RAG, agents, or application development until source-document extraction
and validation are complete.
"""

    with PROGRESS_FILE.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(entry)


def main() -> None:
    print("=" * 60)
    print("FBR SOURCE DOCUMENT MANIFEST")
    print("=" * 60)

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Source directory not found: {SOURCE_DIR}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EXTENSIONS
        )
    )

    counts = {
        ".pdf": 0,
        ".doc": 0,
        ".docx": 0,
        ".xls": 0,
        ".xlsx": 0,
    }

    rows = []

    for index, path in enumerate(
        files,
        start=1,
    ):
        relative_path = path.relative_to(
            SOURCE_DIR
        )

        extension = path.suffix.lower()
        size_bytes = path.stat().st_size

        counts[extension] += 1

        rows.append(
            {
                "index": index,
                "relative_path": str(
                    relative_path
                ),
                "filename": path.name,
                "extension": extension,
                "size_bytes": size_bytes,
                "size_human": format_size(
                    size_bytes
                ),
            }
        )

    with MANIFEST_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "index",
                "relative_path",
                "filename",
                "extension",
                "size_bytes",
                "size_human",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"Documents indexed : {len(files)}"
    )
    print(
        f"PDF files         : {counts['.pdf']}"
    )
    print(
        f"DOC files         : {counts['.doc']}"
    )
    print(
        f"DOCX files        : {counts['.docx']}"
    )
    print(
        f"XLS files         : {counts['.xls']}"
    )
    print(
        f"XLSX files        : {counts['.xlsx']}"
    )
    print()
    print(
        f"Manifest          : {MANIFEST_FILE}"
    )
    print("=" * 60)

    append_progress(
        total=len(files),
        pdf=counts[".pdf"],
        doc=counts[".doc"],
        docx=counts[".docx"],
        xls=counts[".xls"],
        xlsx=counts[".xlsx"],
    )


if __name__ == "__main__":
    main()