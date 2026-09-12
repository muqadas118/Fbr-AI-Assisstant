from __future__ import annotations

import csv
import json
import re
from pathlib import Path

# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

RAW_CSV_DIR = DATA_DIR / "raw" / "03-csv"

PROFILE_DIR = DATA_DIR / "profile"

INVESTIGATION_FILE = PROFILE_DIR / "csv_row_investigation.json"

INCOME_OUTPUT = PROFILE_DIR / "income-tax-slabs_cleaned.csv"

PENALTIES_OUTPUT = PROFILE_DIR / "penalties_cleaned.csv"


# ============================================================
# EXPECTED HEADERS
# ============================================================

INCOME_HEADER = [
    "taxpayer_type",
    "slab_from",
    "slab_to",
    "fixed_amount",
    "rate",
    "rate_applies_on",
    "notes",
    "source",
    "last_updated",
]

PENALTIES_HEADER = [
    "domain",
    "serial_no",
    "offence",
    "penalty",
    "penalty_details",
    "legal_reference",
    "source",
    "last_updated",
]


# ============================================================
# REGEX / IDENTIFICATION HELPERS
# ============================================================

DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}$"
)

INCOME_SOURCE_PATTERN = re.compile(
    r"^(ITO|FA\d{4})",
    re.IGNORECASE,
)

LEGAL_REFERENCE_PATTERN = re.compile(
    r"^(ITO 2001|STA 1990)",
    re.IGNORECASE,
)

PENALTY_SOURCE_PATTERN = re.compile(
    r"^(FBR sec|STA 1990)",
    re.IGNORECASE,
)


# ============================================================
# BASIC CSV FUNCTIONS
# ============================================================

def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
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


