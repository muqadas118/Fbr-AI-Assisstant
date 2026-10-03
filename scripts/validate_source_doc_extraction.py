from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "04-source-docs"
)

EXTRACTED_DIR = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / "source_docs"
    / "extracted"
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
    ".docx",
    ".xls",
    ".xlsx",
    ".md",
    ".jsonl",
}

MANUAL_REVIEW_EXTENSIONS = {
    ".doc",
}


def load_manifest_paths() -> tuple[set[str], set[str]]:
    import csv

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        paths = set()
        manual_review_paths = set()

        for row in reader:
            relative_path = row.get(
                "relative_path",
                "",
            )
            extension = Path(
                relative_path
            ).suffix.lower()

            if extension in SUPPORTED_EXTENSIONS:
                paths.add(relative_path)
            elif extension in MANUAL_REVIEW_EXTENSIONS:
                manual_review_paths.add(relative_path)

        return paths, manual_review_paths


def expected_output_path(
    source_relative_path: str,
) -> Path:
    return (
        EXTRACTED_DIR
        / Path(
            source_relative_path
        ).with_suffix(".json")
    )


def append_progress(
    expected: int,
    actual: int,
    missing: int,
    invalid: int,
    valid: int,
) -> None:
    if not PROGRESS_FILE.exists():
        return

    passed = (
        missing == 0
        and invalid == 0
        and valid == expected
        and actual == expected
    )

    status = (
        "✅ PASS"
        if passed
        else "⏳ PROBLEMS FOUND"
    )

    entry = f"""

## Latest Update

### Source Document Extraction Validation

- Script: `scripts/validate_source_doc_extraction.py`
- Expected extractable documents: {expected}
- Extracted JSON files found: {actual}
- Valid extracted files: {valid}
- Missing extracted files: {missing}
- Invalid extracted files: {invalid}
- Status: {status}
- Raw source documents modified: NO

### Validation Rules

- Every extractable source document must have a corresponding JSON output.
- Every output must be valid JSON.
- Every output must contain `source`.
- Every output must contain `sha256`.
- Every output must contain `data`.
- No raw source document is modified.

### Next

{"Proceed to failed-file review and document normalization." if passed else "Review missing/invalid extraction outputs before document normalization."}
"""

    with PROGRESS_FILE.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(entry)


