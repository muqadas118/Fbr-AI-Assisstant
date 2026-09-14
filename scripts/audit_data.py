from __future__ import annotations

import csv
import hashlib
import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

PROFILE_DIR = DATA_DIR / "profile"
OUTPUT_FILE = PROFILE_DIR / "data_quality_audit.json"

SUPPORTED_EXTENSIONS = {
    ".md",
    ".jsonl",
    ".csv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


# ============================================================
# HELPERS
# ============================================================

def file_hash(path: Path) -> str:
    """Return SHA-256 hash of a file."""
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def safe_read_text(path: Path) -> str:
    """Read a text file without modifying it."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return ""


# ============================================================
# JSONL AUDIT
# ============================================================

def audit_jsonl(files: list[Path]) -> dict:
    total_records = 0
    valid_records = 0
    malformed_records = 0
    empty_records = 0
    missing_question = 0
    missing_answer = 0

    record_hashes = Counter()

    for path in files:
        lines = safe_read_text(path).splitlines()

        for line in lines:
            if not line.strip():
                continue

            total_records += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed_records += 1
                continue

            if not isinstance(record, dict):
                malformed_records += 1
                continue

            valid_records += 1

            if not record:
                empty_records += 1

            question = record.get("question")
            answer = record.get("answer")

            if question is None or not str(question).strip():
                missing_question += 1

            if answer is None or not str(answer).strip():
                missing_answer += 1

            normalized = json.dumps(
                record,
                sort_keys=True,
                ensure_ascii=False,
            )

            record_hashes[
                hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            ] += 1

    duplicate_records = sum(
        count - 1
        for count in record_hashes.values()
        if count > 1
    )

    return {
        "files": len(files),
        "total_records": total_records,
        "valid_records": valid_records,
        "malformed_records": malformed_records,
        "empty_records": empty_records,
        "missing_question": missing_question,
        "missing_answer": missing_answer,
        "duplicate_records": duplicate_records,
    }


# ============================================================
# MARKDOWN AUDIT
# ============================================================

def audit_markdown(files: list[Path]) -> dict:
    empty_files = 0
    unreadable_files = 0
    content_hashes = Counter()

    for path in files:
        try:
            content = safe_read_text(path)
        except OSError:
            unreadable_files += 1
            continue

        if not content.strip():
            empty_files += 1
            continue

        normalized = " ".join(content.split())

        content_hashes[
            hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        ] += 1

    duplicate_files = sum(
        count - 1
        for count in content_hashes.values()
        if count > 1
    )

    return {
        "files": len(files),
        "empty_files": empty_files,
        "unreadable_files": unreadable_files,
        "duplicate_content_files": duplicate_files,
    }


# ============================================================
# CSV AUDIT
# ============================================================

def audit_csv(files: list[Path]) -> dict:
    total_rows = 0
    empty_rows = 0
    missing_values = 0
    inconsistent_columns = 0

    schemas = Counter()

    for path in files:
        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                reader = csv.reader(file)

                try:
                    header = next(reader)
                except StopIteration:
                    continue

                header = [column.strip() for column in header]
                expected_columns = len(header)

                schemas[tuple(header)] += 1

                for row in reader:
                    if not row:
                        continue

                    total_rows += 1

                    if all(not str(value).strip() for value in row):
                        empty_rows += 1

                    if len(row) != expected_columns:
                        inconsistent_columns += 1

                    missing_values += sum(
                        1
                        for value in row
                        if not str(value).strip()
                    )

        except (OSError, UnicodeDecodeError, csv.Error):
            inconsistent_columns += 1

    return {
        "files": len(files),
        "total_rows": total_rows,
        "empty_rows": empty_rows,
        "missing_values": missing_values,
        "inconsistent_rows": inconsistent_columns,
        "different_schemas": len(schemas),
    }


# ============================================================
# SOURCE DOCUMENT AUDIT
# ============================================================

def audit_documents(files: list[Path]) -> dict:
    by_extension = Counter()
    unreadable_files = []

    for path in files:
        extension = path.suffix.lower()
        by_extension[extension] += 1

        try:
            with path.open("rb") as file:
                file.read(1024)
        except OSError:
            unreadable_files.append(str(path.relative_to(PROJECT_ROOT)))

    return {
        "files": len(files),
        "by_extension": dict(sorted(by_extension.items())),
        "unreadable_files": unreadable_files,
    }


# ============================================================
# GLOBAL DUPLICATE AUDIT
# ============================================================

def audit_file_duplicates(files: list[Path]) -> dict:
    hashes = {}

    for path in files:
        try:
            digest = file_hash(path)
        except (OSError, ValueError):
            logger.exception("Error hashing file %s", path)
            continue

        hashes.setdefault(digest, []).append(
            str(path.relative_to(PROJECT_ROOT))
        )

    duplicate_groups = [
        paths
        for paths in hashes.values()
        if len(paths) > 1
    ]

    duplicate_files = sum(
        len(group) - 1
        for group in duplicate_groups
    )

    return {
        "duplicate_groups": len(duplicate_groups),
        "duplicate_files": duplicate_files,
        "groups": duplicate_groups,
    }


# ============================================================
# MAIN AUDIT
# ============================================================

def main() -> None:
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"Data directory not found: {DATA_DIR}"
        )

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    all_files = [
        path
        for path in DATA_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and "profile" not in path.parts
    ]

    jsonl_files = [
        path for path in all_files
        if path.suffix.lower() == ".jsonl"
    ]

    markdown_files = [
        path for path in all_files
        if path.suffix.lower() == ".md"
    ]

    csv_files = [
        path for path in all_files
        if path.suffix.lower() == ".csv"
    ]

    document_files = [
        path for path in all_files
        if path.suffix.lower()
        in {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    ]

    audit = {
        "summary": {
            "total_supported_files": len(all_files),
            "jsonl_files": len(jsonl_files),
            "markdown_files": len(markdown_files),
            "csv_files": len(csv_files),
            "source_document_files": len(document_files),
        },
        "jsonl": audit_jsonl(jsonl_files),
        "markdown": audit_markdown(markdown_files),
        "csv": audit_csv(csv_files),
        "source_documents": audit_documents(document_files),
        "file_duplicates": audit_file_duplicates(all_files),
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            audit,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # CONSOLE REPORT
    # --------------------------------------------------------

    print()
    print("# FBR DATA QUALITY AUDIT")
    print()

    print("## Summary")
    print(f"Supported files : {audit['summary']['total_supported_files']}")
    print(f"JSONL files     : {audit['summary']['jsonl_files']}")
    print(f"Markdown files  : {audit['summary']['markdown_files']}")
    print(f"CSV files       : {audit['summary']['csv_files']}")
    print(
        f"Source documents: "
        f"{audit['summary']['source_document_files']}"
    )

    print()
    print("## JSONL")

    for key, value in audit["jsonl"].items():
        print(f"{key.replace('_', ' ').title():25}: {value}")

    print()
    print("## Markdown")

    for key, value in audit["markdown"].items():
        print(f"{key.replace('_', ' ').title():25}: {value}")

    print()
    print("## CSV")

    for key, value in audit["csv"].items():
        print(f"{key.replace('_', ' ').title():25}: {value}")

    print()
    print("## Source Documents")

    for extension, count in audit["source_documents"][
        "by_extension"
    ].items():
        print(f"{extension:10}: {count}")

    print(
        "Unreadable files        : "
        f"{len(audit['source_documents']['unreadable_files'])}"
    )

    print()
    print("## File Duplicates")
    print(
        "Duplicate groups        : "
        f"{audit['file_duplicates']['duplicate_groups']}"
    )
    print(
        "Duplicate files         : "
        f"{audit['file_duplicates']['duplicate_files']}"
    )

    print()
    print("# AUDIT COMPLETE")
    print()
    print(f"Report: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()