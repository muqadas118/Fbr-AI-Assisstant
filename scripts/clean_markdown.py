from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "01-markdown"
PROFILE_DIR = PROJECT_ROOT / "data" / "profile"
OUTPUT_DIR = PROFILE_DIR / "markdown"


def normalize_line(line: str) -> str:
    """
    Safe Markdown cleanup:
    - remove trailing whitespace
    - normalize tabs to spaces
    - preserve actual content
    """

    line = line.replace("\t", "    ")
    line = line.rstrip()

    return line


def normalize_markdown(text: str) -> str:
    """
    Conservative normalization only.

    We do NOT rewrite wording.
    We only normalize whitespace and blank lines.
    """

    lines = text.splitlines()

    cleaned = []

    previous_blank = False

    for line in lines:

        line = normalize_line(line)

        is_blank = line.strip() == ""

        # Avoid excessive consecutive blank lines.
        if is_blank:

            if previous_blank:
                continue

            previous_blank = True
            cleaned.append("")

            continue

        previous_blank = False

        cleaned.append(line)

    # Remove blank lines at beginning/end.
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)

    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    if not cleaned:
        return ""

    return "\n".join(cleaned) + "\n"


def validate_markdown(
    filename: str,
    text: str,
) -> list[str]:

    problems = []

    if not text.strip():
        problems.append(
            "empty file"
        )
        return problems

    lines = text.splitlines()

    # Check extremely long lines.
    for number, line in enumerate(
        lines,
        start=1,
    ):

        if len(line) > 5000:
            problems.append(
                f"line {number} is unusually long "
                f"({len(line)} characters)"
            )

    # Check broken CR characters.
    if "\r" in text:
        problems.append(
            "contains carriage-return characters"
        )

    # Check null bytes.
    if "\x00" in text:
        problems.append(
            "contains null byte"
        )

    return problems


def process_file(
    source: Path,
    destination: Path,
) -> dict:

    original = source.read_text(
        encoding="utf-8",
        errors="strict",
    )

    problems = validate_markdown(
        source.name,
        original,
    )

    cleaned = normalize_markdown(
        original
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        cleaned,
        encoding="utf-8",
    )

    return {
        "original_chars": len(original),
        "cleaned_chars": len(cleaned),
        "original_lines": len(
            original.splitlines()
        ),
        "cleaned_lines": len(
            cleaned.splitlines()
        ),
        "problems": problems,
        "changed": original != cleaned,
    }


def main():

    print()
    print("=" * 60)
    print("FBR MARKDOWN CLEANING")
    print("=" * 60)
    print()

    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Markdown directory not found:\n{RAW_DIR}"
        )

    markdown_files = sorted(
        RAW_DIR.glob("*.md")
    )

    print(
        f"Markdown files found: "
        f"{len(markdown_files)}"
    )

    print()

    results = []

    for source in markdown_files:

        destination = (
            OUTPUT_DIR / source.name
        )

        result = process_file(
            source,
            destination,
        )

        results.append(
            (
                source.name,
                result,
            )
        )

        status = (
            "CHANGED"
            if result["changed"]
            else "UNCHANGED"
        )

        print(
            f"{source.name:45} "
            f"{status}"
        )

        if result["problems"]:

            for problem in result["problems"]:
                print(
                    f"    WARNING: {problem}"
                )

    changed = sum(
        1
        for _, result in results
        if result["changed"]
    )

    warnings = sum(
        len(result["problems"])
        for _, result in results
    )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Files processed : {len(results)}"
    )

    print(
        f"Files changed   : {changed}"
    )

    print(
        f"Warnings        : {warnings}"
    )

    print(
        f"Output folder   : {OUTPUT_DIR}"
    )

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()