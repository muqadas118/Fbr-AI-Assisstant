from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
PROFILE_DIR = DATA_DIR / "profile"
CSV_PROFILE_DIR = PROFILE_DIR / "csv"

CSV_DIR = DATA_DIR / "raw" / "03-csv"

OUTPUT_FILE = CSV_PROFILE_DIR / "csv_row_investigation.json"


# ============================================================
# CONSTANTS
# ============================================================

CURRENCY_PATTERN = re.compile(
    r"^(?:Rs\.?|PKR)?\s*[\d,]+(?:\.\d+)?$",
    re.IGNORECASE,
)

NUMBER_PATTERN = re.compile(
    r"^[\d,]+(?:\.\d+)?$"
)

DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}$"
)


# ============================================================
# HELPERS
# ============================================================

def clean(value: str) -> str:
    """Return a stripped string without changing its meaning."""
    return str(value).strip()


def looks_numeric(value: str) -> bool:
    """Check whether a value looks like a numeric fragment."""
    value = clean(value)

    if not value:
        return False

    return bool(NUMBER_PATTERN.fullmatch(value))


def looks_currency(value: str) -> bool:
    """Check whether a value looks like a currency value."""
    value = clean(value)

    if not value:
        return False

    return bool(CURRENCY_PATTERN.fullmatch(value))


def looks_date(value: str) -> bool:
    """Check whether a value looks like an ISO date."""
    return bool(DATE_PATTERN.fullmatch(clean(value)))


def contains_comma_number(value: str) -> bool:
    """
    Detect values such as:
    Rs 10,000
    1,200,000
    10,500
    """
    value = clean(value)

    if not value:
        return False

    return "," in value and bool(
        re.search(r"\d,\d", value)
    )


def is_numeric_fragment(value: str) -> bool:
    """
    Detect fragments that commonly appear after a comma split.

    Examples:
    'Rs 10'
    '000'
    '1'
    '200'
    """
    value = clean(value)

    if not value:
        return False

    if looks_numeric(value):
        return True

    return bool(
        re.fullmatch(
            r"(?:Rs\.?|PKR)?\s*\d+",
            value,
            re.IGNORECASE,
        )
    )


def join_fragments(left: str, right: str) -> str:
    """
    Reconstruct a possible comma-separated numeric value
    for investigation only.

    This DOES NOT modify the source CSV.
    """
    left = clean(left)
    right = clean(right)

    return f"{left},{right}"


# ============================================================
# CSV READING
# ============================================================

