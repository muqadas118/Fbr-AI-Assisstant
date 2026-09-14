from __future__ import annotations
from collections import Counter
import csv
import hashlib
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "profile"

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

TOPIC_RULES = {
    "income_tax": [
        "income-tax",
        "income_tax",
        "income tax",
        "income",
        "ito",
        "return",
    ],
    "sales_tax": [
        "sales-tax",
        "sales_tax",
        "sales tax",
        "st-act",
        "sales",
    ],
    "withholding_tax": [
        "withholding",
        "wht",
    ],
    "customs": [
        "customs",
        "tariff",
        "dirbs",
    ],
    "federal_excise_duty": [
        "federal-excise",
        "federal_excise",
        "excise",
        "fed",
    ],
    "property_taxation": [
        "property",
        "valuation",
    ],
    "taxpayer_services": [
        "tax-assaan",
        "active-taxpayer",
        "atl",
        "register",
        "contact",
        "services",
        "payment",
        "refund",
        "forms",
    ],
    "penalties_and_appeals": [
        "penalt",
        "appeal",
    ],
    "budget_and_finance_acts": [
        "budget",
        "finance-act",
        "finance_act",
        "finance act",
    ],
}

LANGUAGE_RULES = {
    "roman_urdu": [
        "roman-urdu",
        "roman_urdu",
    ],
}


def normalize_name(value: str) -> str:
    """Normalize a filename/path component for rule matching."""
    value = value.lower()
    value = value.replace("_", "-")
    value = re.sub(r"[^a-z0-9\- ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def detect_topics(path: Path) -> list[str]:
    """Infer possible topics from the path and filename."""
    haystack = normalize_name(path.as_posix())

    matches = []

    for topic, keywords in TOPIC_RULES.items():
        if any(normalize_name(keyword) in haystack for keyword in keywords):
            matches.append(topic)

    return matches or ["uncategorized"]


def detect_language(path: Path) -> str:
    """Infer language only when there is a strong filename signal."""
    normalized = normalize_name(path.as_posix())

    for language, keywords in LANGUAGE_RULES.items():
        if any(normalize_name(keyword) in normalized for keyword in keywords):
            return language

    return "unknown"


def detect_source_category(path: Path) -> str:
    """Classify the source based on its directory and filename."""
    normalized = normalize_name(path.as_posix())

    if "04-source-docs" in normalized:
        return "source_document"

    if "02-jsonl" in normalized:
        return "qa_or_structured_knowledge"

    if "03-csv" in normalized:
        return "structured_table"

    if "01-markdown" in normalized:
        return "curated_guide"

    return "other"


def detect_content_type(path: Path) -> str:
    """Classify the technical content format."""
    extension = path.suffix.lower()

    if extension in {".md", ".txt"}:
        return "text"

    if extension in {".json", ".jsonl"}:
        return "json"

    if extension == ".csv":
        return "table"

    if extension == ".pdf":
        return "document"

    if extension in {".doc", ".docx"}:
        return "document"

    if extension in {".xls", ".xlsx"}:
        return "spreadsheet"

    return "unknown"


def detect_years(path: Path) -> list[int]:
    """Extract plausible years from the path and filename."""
    text = path.as_posix()

    years = {
        int(match)
        for match in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)
    }

    return sorted(years)


