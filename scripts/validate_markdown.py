from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "01-markdown"
CLEAN_DIR = PROJECT_ROOT / "data" / "profile" / "markdown"


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8",
        errors="strict",
    )


def basic_markdown_checks(
    filename: str,
    text: str,
) -> list[str]:
    problems = []

    if not text.strip():
        problems.append("empty file")

    # Check fenced code blocks.
    fence_count = text.count("```")

    if fence_count % 2 != 0:
        problems.append(
            f"unbalanced code fences: {fence_count}"
        )

    # Check Markdown table rows in a very conservative way.
    # We only flag an obviously broken separator line.
    lines = text.splitlines()

    for index, line in enumerate(lines):

        stripped = line.strip()

        # A separator row should contain at least one dash when it appears
        # after another table row.
        if (
            stripped.startswith("|")
            and "|" in stripped
            and index > 0
            and "---" in stripped
            and stripped.count("|") < 2
        ):
                problems.append(
                    f"suspicious table separator near line "
                    f"{index + 1}"
                )

    return problems


def validate():

    print()
    print("=" * 60)
    print("FBR MARKDOWN VALIDATION")
    print("=" * 60)
    print()

    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Raw Markdown directory not found:\n{RAW_DIR}"
        )

    if not CLEAN_DIR.exists():
        raise FileNotFoundError(
            f"Cleaned Markdown directory not found:\n{CLEAN_DIR}"
        )

    raw_files = {
        file.name
        for file in RAW_DIR.glob("*.md")
    }

    clean_files = {
        file.name
        for file in CLEAN_DIR.glob("*.md")
    }

    print(
        f"Raw Markdown files     : {len(raw_files)}"
    )

    print(
        f"Cleaned Markdown files : {len(clean_files)}"
    )

    print()

    missing = sorted(
        raw_files - clean_files
    )

    extra = sorted(
        clean_files - raw_files
    )

    if missing:

        print("MISSING CLEANED FILES:")

        for name in missing:
            print(f"  {name}")

    if extra:

        print("EXTRA CLEANED FILES:")

        for name in extra:
            print(f"  {name}")

    if not missing and not extra:
        print(
            "Filename consistency : PASS"
        )

    print()

    problems_found = 0
    changed_files = 0

    for filename in sorted(raw_files):

        raw_path = RAW_DIR / filename
        clean_path = CLEAN_DIR / filename

        if not clean_path.exists():
            continue

        try:
            raw_text = read_text(raw_path)
            clean_text = read_text(clean_path)

        except (OSError, UnicodeError) as error:

            print(
                f"ERROR reading {filename}: {error}"
            )

            problems_found += 1
            continue

        if raw_text != clean_text:
            changed_files += 1

        problems = basic_markdown_checks(
            filename,
            clean_text,
        )

        # ----------------------------------------------------
        # Size/content safety check
        # ----------------------------------------------------

        raw_length = len(raw_text)
        clean_length = len(clean_text)

        if raw_length > 0:

            ratio = clean_length / raw_length

            # Cleaning should not drastically change content size.
            if ratio < 0.90 or ratio > 1.10:

                problems.append(
                    "content size changed by more than 10% "
                    f"({ratio:.2%})"
                )

        if problems:

            print()
            print(
                f"PROBLEMS: {filename}"
            )

            for problem in problems:

                print(
                    f"  - {problem}"
                )

            problems_found += len(
                problems
            )

    print()
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    print(
        f"Raw files checked       : {len(raw_files)}"
    )

    print(
        f"Cleaned files checked   : {len(clean_files)}"
    )

    print(
        f"Changed files           : {changed_files}"
    )

    print(
        f"Problems found          : {problems_found}"
    )

    print(
        f"Missing files           : {len(missing)}"
    )

    print(
        f"Extra files             : {len(extra)}"
    )

    print()

    if (
        not missing
        and not extra
        and problems_found == 0
    ):

        print(
            "ALL MARKDOWN VALIDATIONS PASSED"
        )

    else:

        print(
            "MARKDOWN VALIDATION FAILED"
        )

    print("=" * 60)
    print()


if __name__ == "__main__":
    validate()