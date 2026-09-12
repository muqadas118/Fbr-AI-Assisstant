from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "02-jsonl"
CLEAN_DIR = PROJECT_ROOT / "data" / "profile" / "jsonl"


REQUIRED_FIELDS = [
    "id",
    "question",
    "answer",
    "source",
    "section",
    "language",
    "difficulty",
    "last_updated",
]


def read_jsonl(path: Path) -> list[dict]:
    records = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        for line_number, line in enumerate(
            file,
            start=1,
        ):

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path.name}, line {line_number}: "
                    f"invalid JSON: {error}"
                )

            if not isinstance(record, dict):
                raise TypeError(
                    f"{path.name}, line {line_number}: "
                    "record is not a JSON object"
                )

            records.append(record)

    return records


def validate_records(
    filename: str,
    records: list[dict],
) -> list[str]:

    problems = []
    seen_ids = set()

    for record_number, record in enumerate(
        records,
        start=1,
    ):

        for field in REQUIRED_FIELDS:

            if field not in record:
                problems.append(
                    f"record {record_number}: "
                    f"missing '{field}'"
                )

        for field in (
            "id",
            "question",
            "answer",
        ):

            if field not in record:
                continue

            value = record[field]

            if not isinstance(value, str):
                problems.append(
                    f"record {record_number}: "
                    f"'{field}' is not a string"
                )

            elif not value.strip():
                problems.append(
                    f"record {record_number}: "
                    f"'{field}' is empty"
                )

        if "id" in record:

            record_id = str(
                record["id"]
            )

            if record_id in seen_ids:

                problems.append(
                    f"record {record_number}: "
                    f"duplicate id '{record_id}'"
                )

            seen_ids.add(record_id)

    return problems


def main():

    print()
    print("=" * 60)
    print("FBR JSONL VALIDATION")
    print("=" * 60)
    print()

    raw_files = {
        file.name
        for file in RAW_DIR.glob("*.jsonl")
    }

    clean_files = {
        file.name
        for file in CLEAN_DIR.glob("*.jsonl")
    }

    print(
        f"Raw JSONL files     : {len(raw_files)}"
    )

    print(
        f"Cleaned JSONL files : {len(clean_files)}"
    )

    missing = sorted(
        raw_files - clean_files
    )

    extra = sorted(
        clean_files - raw_files
    )

    print(
        f"Missing files       : {len(missing)}"
    )

    print(
        f"Extra files         : {len(extra)}"
    )

    problems_found = 0
    raw_total = 0
    clean_total = 0

    for filename in sorted(raw_files):

        raw_path = RAW_DIR / filename
        clean_path = CLEAN_DIR / filename

        if not clean_path.exists():
            continue

        try:
            raw_records = read_jsonl(
                raw_path
            )

            clean_records = read_jsonl(
                clean_path
            )

        except (OSError, TypeError, ValueError) as error:

            print()
            print(
                f"ERROR: {filename}"
            )
            print(error)

            problems_found += 1
            continue

        raw_count = len(raw_records)
        clean_count = len(clean_records)

        raw_total += raw_count
        clean_total += clean_count

        if raw_count != clean_count:

            print()
            print(
                f"COUNT MISMATCH: {filename}"
            )

            print(
                f"  Raw     : {raw_count}"
            )

            print(
                f"  Cleaned : {clean_count}"
            )

            problems_found += 1

        record_problems = validate_records(
            filename,
            clean_records,
        )

        if record_problems:

            print()
            print(
                f"PROBLEMS: {filename}"
            )

            for problem in record_problems[:20]:

                print(
                    f"  - {problem}"
                )

            problems_found += len(
                record_problems
            )

    print()
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    print(
        f"Raw files checked    : {len(raw_files)}"
    )

    print(
        f"Cleaned files checked: {len(clean_files)}"
    )

    print(
        f"Raw records          : {raw_total}"
    )

    print(
        f"Cleaned records      : {clean_total}"
    )

    print(
        f"Problems found       : {problems_found}"
    )

    print(
        f"Missing files        : {len(missing)}"
    )

    print(
        f"Extra files          : {len(extra)}"
    )

    print()

    if (
        not missing
        and not extra
        and raw_total == clean_total
        and problems_found == 0
    ):

        print(
            "ALL JSONL VALIDATIONS PASSED"
        )

    else:

        print(
            "JSONL VALIDATION FAILED"
        )

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()