def calculate_sha256(path: Path) -> str:
    """Calculate a content hash for exact duplicate detection."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def count_json_records(path: Path) -> int | None:
    """Count JSON or JSONL records where possible."""
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

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None

    return None


def count_csv_rows(path: Path) -> int | None:
    """Count CSV data rows, excluding the header."""
    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.reader(file)

            row_count = 0

            for index, row in enumerate(reader):
                if index == 0:
                    continue

                if row:
                    row_count += 1

        return row_count

    except (
        OSError,
        UnicodeDecodeError,
        csv.Error,
    ):
        return None


def profile_file(path: Path) -> dict:
    """Create a non-destructive profile for one source file."""
    relative_path = path.relative_to(RAW_DATA_DIR)

    profile = {
        "file_name": path.name,
        "relative_path": relative_path.as_posix(),
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "source_category": detect_source_category(path),
        "content_type": detect_content_type(path),
        "topics": detect_topics(path),
        "language": detect_language(path),
        "years_detected": detect_years(path),
        "sha256": calculate_sha256(path),
    }

    extension = path.suffix.lower()

    if extension in {".json", ".jsonl"}:
        profile["record_count"] = count_json_records(path)

    elif extension == ".csv":
        profile["row_count"] = count_csv_rows(path)

    return profile


def scan_sources() -> list[dict]:
    """Profile all supported source files."""
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(
            f"Raw data directory does not exist: {RAW_DATA_DIR}"
        )

    files = [
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    files.sort(
        key=lambda path: path.relative_to(RAW_DATA_DIR)
        .as_posix()
        .lower()
    )

    return [profile_file(path) for path in files]


def find_exact_duplicates(profiles: list[dict]) -> dict[str, list[str]]:
    """Find files with identical binary content using SHA-256."""
    hashes: dict[str, list[str]] = {}

    for profile in profiles:
        hashes.setdefault(profile["sha256"], []).append(
            profile["relative_path"]
        )

    return {
        file_hash: paths
        for file_hash, paths in hashes.items()
        if len(paths) > 1
    }


def write_json(data: object, path: Path) -> None:
    """Write UTF-8 JSON with readable formatting."""
    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def write_csv(profiles: list[dict], path: Path) -> None:
    """Write the source catalog as CSV."""
    fieldnames = [
        "file_name",
        "relative_path",
        "extension",
        "size_bytes",
        "source_category",
        "content_type",
        "topics",
        "language",
        "years_detected",
        "record_count",
        "row_count",
        "sha256",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for profile in profiles:
            row = profile.copy()

            row["topics"] = ";".join(row["topics"])
            row["years_detected"] = ";".join(
                str(year)
                for year in row["years_detected"]
            )

            writer.writerow(
                {
                    field: row.get(field, "")
                    for field in fieldnames
                }
            )


def build_summary(
    profiles: list[dict],
    duplicates: dict[str, list[str]],
) -> dict:
    """Build high-level profiling statistics."""
    category_counts = Counter(
        profile["source_category"]
        for profile in profiles
    )

    extension_counts = Counter(
        profile["extension"]
        for profile in profiles
    )

    topic_counts = Counter()

    for profile in profiles:
        for topic in profile["topics"]:
            topic_counts[topic] += 1

    language_counts = Counter(
        profile["language"]
        for profile in profiles
    )

    return {
        "total_files": len(profiles),
        "total_size_bytes": sum(
            profile["size_bytes"]
            for profile in profiles
        ),
        "source_categories": dict(
            sorted(category_counts.items())
        ),
        "extensions": dict(
            sorted(extension_counts.items())
        ),
        "topics": dict(
            sorted(topic_counts.items())
        ),
        "languages": dict(
            sorted(language_counts.items())
        ),
        "exact_duplicate_groups": len(duplicates),
        "exact_duplicate_files": sum(
            len(paths)
            for paths in duplicates.values()
        ),
    }


def main() -> None:
    profiles = scan_sources()

    duplicates = find_exact_duplicates(profiles)
    summary = build_summary(profiles, duplicates)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json(
        profiles,
        OUTPUT_DIR / "source_catalog.json",
    )

    write_csv(
        profiles,
        OUTPUT_DIR / "source_catalog.csv",
    )

    write_json(
        summary,
        OUTPUT_DIR / "profile_summary.json",
    )

    write_json(
        duplicates,
        OUTPUT_DIR / "exact_duplicates.json",
    )

    print("\nSOURCE PROFILING COMPLETE")
    print("=" * 60)
    print(f"Files profiled          : {summary['total_files']}")
    print(
        "Total size              : "
        f"{summary['total_size_bytes']:,} bytes"
    )
    print(
        "Exact duplicate groups  : "
        f"{summary['exact_duplicate_groups']}"
    )
    print(
        "Exact duplicate files   : "
        f"{summary['exact_duplicate_files']}"
    )

    print("\nSource categories")
    print("-" * 60)

    for category, count in summary["source_categories"].items():
        print(f"{category:30} : {count}")

    print("\nTopics detected")
    print("-" * 60)

    for topic, count in summary["topics"].items():
        print(f"{topic:30} : {count}")

    print("\nOutput files")
    print("-" * 60)
    print(OUTPUT_DIR / "source_catalog.json")
    print(OUTPUT_DIR / "source_catalog.csv")
    print(OUTPUT_DIR / "profile_summary.json")
    print(OUTPUT_DIR / "exact_duplicates.json")


if __name__ == "__main__":
    main()