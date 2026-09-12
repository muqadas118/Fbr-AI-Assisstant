from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "data" / "profile"


FILES = {
    "income-tax-slabs_cleaned.csv": 9,
    "penalties_cleaned.csv": 8,
}


def read_csv(path: Path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.reader(file)

        header = next(reader)
        rows = list(reader)

    return header, rows


def validate_file(
    filename: str,
    expected_columns: int,
) -> bool:

    path = PROFILE_DIR / filename

    print()
    print("=" * 60)
    print(filename)
    print("=" * 60)

    if not path.exists():
        print(f"ERROR: file not found: {path}")
        return False

    try:
        header, rows = read_csv(path)
    except Exception as error:
        print(f"ERROR reading file: {error}")
        return False

    print(f"Rows found    : {len(rows)}")
    print(f"Columns found : {len(header)}")
    print(f"Expected      : {expected_columns}")

    if len(header) != expected_columns:
        print(
            "FAIL: header has incorrect number of columns."
        )
        return False

    bad_rows = []

    empty_rows = []

    for row_number, row in enumerate(
        rows,
        start=2,
    ):

        if len(row) != expected_columns:
            bad_rows.append(
                (
                    row_number,
                    len(row),
                )
            )

        if all(
            not value.strip()
            for value in row
        ):
            empty_rows.append(row_number)

    print(
        f"Inconsistent rows : {len(bad_rows)}"
    )

    print(
        f"Completely empty rows : {len(empty_rows)}"
    )

    if bad_rows:

        print()
        print("BAD ROWS:")

        for row_number, column_count in bad_rows[:20]:
            print(
                f"  Row {row_number}: "
                f"{column_count} columns"
            )

        return False

    if empty_rows:

        print()
        print(
            "WARNING: completely empty rows found:"
        )

        for row_number in empty_rows[:20]:
            print(f"  Row {row_number}")

    print("PASS")

    return True


def main():

    print()
    print("# CLEANED CSV VALIDATION")
    print()

    results = []

    for filename, expected_columns in FILES.items():

        result = validate_file(
            filename,
            expected_columns,
        )

        results.append(result)

    print()
    print("=" * 60)

    if all(results):
        print("ALL CLEANED CSV FILES PASSED")
    else:
        print("SOME CLEANED CSV FILES FAILED")

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()