def write_csv(
    path: Path,
    header: list[str],
    rows: list[list[str]],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.writer(file)

        writer.writerow(header)

        writer.writerows(rows)


# ============================================================
# STRING HELPERS
# ============================================================

def strip_value(value: str) -> str:
    return value.strip()


def join_with_comma(values: list[str]) -> str:
    return ",".join(
        value.strip()
        for value in values
        if value.strip() != ""
    )


def is_date(value: str) -> bool:
    return bool(
        DATE_PATTERN.fullmatch(
            value.strip()
        )
    )


def is_legal_reference(value: str) -> bool:
    return bool(
        LEGAL_REFERENCE_PATTERN.match(
            value.strip()
        )
    )


def is_penalty_source(value: str) -> bool:
    return bool(
        PENALTY_SOURCE_PATTERN.match(
            value.strip()
        )
    )


def is_income_source(value: str) -> bool:
    return bool(
        INCOME_SOURCE_PATTERN.match(
            value.strip()
        )
    )


# ============================================================
# LOAD INVESTIGATION REPORT
# ============================================================

def load_problematic_rows() -> dict[str, set[int]]:
    """
    Reads the existing investigation report.

    The actual report structure is:

    {
        "summary": {...},
        "files": [
            {
                "file": "...",
                "problematic_rows": [...]
            }
        ]
    }
    """

    if not INVESTIGATION_FILE.exists():
        raise FileNotFoundError(
            "Could not find:\n"
            f"{INVESTIGATION_FILE}"
        )

    with INVESTIGATION_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:

        report = json.load(file)

    problematic_rows: dict[str, set[int]] = {}

    for file_info in report.get(
        "files",
        [],
    ):

        file_path = Path(
            file_info["file"]
        )

        file_name = file_path.name

        row_numbers = {
            item["row_number"]
            for item in file_info.get(
                "problematic_rows",
                [],
            )
        }

        problematic_rows[file_name] = row_numbers

    return problematic_rows


# ============================================================
# FIND INCOME TAX SOURCE / DATE
# ============================================================

def locate_income_tail(
    row: list[str],
) -> tuple[int, int]:
    """
    Find:

        source
        last_updated

    from the right side of a malformed row.

    last_updated is always an ISO date.

    source is the field immediately before it,
    and starts with either ITO or FA.
    """

    if not row:
        raise ValueError(
            "Empty income-tax row."
        )

    date_index = None

    for index in range(
        len(row) - 1,
        -1,
        -1,
    ):

        if is_date(row[index]):

            date_index = index
            break

    if date_index is None:
        raise ValueError(
            "Could not locate last_updated date "
            f"in row:\n{row}"
        )

    source_index = None

    # Search backwards before the date.
    for index in range(
        date_index - 1,
        4,
        -1,
    ):

        if is_income_source(
            row[index]
        ):

            source_index = index
            break

    if source_index is None:
        raise ValueError(
            "Could not locate source in income-tax row:\n"
            f"{row}"
        )

    return source_index, date_index


# ============================================================
# CLEAN INCOME-TAX ROW
# ============================================================

def clean_income_tax_row(
    row: list[str],
) -> list[str]:
    """
    Expected:

    taxpayer_type
    slab_from
    slab_to
    fixed_amount
    rate
    rate_applies_on
    notes
    source
    last_updated

    The malformed rows lost quotation marks around values
    such as:

        amount exceeding Rs 1,200,000

    or:

        Fixed Rs 2,000

    We restore the split fragments by rebuilding everything
    between the first five columns and source/date.
    """

    # Already valid.
    if len(row) == len(INCOME_HEADER):
        return [
            value.strip()
            for value in row
        ]

    if len(row) < len(INCOME_HEADER):
        raise ValueError(
            "Income-tax row has too few columns:\n"
            f"{row}"
        )

    # First five columns are stable.
    first_five = [
        value.strip()
        for value in row[:5]
    ]

    source_index, date_index = locate_income_tail(
        row
    )

    source = row[source_index].strip()

    last_updated = row[date_index].strip()

    # Everything between rate and source belongs to:
    # rate_applies_on + notes
    middle = [
        value.strip()
        for value in row[5:source_index]
    ]

    if not middle:
        raise ValueError(
            "No rate/notes content found:\n"
            f"{row}"
        )

    # --------------------------------------------------------
    # The rate_applies_on field is usually:
    #
    # amount exceeding Rs 1,200,000
    #
    # or:
    #
    # —
    #
    # Detect it first.
    # --------------------------------------------------------

    if middle[0] == "—":

        rate_applies_on = "—"

        notes = join_with_comma(
            middle[1:]
        )

    else:

        # Find the point where notes begin.
        #
        # Known patterns in this dataset:
        #
        # FA2025
        # FA2024
        # Division
        # Section
        # Budget
        # Fixed
        #
        # But "Budget" can be inside the notes after
        # FA2025, so FA/Division/Fixed are better anchors.
        # ----------------------------------------------------

        note_start = None

        for index, value in enumerate(
            middle
        ):

            if (
                value.startswith("FA2025")
                or value.startswith("FA2024")
                or value.startswith("Division ")
                or value.startswith("Section ")
                or value.startswith("Fixed ")
            ):
                note_start = index
                break

        if note_start is None:

            # No notes detected.
            #
            # Entire middle belongs to
            # rate_applies_on.
            rate_applies_on = join_with_comma(
                middle
            )

            notes = ""

        else:

            rate_applies_on = join_with_comma(
                middle[:note_start]
            )

            notes = join_with_comma(
                middle[note_start:]
            )

    cleaned = first_five + [
        rate_applies_on,
        notes,
        source,
        last_updated,
    ]

    if len(cleaned) != len(INCOME_HEADER):
        raise ValueError(
            "Income-tax cleaning produced "
            f"{len(cleaned)} columns instead of "
            f"{len(INCOME_HEADER)}:\n{cleaned}"
        )

    return cleaned


# ============================================================
# FIND PENALTY TAIL
# ============================================================

def locate_penalty_tail(
    row: list[str],
) -> tuple[int, int, int]:
    """
    Locate:

        legal_reference
        source
        last_updated

    from the right side.

    Example:

        ...,
        ITO 2001 sec 182(1), Table S.No.1,
        FBR sec 182 page,
        2026-08-01

    """

    if len(row) < len(PENALTIES_HEADER):
        raise ValueError(
            "Penalty row is too short:\n"
            f"{row}"
        )

    # --------------------------------------------------------
    # last_updated
    # --------------------------------------------------------

    date_index = None

    for index in range(
        len(row) - 1,
        -1,
        -1,
    ):

        if is_date(row[index]):

            date_index = index
            break

    if date_index is None:
        raise ValueError(
            "Could not locate last_updated in penalty row:\n"
            f"{row}"
        )

    # --------------------------------------------------------
    # source
    # --------------------------------------------------------

    source_index = None

    for index in range(
        date_index - 1,
        2,
        -1,
    ):

        if is_penalty_source(
            row[index]
        ):

            source_index = index
            break

    if source_index is None:
        raise ValueError(
            "Could not locate source in penalty row:\n"
            f"{row}"
        )

    # --------------------------------------------------------
    # legal_reference
    # --------------------------------------------------------

    legal_index = None

    for index in range(
        source_index - 1,
        2,
        -1,
    ):

        if is_legal_reference(
            row[index]
        ):

            legal_index = index
            break

    if legal_index is None:
        raise ValueError(
            "Could not locate legal_reference "
            f"in penalty row:\n{row}"
        )

    return (
        legal_index,
        source_index,
        date_index,
    )


# ============================================================
# CLEAN PENALTY ROW
# ============================================================

def clean_penalty_row(
    row: list[str],
) -> list[str]:
    """
    Expected:

    domain
    serial_no
    offence
    penalty
    penalty_details
    legal_reference
    source
    last_updated
    """

    # Already valid.
    if len(row) == len(PENALTIES_HEADER):
        return [
            value.strip()
            for value in row
        ]

    if len(row) < len(PENALTIES_HEADER):
        raise ValueError(
            "Penalty row has too few columns:\n"
            f"{row}"
        )

    # First three are stable.
    first_three = [
        value.strip()
        for value in row[:3]
    ]

    (
        legal_index,
        source_index,
        date_index,
    ) = locate_penalty_tail(
        row
    )

    legal_reference = row[
        legal_index
    ].strip()

    source = row[
        source_index
    ].strip()

    last_updated = row[
        date_index
    ].strip()

    # Everything between offence and legal reference
    # belongs to:
    #
    # penalty
    # penalty_details
    #
    middle = [
        value.strip()
        for value in row[3:legal_index]
    ]

    if not middle:
        raise ValueError(
            "No penalty data found:\n"
            f"{row}"
        )

    # --------------------------------------------------------
    # Determine where penalty_details begins.
    #
    # In this dataset, penalty starts from the first field.
    # A penalty may itself be comma-split:
    #
    #   Rs 5
    #   000 or Rs 2
    #   500/day
    #
    # Therefore we collect fragments until we reach the
    # beginning of the details.
    #
    # Details usually repeat the amount or start with:
    #
    #   Rs
    #   Flat
    #   Penalty
    #   Goods
    #   0.1%
    #   ...
    #
    # We use structural detection plus known patterns.
    # --------------------------------------------------------

    detail_start = None

    # A second description often starts with the same
    # semantic expression as penalty.
    #
    # We compare the fragments and detect the first place
    # where a new amount/expression begins after the
    # initial penalty expression.

    for index in range(
        1,
        len(middle),
    ):

        value = middle[index]

        previous = middle[index - 1]

        # Common explicit beginnings of details.
        if (
            value.startswith("Flat ")
            or value.startswith("Penalty ")
            or value.startswith("Goods ")
            or value.startswith("Confiscation ")
            or value.startswith("0.1%")
            or value.startswith("Rs ")
            or value.startswith("Up to Rs ")
        ):

            # Do not split a number such as:
            #
            # Rs 5
            # 000
            #
            # because "000" does not start with Rs.
            #
            # Also do not split:
            #
            # Rs 5
            # 000 or 3%
            #
            # at "000".
            if not value.isdigit():
                detail_start = index
                break

        # If the current field ends with something that
        # clearly completes a penalty expression, and the
        # next field starts another monetary expression,
        # that's a good boundary.
        if (
            index > 0
            and previous.endswith("%")
            and (
                value.startswith("Rs ")
                or value.startswith("0.1%")
            )
        ):
            detail_start = index
            break

    # --------------------------------------------------------
    # Dataset-specific fallback patterns.
    # --------------------------------------------------------

    if detail_start is None:

        # Most rows have a simple pattern:
        #
        # penalty fragments
        # details fragments
        #
        # We can recognize the boundary when a new monetary
        # phrase appears after the first completed amount.
        #

        for index in range(
            1,
            len(middle),
        ):

            value = middle[index]

            if (
                value.startswith("Rs ")
                or value.startswith("100%")
                or value.startswith("Confiscation ")
                or value.startswith("Up to Rs ")
            ):

                # Ignore obvious continuation fragments.
                if value.strip() in {
                    "Rs 5",
                    "Rs 10",
                    "Rs 25",
                    "Rs 50",
                    "Rs 100",
                    "Rs 300",
                    "Rs 500",
                    "Rs 1",
                }:
                    continue

                detail_start = index
                break

    # --------------------------------------------------------
    # Final fallback
    # --------------------------------------------------------

    if detail_start is None:

        # The first logical field is penalty.
        # We preserve all remaining content in details.
        #
        # This is safer than inventing a split.
        detail_start = 1

    penalty = join_with_comma(
        middle[:detail_start]
    )

    penalty_details = join_with_comma(
        middle[detail_start:]
    )

    cleaned = first_three + [
        penalty,
        penalty_details,
        legal_reference,
        source,
        last_updated,
    ]

    if len(cleaned) != len(PENALTIES_HEADER):
        raise ValueError(
            "Penalty cleaning produced "
            f"{len(cleaned)} columns instead of "
            f"{len(PENALTIES_HEADER)}:\n{cleaned}"
        )

    return cleaned


# ============================================================
# VALIDATION
# ============================================================

def validate_rows(
    file_name: str,
    header: list[str],
    rows: list[list[str]],
) -> None:

    expected = len(header)

    bad_rows = []

    for row_number, row in enumerate(
        rows,
        start=2,
    ):

        if len(row) != expected:

            bad_rows.append(
                (
                    row_number,
                    len(row),
                )
            )

    if bad_rows:

        print(
            f"\nERROR: {file_name}"
        )

        for row_number, actual in bad_rows:

            print(
                f"  Row {row_number}: "
                f"{actual} columns "
                f"(expected {expected})"
            )

        raise ValueError(
            f"Validation failed for {file_name}"
        )

    print(
        f"OK: {file_name}"
    )

    print(
        f"   Rows    : {len(rows)}"
    )

    print(
        f"   Columns : {expected}"
    )


# ============================================================
# PROCESS INCOME TAX
# ============================================================

def process_income_tax(
    problematic_rows: set[int],
) -> None:

    input_file = (
        RAW_CSV_DIR
        / "income-tax-slabs.csv"
    )

    header, raw_rows = read_csv(
        input_file
    )

    if header != INCOME_HEADER:

        raise ValueError(
            "Unexpected income-tax header:\n"
            f"{header}"
        )

    cleaned_rows = []

    repaired = 0

    for row_number, row in enumerate(
        raw_rows,
        start=2,
    ):

        if row_number in problematic_rows:

            cleaned_rows.append(
                clean_income_tax_row(
                    row
                )
            )

            repaired += 1

        else:

            # Already valid rows are copied exactly,
            # except for surrounding whitespace.
            cleaned_rows.append(
                [
                    value.strip()
                    for value in row
                ]
            )

    validate_rows(
        "income-tax-slabs.csv",
        header,
        cleaned_rows,
    )

    write_csv(
        INCOME_OUTPUT,
        INCOME_HEADER,
        cleaned_rows,
    )

    print(
        f"   Repaired: {repaired}"
    )

    print(
        f"   Output  : {INCOME_OUTPUT}"
    )


# ============================================================
# PROCESS PENALTIES
# ============================================================

def process_penalties(
    problematic_rows: set[int],
) -> None:

    input_file = (
        RAW_CSV_DIR
        / "penalties.csv"
    )

    header, raw_rows = read_csv(
        input_file
    )

    if header != PENALTIES_HEADER:

        raise ValueError(
            "Unexpected penalties header:\n"
            f"{header}"
        )

    cleaned_rows = []

    repaired = 0

    for row_number, row in enumerate(
        raw_rows,
        start=2,
    ):

        if row_number in problematic_rows:

            cleaned_rows.append(
                clean_penalty_row(
                    row
                )
            )

            repaired += 1

        else:

            cleaned_rows.append(
                [
                    value.strip()
                    for value in row
                ]
            )

    validate_rows(
        "penalties.csv",
        header,
        cleaned_rows,
    )

    write_csv(
        PENALTIES_OUTPUT,
        PENALTIES_HEADER,
        cleaned_rows,
    )

    print(
        f"   Repaired: {repaired}"
    )

    print(
        f"   Output  : {PENALTIES_OUTPUT}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print(
        "=" * 50
    )
    print(
        "FBR CSV CLEANING"
    )
    print(
        "=" * 50
    )
    print()

    problematic = load_problematic_rows()

    income_rows = problematic.get(
        "income-tax-slabs.csv",
        set(),
    )

    penalty_rows = problematic.get(
        "penalties.csv",
        set(),
    )

    print(
        f"income-tax-slabs.csv : "
        f"{len(income_rows)} problematic rows"
    )

    print(
        f"penalties.csv        : "
        f"{len(penalty_rows)} problematic rows"
    )

    print()

    # --------------------------------------------------------
    # CLEAN INCOME TAX
    # --------------------------------------------------------

    process_income_tax(
        income_rows
    )

    print()

    # --------------------------------------------------------
    # CLEAN PENALTIES
    # --------------------------------------------------------

    process_penalties(
        penalty_rows
    )

    print()
    print(
        "=" * 50
    )
    print(
        "CLEANING COMPLETE"
    )
    print(
        "=" * 50
    )
    print()


if __name__ == "__main__":
    main()