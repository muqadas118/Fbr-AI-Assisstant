from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "02-jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "profile" / "jsonl"


def load_jsonl(path: Path) -> list[dict]:
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
                raise TypeError(
                    f"{path.name}, line {line_number}: "
                    f"Invalid JSON: {error}"
                )

            if not isinstance(record, dict):
                raise TypeError(
                    f"{path.name}, line {line_number}: "
                    "JSON record is not an object."
                )

            records.append(record)

    return records


def validate_record(
    record: dict,
    filename: str,
    record_number: int,
) -> None:

    required_fields = [
        "id",
        "question",
        "answer",
        "source",
        "section",
        "language",
        "difficulty",
        "last_updated",
    ]

    for field in required_fields:

        if field not in record:
            raise ValueError(
                f"{filename}, record {record_number}: "
                f"missing required field '{field}'"
            )

        if record[field] is None:
            raise ValueError(
                f"{filename}, record {record_number}: "
                f"field '{field}' is null"
            )

    for field in [
        "id",
        "question",
        "answer",
    ]:

        if not isinstance(
            record[field],
            str,
        ):

            raise TypeError(
                f"{filename}, record {record_number}: "
                f"'{field}' must be a string"
            )

        if not record[field].strip():

            raise ValueError(
                f"{filename}, record {record_number}: "
                f"'{field}' is empty"
            )


def clean_record(record: dict) -> dict:
    """
    Conservative normalization.

    We do NOT change the factual content.
    We only normalize whitespace around string values.

    Lists and nested dictionaries are preserved.
    """

    cleaned = {}

    for key, value in record.items():

        if isinstance(value, str):

            cleaned[key] = value.strip()

        elif isinstance(value, list):

            cleaned[key] = [
                item.strip()
                if isinstance(item, str)
                else item
                for item in value
            ]

        elif isinstance(value, dict):

            cleaned[key] = {
                nested_key: (
                    nested_value.strip()
                    if isinstance(
                        nested_value,
                        str,
                    )
                    else nested_value
                )
                for nested_key, nested_value
                in value.items()
            }

        else:

            cleaned[key] = value

    return cleaned


def write_jsonl(
    path: Path,
    records: list[dict],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:

        for record in records:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(
                        ",",
                        ":",
                    ),
                )
                + "\n"
            )


def process_file(source: Path):

    records = load_jsonl(source)

    cleaned_records = []

    seen_ids = set()

    for record_number, record in enumerate(
        records,
        start=1,
    ):

        validate_record(
            record,
            source.name,
            record_number,
        )

        cleaned = clean_record(
            record
        )

        record_id = cleaned["id"]

        if record_id in seen_ids:

            raise ValueError(
                f"{source.name}, record "
                f"{record_number}: duplicate id "
                f"'{record_id}'"
            )

        seen_ids.add(record_id)

        cleaned_records.append(
            cleaned
        )

    destination = (
        OUTPUT_DIR / source.name
    )

    write_jsonl(
        destination,
        cleaned_records,
    )

    return len(records)


def main():

    print()
    print("=" * 60)
    print("FBR JSONL CLEANING")
    print("=" * 60)
    print()

    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Raw JSONL directory not found:\n{RAW_DIR}"
        )

    files = sorted(
        RAW_DIR.glob("*.jsonl")
    )

    print(
        f"JSONL files found: {len(files)}"
    )

    print()

    total_records = 0

    for source in files:

        count = process_file(source)

        total_records += count

        print(
            f"OK: {source.name} "
            f"-> {count} records"
        )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Files processed : {len(files)}"
    )

    print(
        f"Records processed: {total_records}"
    )

    print(
        f"Output folder   : {OUTPUT_DIR}"
    )

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()