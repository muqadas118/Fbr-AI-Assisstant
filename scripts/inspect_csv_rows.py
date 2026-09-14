from __future__ import annotations

import csv
import json
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_CSV_DIR = DATA_DIR / "raw" / "03-csv"
PROFILE_DIR = DATA_DIR / "profile"

INPUT_REPORT = PROFILE_DIR / "csv_inspection.json"
OUTPUT_REPORT = PROFILE_DIR / "csv_row_investigation.json"


# ============================================================
# HELPERS
# ============================================================

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


def inspect_problematic_rows(
    file_info: dict,
) -> dict:
    """Inspect rows whose column count differs from the header."""

    relative_path = Path(file_info["file"])
    csv_path = PROJECT_ROOT / relative_path

    header, rows = read_csv(csv_path)

    expected_columns = len(header)

    problematic_rows = []

    for row_number, row in enumerate(rows, start=2):
        actual_columns = len(row)

        if actual_columns != expected_columns:
            row_data = []

            max_columns = max(
                expected_columns,
                actual_columns,
            )

            for index in range(max_columns):
                column_name = (
                    header[index]
                    if index < expected_columns
                    else f"UNEXPECTED_COLUMN_{index + 1}"
                )

                value = (
                    row[index]
                    if index < actual_columns
                    else None
                )

                row_data.append(
                    {
                        "column_position": index + 1,
                        "column": column_name,
                        "value": value,
                    }
                )

            problematic_rows.append(
                {
                    "row_number": row_number,
                    "expected_columns": expected_columns,
                    "actual_columns": actual_columns,
                    "difference": actual_columns - expected_columns,
                    "values": row_data,
                }
            )

    return {
        "file": file_info["file"],
        "expected_columns": expected_columns,
        "header": header,
        "problematic_row_count": len(problematic_rows),
        "problematic_rows": problematic_rows,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    if not INPUT_REPORT.exists():
        raise FileNotFoundError(
            f"Inspection report not found: {INPUT_REPORT}"
        )

    PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    inspection = json.loads(
        INPUT_REPORT.read_text(
            encoding="utf-8"
        )
    )

    files_with_problems = [
        file_info
        for file_info in inspection["files"]
        if file_info["inconsistent_rows"]
    ]

    if not files_with_problems:
        print()
        print("# CSV ROW INVESTIGATION")
        print()
        print("No inconsistent rows found.")
        return

    investigations = []

    total_problematic_rows = 0

    print()
    print("# FBR CSV ROW INVESTIGATION")
    print()

    for file_info in files_with_problems:
        result = inspect_problematic_rows(file_info)

        investigations.append(result)

        count = result["problematic_row_count"]
        total_problematic_rows += count

        print(
            f"{Path(result['file']).name}"
            f" | problematic rows={count}"
            f" | expected columns={result['expected_columns']}"
        )

    report = {
        "summary": {
            "files_investigated": len(investigations),
            "total_problematic_rows": total_problematic_rows,
        },
        "files": investigations,
    }

    OUTPUT_REPORT.write_text(
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
        f"Files investigated     : {len(investigations)}"
    )
    print(
        f"Problematic rows       : {total_problematic_rows}"
    )

    print()
    print("# ROW INVESTIGATION COMPLETE")
    print()
    print(f"Report: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()