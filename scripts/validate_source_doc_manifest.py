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

MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / "source_docs"
    / "source_doc_manifest.csv"
)

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


def append_progress(
    manifest_rows: int,
    actual_files: int,
    missing: int,
    extra: int,
    invalid: int,
) -> None:
    if not PROGRESS_FILE.exists():
        return

    status = "✅ PASS" if (
        missing == 0
        and extra == 0
        and invalid == 0
        and manifest_rows == actual_files
    ) else "⏳ PROBLEMS FOUND"

    entry = f"""

## Latest Update

### Source Document Manifest Validation

- Script: `scripts/validate_source_doc_manifest.py`
- Manifest rows: {manifest_rows}
- Actual supported source files: {actual_files}
- Missing files in manifest: {missing}
- Extra manifest files: {extra}
- Invalid manifest rows: {invalid}
- Status: {status}
- Raw source documents modified: NO

### Validation Rule

The manifest must exactly match the supported files under
`data/raw/04-source-docs/`.

No source content was modified.
"""

    with PROGRESS_FILE.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(entry)


def main() -> None:
    print("=" * 60)
    print("SOURCE DOCUMENT MANIFEST VALIDATION")
    print("=" * 60)

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Source directory not found: {SOURCE_DIR}"
        )

    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_FILE}"
        )

    actual_files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EXTENSIONS
        )
    )

    actual_paths = {
        str(path.relative_to(SOURCE_DIR))
        for path in actual_files
    }

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    manifest_paths = {
        row["relative_path"]
        for row in rows
        if row.get("relative_path")
    }

    missing_files = sorted(
        actual_paths - manifest_paths
    )

    extra_files = sorted(
        manifest_paths - actual_paths
    )

    invalid_rows = []

    for row in rows:
        relative_path = row.get(
            "relative_path",
            "",
        )

        extension = row.get(
            "extension",
            "",
        )

        if (
            not relative_path
            or extension.lower()
            not in SUPPORTED_EXTENSIONS
        ):
            invalid_rows.append(row)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"Manifest rows          : {len(rows)}"
    )
    print(
        f"Actual source files    : "
        f"{len(actual_files)}"
    )
    print(
        f"Missing files          : "
        f"{len(missing_files)}"
    )
    print(
        f"Extra manifest files   : "
        f"{len(extra_files)}"
    )
    print(
        f"Invalid manifest rows  : "
        f"{len(invalid_rows)}"
    )

    if missing_files:
        print()
        print("MISSING FILES")
        for item in missing_files:
            print(item)

    if extra_files:
        print()
        print("EXTRA MANIFEST FILES")
        for item in extra_files:
            print(item)

    if invalid_rows:
        print()
        print("INVALID ROWS")
        for row in invalid_rows:
            print(row)

    passed = (
        len(rows) == len(actual_files)
        and not missing_files
        and not extra_files
        and not invalid_rows
    )

    print()

    if passed:
        print("MANIFEST VALIDATION: PASS")
    else:
        print("MANIFEST VALIDATION: FAIL")

    print("=" * 60)

    append_progress(
        manifest_rows=len(rows),
        actual_files=len(actual_files),
        missing=len(missing_files),
        extra=len(extra_files),
        invalid=len(invalid_rows),
    )

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()