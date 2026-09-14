from __future__ import annotations

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".csv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


def count_json_records(path: Path) -> int | None:
    """Count JSON/JSONL records without modifying the source file."""
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8-sig") as file:
                return sum(1 for line in file if line.strip())

        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)

        if isinstance(data, list):
            return len(data)

        if isinstance(data, dict):
            return 1

        return None

    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def count_csv_rows(path: Path) -> int | None:
    """Count CSV data rows without modifying the source file."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            rows = list(reader)

        if not rows:
            return 0

        # First row is treated as the header.
        return max(len(rows) - 1, 0)

    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def inspect_file(path: Path) -> dict:
    """Return basic inventory information for one file."""
    relative_path = path.relative_to(RAW_DATA_DIR)

    result = {
        "file_name": path.name,
        "relative_path": relative_path.as_posix(),
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
    }

    extension = path.suffix.lower()

    if extension in {".json", ".jsonl"}:
        result["record_count"] = count_json_records(path)

    elif extension == ".csv":
        result["row_count"] = count_csv_rows(path)

    return result


def scan_raw_data() -> list[dict]:
    """Recursively scan all supported files in the raw data directory."""
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(
            f"Raw data directory does not exist: {RAW_DATA_DIR}"
        )

    files = [
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    files.sort(key=lambda path: path.relative_to(RAW_DATA_DIR).as_posix().lower())

    return [inspect_file(path) for path in files]


def print_inventory(inventory: list[dict]) -> None:
    """Print a compact inventory summary."""
    print("\nFBR DATA INVENTORY")
    print("=" * 60)

    total_files = len(inventory)
    total_size = sum(item["size_bytes"] for item in inventory)

    print(f"Total supported files : {total_files}")
    print(f"Total size            : {total_size:,} bytes")

    print("\nFiles by type")
    print("-" * 60)

    extension_counts: dict[str, int] = {}

    for item in inventory:
        extension = item["extension"] or "[no extension]"
        extension_counts[extension] = extension_counts.get(extension, 0) + 1

    for extension, count in sorted(extension_counts.items()):
        print(f"{extension:10} : {count}")

    print("\nFiles")
    print("-" * 60)

    for item in inventory:
        extra = ""

        if "record_count" in item:
            extra = f" | records={item['record_count']}"

        elif "row_count" in item:
            extra = f" | rows={item['row_count']}"

        print(
            f"{item['relative_path']} "
            f"| {item['size_bytes']:,} bytes{extra}"
        )


def main() -> None:
    inventory = scan_raw_data()
    print_inventory(inventory)


if __name__ == "__main__":
    main()