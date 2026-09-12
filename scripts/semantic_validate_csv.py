from __future__ import annotations

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "data" / "profile"


def read_csv(path: Path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)
        return list(reader)


def is_date(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            value.strip(),
        )
    )


def validate_income_tax() -> bool:

    path = (
        PROFILE_DIR
        / "income-tax-slabs_cleaned.csv"
    )

    rows = read_csv(path)

    problems = []

    for row_number, row in enumerate(
        rows,
        start=2,
    ):

        if not row["taxpayer_type"].strip():
            problems.append(
                (row_number, "empty taxpayer_type")
            )

        if not row["slab_from"].strip():
            problems.append(
                (row_number, "empty slab_from")
            )

        if not row["slab_to"].strip():
            problems.append(
                (row_number, "empty slab_to")
            )

        if not row["rate"].strip():
            problems.append(
                (row_number, "empty rate")
            )

        if not row["source"].strip():
            problems.append(
                (row_number, "empty source")
            )

        if not is_date(row["last_updated"]):
            problems.append(
                (
                    row_number,
                    f"invalid date: "
                    f"{row['last_updated']}",
                )
            )

    print()
    print("=" * 60)
    print("INCOME TAX SEMANTIC VALIDATION")
    print("=" * 60)

    if problems:

        print(
            f"Problems found: {len(problems)}"
        )

        for row_number, problem in problems[:30]:

            print(
                f"Row {row_number}: {problem}"
            )

        return False

    print(
        f"Rows checked: {len(rows)}"
    )

    print("PASS")

    return True


def validate_penalties() -> bool:

    path = (
        PROFILE_DIR
        / "penalties_cleaned.csv"
    )

    rows = read_csv(path)

    problems = []

    for row_number, row in enumerate(
        rows,
        start=2,
    ):

        if not row["domain"].strip():
            problems.append(
                (row_number, "empty domain")
            )

        if not row["offence"].strip():
            problems.append(
                (row_number, "empty offence")
            )

        if not row["penalty"].strip():
            problems.append(
                (row_number, "empty penalty")
            )

        if not row["legal_reference"].strip():
            problems.append(
                (
                    row_number,
                    "empty legal_reference",
                )
            )

        if not row["source"].strip():
            problems.append(
                (row_number, "empty source")
            )

        if not is_date(row["last_updated"]):
            problems.append(
                (
                    row_number,
                    f"invalid date: "
                    f"{row['last_updated']}",
                )
            )

    print()
    print("=" * 60)
    print("PENALTIES SEMANTIC VALIDATION")
    print("=" * 60)

    if problems:

        print(
            f"Problems found: {len(problems)}"
        )

        for row_number, problem in problems[:30]:

            print(
                f"Row {row_number}: {problem}"
            )

        return False

    print(
        f"Rows checked: {len(rows)}"
    )

    print("PASS")

    return True


def main():

    income_result = validate_income_tax()

    penalty_result = validate_penalties()

    print()
    print("=" * 60)

    if (
        income_result
        and penalty_result
    ):
        print(
            "ALL SEMANTIC VALIDATIONS PASSED"
        )
    else:
        print(
            "SEMANTIC VALIDATION FAILED"
        )

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()