def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read a CSV exactly as stored."""
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.reader(file)

        try:
            header = next(reader)
        except StopIteration:
            return [], []

        rows = list(reader)

    return header, rows


# ============================================================
# ROW ANALYSIS
# ============================================================

def find_numeric_split_sequences(
    row: list[str],
) -> list[dict]:
    """
    Find adjacent fragments that may have originally belonged
    to one comma-separated numeric/currency value.
    """
    sequences = []

    index = 0

    while index < len(row) - 1:
        current = clean(row[index])
        next_value = clean(row[index + 1])

        if (
            is_numeric_fragment(current)
            and is_numeric_fragment(next_value)
        ):
            reconstructed = join_fragments(
                current,
                next_value,
            )

            sequences.append(
                {
                    "start_position": index + 1,
                    "end_position": index + 2,
                    "values": [
                        current,
                        next_value,
                    ],
                    "reconstructed_candidate": reconstructed,
                    "reason": (
                        "Adjacent numeric fragments may represent "
                        "one comma-separated numeric/currency value."
                    ),
                }
            )

        index += 1

    return sequences


def classify_row(
    row: list[str],
    expected_columns: int,
) -> dict:
    """Classify the likely root cause of an inconsistent row."""

    actual_columns = len(row)
    difference = actual_columns - expected_columns

    numeric_splits = find_numeric_split_sequences(row)

    if difference > 0 and numeric_splits:
        return {
            "classification": "LIKELY_CSV_COMMA_SPLIT",
            "confidence": "high",
            "reason": (
                "The row contains extra columns and adjacent "
                "numeric fragments strongly suggest that one or "
                "more comma-containing numeric values were split "
                "into separate CSV fields."
            ),
            "split_sequences": numeric_splits,
        }

    if difference > 0:
        return {
            "classification": "UNEXPLAINED_EXTRA_COLUMNS",
            "confidence": "medium",
            "reason": (
                "The row contains more fields than the header, "
                "but no strong numeric comma-split pattern was detected."
            ),
            "split_sequences": [],
        }

    if difference < 0:
        return {
            "classification": "MISSING_COLUMNS",
            "confidence": "high",
            "reason": (
                "The row contains fewer fields than the header."
            ),
            "split_sequences": [],
        }

    return {
        "classification": "CONSISTENT",
        "confidence": "high",
        "reason": "Row length matches the header.",
        "split_sequences": [],
    }


# ============================================================
# COLUMN MAPPING
# ============================================================

def map_row_columns(
    header: list[str],
    row: list[str],
) -> list[dict]:
    """
    Preserve the exact positional relationship between header
    columns and row values.

    Extra values are explicitly labelled instead of being
    silently assigned to another column.
    """
    mapped = []

    maximum = max(len(header), len(row))

    for index in range(maximum):
        column_name = (
            header[index]
            if index < len(header)
            else f"UNEXPECTED_COLUMN_{index + 1}"
        )

        value = (
            row[index]
            if index < len(row)
            else ""
        )

        mapped.append(
            {
                "position": index + 1,
                "column": column_name,
                "value": value,
            }
        )

    return mapped


# ============================================================
# FILE INVESTIGATION
# ============================================================

def investigate_file(path: Path) -> dict:
    """Investigate all structurally inconsistent rows in a CSV."""

    header, rows = read_csv(path)

    expected_columns = len(header)

    inconsistent_rows = []

    classification_counts = Counter()

    for row_number, row in enumerate(rows, start=2):

        if len(row) == expected_columns:
            continue

        classification = classify_row(
            row,
            expected_columns,
        )

        classification_name = classification[
            "classification"
        ]

        classification_counts[
            classification_name
        ] += 1

        inconsistent_rows.append(
            {
                "row_number": row_number,
                "expected_columns": expected_columns,
                "actual_columns": len(row),
                "column_difference": (
                    len(row) - expected_columns
                ),
                "classification": classification,
                "columns": map_row_columns(
                    header,
                    row,
                ),
                "original_row": row,
            }
        )

    return {
        "file": str(
            path.relative_to(PROJECT_ROOT)
        ),
        "rows": len(rows),
        "expected_columns": expected_columns,
        "column_names": header,
        "inconsistent_row_count": len(
            inconsistent_rows
        ),
        "classification_counts": dict(
            classification_counts
        ),
        "inconsistent_rows": inconsistent_rows,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    if not CSV_DIR.exists():
        raise FileNotFoundError(
            f"CSV directory not found: {CSV_DIR}"
        )

    CSV_PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    csv_files = sorted(
        CSV_DIR.glob("*.csv")
    )

    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in: {CSV_DIR}"
        )

    results = []

    total_rows = 0
    total_inconsistent_rows = 0

    overall_classifications = Counter()

    print()
    print("# FBR CSV ROW INVESTIGATION")
    print()

    for path in csv_files:

        result = investigate_file(path)

        results.append(result)

        total_rows += result["rows"]

        total_inconsistent_rows += result[
            "inconsistent_row_count"
        ]

        overall_classifications.update(
            result["classification_counts"]
        )

        print(
            f"{path.name}"
            f" | inconsistent="
            f"{result['inconsistent_row_count']}"
        )

        if result["classification_counts"]:
            for (
                classification,
                count,
            ) in result["classification_counts"].items():

                print(
                    f"    {classification}: {count}"
                )

    report = {
        "report_type": (
            "FBR CSV Row-Level Investigation"
        ),
        "purpose": (
            "Investigate structural CSV anomalies "
            "without modifying raw source data."
        ),
        "source_directory": str(
            CSV_DIR.relative_to(PROJECT_ROOT)
        ),
        "summary": {
            "files": len(csv_files),
            "total_rows": total_rows,
            "total_inconsistent_rows": (
                total_inconsistent_rows
            ),
            "classification_counts": dict(
                overall_classifications
            ),
        },
        "files": results,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("## Summary")
    print(
        f"CSV files              : {len(csv_files)}"
    )
    print(
        f"Total rows             : {total_rows}"
    )
    print(
        "Inconsistent rows      : "
        f"{total_inconsistent_rows}"
    )

    print()
    print("## Root Cause Classification")

    for (
        classification,
        count,
    ) in overall_classifications.items():

        print(
            f"{classification:<35}: {count}"
        )

    print()
    print("# ROW INVESTIGATION COMPLETE")
    print()
    print(f"Report: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()