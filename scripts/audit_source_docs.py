from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = PROJECT_ROOT / "data" / "raw" / "04-source-docs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "profile" / "source_docs"


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


def file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()

    with path.open("rb") as file:

        while True:

            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def classify_file(path: Path) -> str:

    extension = path.suffix.lower()

    if extension == ".pdf":
        return "pdf"

    if extension in {".doc", ".docx"}:
        return "word"

    if extension in {".xls", ".xlsx"}:
        return "spreadsheet"

    return "unsupported"


def main():

    print()
    print("=" * 60)
    print("FBR SOURCE DOCUMENT AUDIT")
    print("=" * 60)
    print()

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Source directory not found:\n{SOURCE_DIR}"
        )

    files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower()
        in SUPPORTED_EXTENSIONS
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Supported documents: {len(files)}"
    )

    print()

    hashes = {}
    duplicates = []
    zero_byte = []

    type_counts = {
        "pdf": 0,
        "word": 0,
        "spreadsheet": 0,
    }

    for path in files:

        file_type = classify_file(path)

        type_counts[file_type] += 1

        size = path.stat().st_size

        if size == 0:

            zero_byte.append(
                path.name
            )

        digest = file_hash(path)

        if digest in hashes:

            duplicates.append(
                (
                    path.name,
                    hashes[digest],
                )
            )

        else:

            hashes[digest] = path.name

    print("FILE TYPES")
    print("-" * 60)

    for file_type, count in type_counts.items():

        print(
            f"{file_type:15}: {count}"
        )

    print()

    print("ZERO-BYTE FILES")
    print("-" * 60)

    if zero_byte:

        for name in zero_byte:
            print(name)

    else:

        print("None")

    print()

    print("EXACT DUPLICATES")
    print("-" * 60)

    if duplicates:

        for duplicate, original in duplicates:

            print(
                f"{duplicate}"
            )

            print(
                f"  duplicate of: {original}"
            )

    else:

        print("None")

    print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Documents audited : {len(files)}"
    )

    print(
        f"Zero-byte files   : {len(zero_byte)}"
    )

    print(
        f"Duplicate files   : {len(duplicates)}"
    )

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()