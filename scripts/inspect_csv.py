from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROFILE_DIR = DATA_DIR / "profile"
OUTPUT_FILE = PROFILE_DIR / "csv_inspection.json"

CSV_DIR = DATA_DIR / "raw" / "03-csv"


# ============================================================
# HELPERS
# ============================================================

def normalize_column_name(value: str) -> str:
    """Normalize a column name for comparison."""
    return " ".join(value.strip().lower().split())


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read a CSV without modifying it."""
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
# FILE INSPECTION
# ============================================================

def inspect_file(path: Path) -> dict:
    header, rows = read_csv(path)

    expected_columns = len(header)

    column_names = [
        column.strip()
        for column in header
    ]

    normalized_columns = [
        normalize_column_name(column)
        for column in header
    ]

    missing_by_column = Counter()

    inconsistent_rows = []

    row_lengths = Counter()

    for row_number, row in enumerate(rows, start=2):
        row_lengths[len(row)] += 1

        if len(row) != expected_columns:
            inconsistent_rows.append(
                {
                    "row_number": row_number,
                    "expected_columns": expected_columns,
                    "actual_columns": len(row),
                    "row": row,
                }
            )

        for index, column in enumerate(column_names):
            value = row[index] if index < len(row) else ""

            if not str(value).strip():
                missing_by_column[column] += 1

    # Detect duplicate column names
    duplicate_columns = [
        column
        for column, count in Counter(normalized_columns).items()
        if count > 1
    ]

    # Non-empty value statistics
    value_counts = {}

    for index, column in enumerate(column_names):
        values = []

        for row in rows:
            if index < len(row):
                value = row[index].strip()

                if value:
                    values.append(value)

        counter = Counter(values)

        value_counts[column] = {
            "unique_values": len(counter),
            "top_values": [
                {
                    "value": value,
                    "count": count,
                }
                for value, count in counter.most_common(5)
            ],
        }

    return {
        "file": str(path.relative_to(PROJECT_ROOT)),
        "rows": len(rows),
        "columns": expected_columns,
        "column_names": column_names,
        "duplicate_columns": duplicate_columns,
        "missing_values_by_column": dict(missing_by_column),
        "inconsistent_rows": inconsistent_rows,
        "row_length_distribution": {
            str(length): count
            for length, count in sorted(row_lengths.items())
        },
        "value_statistics": value_counts,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    if not CSV_DIR.exists():
        raise FileNotFoundError(
            f"CSV directory not found: {CSV_DIR}"
        )

    PROFILE_DIR.mkdir(
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
    total_missing_values = 0

    print()
    print("# FBR CSV STRUCTURAL INSPECTION")
    print()

    for path in csv_files:
        result = inspect_file(path)
        results.append(result)

        total_rows += result["rows"]
        total_inconsistent_rows += len(
            result["inconsistent_rows"]
        )

        total_missing_values += sum(
            result["missing_values_by_column"].values()
        )

        print(
            f"{path.name}"
            f" | rows={result['rows']}"
            f" | columns={result['columns']}"
            f" | inconsistent={len(result['inconsistent_rows'])}"
        )

    report = {
        "summary": {
            "files": len(csv_files),
            "total_rows": total_rows,
            "total_inconsistent_rows": total_inconsistent_rows,
            "total_missing_values": total_missing_values,
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
    print(f"CSV files              : {len(csv_files)}")
    print(f"Total rows             : {total_rows}")
    print(
        "Inconsistent rows      : "
        f"{total_inconsistent_rows}"
    )
    print(
        "Missing values         : "
        f"{total_missing_values}"
    )

    print()
    print("# INSPECTION COMPLETE")
    print()
    print(f"Report: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()