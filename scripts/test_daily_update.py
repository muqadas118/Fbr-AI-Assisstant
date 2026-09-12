from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "data" / "raw" / "04-source-docs"
DAILY_UPDATE = PROJECT_ROOT / "scripts" / "daily_update.py"


# ============================================================
# TEST SOURCE
# ============================================================
#
# We select an existing source document.
# The original file is backed up first.
#
# IMPORTANT:
# The original file is restored after the test.
# ============================================================

TEST_FILE = (
    SOURCE_DIR
    / "20266291261044366FinanceAct2026.pdf"
)

BACKUP_FILE = (
    SOURCE_DIR
    / "20266291261044366FinanceAct2026.pdf.daily_test_backup"
)


# ============================================================
# HASH
# ============================================================

def sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    print()
    print("=" * 60)
    print("FBR DAILY UPDATE - CHANGE DETECTION TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Check files
    # --------------------------------------------------------

    if not TEST_FILE.exists():
        print()
        print("ERROR: Test source file does not exist:")
        print(TEST_FILE)
        return 1

    if BACKUP_FILE.exists():
        print()
        print("ERROR: Backup file already exists:")
        print(BACKUP_FILE)
        print()
        print("Delete the old .daily_test_backup file first.")
        return 1

    # --------------------------------------------------------
    # Original hash
    # --------------------------------------------------------

    original_hash = sha256(TEST_FILE)

    print()
    print("Test file:")
    print(TEST_FILE.relative_to(PROJECT_ROOT))

    print()
    print("Original SHA-256:")
    print(original_hash)

    # --------------------------------------------------------
    # Create exact backup
    # --------------------------------------------------------

    print()
    print("Creating temporary backup...")

    shutil.copy2(
        TEST_FILE,
        BACKUP_FILE
    )

    print("Backup created.")

    try:

        # ----------------------------------------------------
        # Make harmless file-level modification
        # ----------------------------------------------------
        #
        # We only touch the PDF metadata timestamp.
        # The actual document content is NOT changed.
        #
        # This is NOT enough for SHA-256 change detection,
        # because the file bytes remain identical.
        #
        # Therefore we intentionally append a temporary
        # test marker and restore the original afterward.
        # ----------------------------------------------------

        print()
        print("Applying temporary test modification...")

        with open(
            TEST_FILE,
            "ab"
        ) as file:

            file.write(
                b"\nFBR_DAILY_UPDATE_TEST_MARKER\n"
            )

        modified_hash = sha256(TEST_FILE)

        print()
        print("Temporary modified SHA-256:")
        print(modified_hash)

        if modified_hash == original_hash:
            print()
            print("ERROR: Test modification did not change the hash.")
            return 1

        print()
        print("PASS: File hash changed.")

        # ----------------------------------------------------
        # Run daily update
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print("RUNNING DAILY UPDATE")
        print("=" * 60)

        result = subprocess.run(
            [
                sys.executable,
                str(DAILY_UPDATE)
            ],
            cwd=PROJECT_ROOT,
            check=False
        )

        if result.returncode != 0:
            print()
            print(
                "WARNING: daily_update.py returned "
                f"exit code {result.returncode}."
            )

            return result.returncode

        print()
        print("daily_update.py completed successfully.")

        return 0

    finally:

        # ----------------------------------------------------
        # ALWAYS RESTORE ORIGINAL FILE
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print("RESTORING ORIGINAL SOURCE FILE")
        print("=" * 60)

        if BACKUP_FILE.exists():

            shutil.copy2(
                BACKUP_FILE,
                TEST_FILE
            )

            restored_hash = sha256(TEST_FILE)

            print()
            print("Restored SHA-256:")
            print(restored_hash)

            if restored_hash == original_hash:
                print()
                print("PASS: Original source file restored exactly.")
            else:
                print()
                print(
                    "ERROR: Restored file hash does not match "
                    "the original hash."
                )

            BACKUP_FILE.unlink()

            print()
            print("Temporary backup removed.")

        else:
            print()
            print("WARNING: Backup file was not found.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())