def main() -> None:
    print("=" * 60)
    print("SOURCE DOCUMENT EXTRACTION VALIDATION")
    print("=" * 60)

    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_FILE}"
        )

    if not EXTRACTED_DIR.exists():
        raise FileNotFoundError(
            f"Extraction directory not found: {EXTRACTED_DIR}"
        )

    expected_paths, manual_review_paths = (
        load_manifest_paths()
    )

    json_files = {
        str(
            path.relative_to(EXTRACTED_DIR)
            .with_suffix("")
        )
        for path in EXTRACTED_DIR.rglob("*.json")
    }

    expected_without_extension = {
        str(
            Path(path).with_suffix("")
        )
        for path in expected_paths
    }

    missing_paths = sorted(
        expected_without_extension
        - json_files
    )

    manual_review_without_extension = {
        str(
            Path(path).with_suffix("")
        )
        for path in manual_review_paths
    }

    missing_manual_review_paths = sorted(
        manual_review_without_extension
        - json_files
    )

    invalid_files = []
    valid_files = 0
    valid_manual_review_files = 0

    for relative_json in sorted(json_files):
        # relative_json is already extension-stripped (e.g. "...upto30.06.2015").
        # Do NOT use Path(...).with_suffix(".json") here: stems may contain dots
        # (date-stamped FBR filenames), and with_suffix would strip the last
        # dot-segment, producing a wrong path like "...upto30.06.json".
        output_path = (
            EXTRACTED_DIR
            / f"{relative_json}.json"
        )

        try:
            with output_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(
                data,
                dict,
            ):
                raise TypeError(
                    "Root JSON value is not an object."
                )

            source_name = data["source"]
            source_extension = Path(
                source_name
            ).suffix.lower()

            if source_extension in MANUAL_REVIEW_EXTENSIONS:
                manual_fields = {
                    "source",
                    "sha256",
                    "status",
                    "data",
                }

                missing_manual_fields = (
                    manual_fields
                    - data.keys()
                )

                if missing_manual_fields:
                    raise ValueError(
                        "Missing manual-review fields: "
                        + ", ".join(
                            sorted(missing_manual_fields)
                        )
                    )

                if data["status"] not in {
                    "extracted",
                    "manual_review_required",
                }:
                    raise ValueError(
                        "Invalid manual-review status."
                    )

                if not isinstance(
                    data["data"],
                    dict,
                ):
                    raise TypeError(
                        "Manual-review data must be an object."
                    )

                if data["status"] == (
                    "manual_review_required"
                ):
                    paragraphs = data["data"].get(
                        "paragraphs",
                        [],
                    )
                    tables = data["data"].get(
                        "tables",
                        [],
                    )
                    if paragraphs or any(
                        cell
                        for table in tables
                        for row in table
                        for cell in row
                    ):
                        raise ValueError(
                            "Manual-review record contains "
                            "meaningful extracted content."
                        )

                valid_manual_review_files += 1
                continue

            required_fields = {
                "source",
                "sha256",
                "data",
            }

            missing_fields = (
                required_fields
                - data.keys()
            )

            if missing_fields:
                raise ValueError(
                    "Missing fields: "
                    + ", ".join(
                        sorted(missing_fields)
                    )
                )

            if not data["source"]:
                raise ValueError(
                    "Empty source field."
                )

            if not data["sha256"]:
                raise ValueError(
                    "Empty sha256 field."
                )

            if "data" not in data:
                raise ValueError(
                    "Missing data field."
                )

            valid_files += 1

        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            invalid_files.append(
                (
                    relative_json,
                    f"{type(exc).__name__}: {exc}",
                )
            )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(
        f"Expected extractable docs : "
        f"{len(expected_paths)}"
    )
    print(
        f"JSON files found          : "
        f"{len(json_files)}"
    )
    print(
        f"Valid extracted files     : "
        f"{valid_files}"
    )
    print(
        f"Missing extracted files   : "
        f"{len(missing_paths)}"
    )
    print(
        f"Valid manual-review files : "
        f"{valid_manual_review_files}"
    )
    print(
        f"Missing manual-review files: "
        f"{len(missing_manual_review_paths)}"
    )
    print(
        f"Invalid extracted files   : "
        f"{len(invalid_files)}"
    )

    if missing_paths:
        print()
        print("MISSING OUTPUTS")
        for item in missing_paths:
            print(item + ".json")

    if missing_manual_review_paths:
        print()
        print("MISSING MANUAL-REVIEW OUTPUTS")
        for item in missing_manual_review_paths:
            print(item + ".json")

    if invalid_files:
        print()
        print("INVALID OUTPUTS")
        for filename, error in invalid_files:
            print(
                f"{filename}.json => {error}"
            )

    passed = (
        len(missing_paths) == 0
        and len(missing_manual_review_paths) == 0
        and len(invalid_files) == 0
        and valid_files == len(
            expected_paths
        )
        and valid_manual_review_files == len(
            manual_review_paths
        )
        and len(json_files) == (
            len(expected_paths)
            + len(manual_review_paths)
        )
    )

    print()

    if passed:
        print(
            "EXTRACTION VALIDATION: PASS"
        )
    else:
        print(
            "EXTRACTION VALIDATION: "
            "INCOMPLETE / REVIEW REQUIRED"
        )

    print("=" * 60)

    append_progress(
        expected=len(expected_paths),
        actual=len(json_files),
        missing=len(missing_paths),
        invalid=len(invalid_files),
        valid=valid_files,
    )

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()