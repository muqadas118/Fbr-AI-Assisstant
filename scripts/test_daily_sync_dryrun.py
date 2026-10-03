"""
test_daily_sync_dryrun.py — Dry-run demo for daily_update.py FIX 1 / 2 / 3
==========================================================================

NO real network, NO real source documents touched (isolated workspace,
http_get is replaced with synthetic bytes — same style as
test_daily_update_safe.py).

What it proves:

1. FIX 1 (up-to-date path): existing file + SAME remote hash
   -> "Already up-to-date", temp file deleted, local bytes untouched.
2. FIX 1 (update path): same filename, DIFFERENT remote hash
   -> "Updated: ...", local file overwritten, no stray .tmp.pdf left.
3. FIX 1 (new file path): no local file -> "Updated: ...", file created.
4. FIX 3: .pdf destination with data NOT starting with %PDF
   -> WARNING + False, nothing written, existing file untouched.
5. FIX 2: document_is_relevant("finance_acts", ...) accepts
   Budget / Salient Features filenames, not only Finance Act.
6. FIX 3 (positive): valid %PDF data passes download_file.

Run:
    python scripts/test_daily_sync_dryrun.py
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location(
    "daily_update", PROJECT_ROOT / "scripts" / "daily_update.py"
)
daily_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily_update)

# Isolated workspace PROJECT ke ANDAR — daily_update ke log
# destination.relative_to(PROJECT_ROOT) use karte hain
# (test_daily_update_safe.py wala hi pattern).
WORKSPACE = PROJECT_ROOT / "data" / "profile" / "daily_sync_dryrun_test"


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def main() -> int:
    print("=" * 64)
    print("DAILY UPDATE - FIX 1 / 2 / 3 DRY-RUN DEMO (no network)")
    print("=" * 64)

    workspace = WORKSPACE
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, bool, str]] = []

    try:
        # ------------------------------------------------------
        # Synthetic remote bytes (http_get replace = no network)
        # ------------------------------------------------------
        pdf_v1 = b"%PDF-1.4\noriginal finance act bytes\n"
        pdf_v2 = b"%PDF-1.7\nREVISED finance act bytes (new FBR version)\n"
        not_pdf = b"<html><body>error 403</body></html>"

        daily_update.http_get = lambda url: pdf_v1
        daily_update.calculate_file_hash = lambda p: sha256_bytes(Path(p).read_bytes())

        # ------------------------------------------------------
        # DEMO 1: same hash -> "Already up-to-date"
        # ------------------------------------------------------
        print("\n--- DEMO 1: remote file SAME hash ---")
        dest = workspace / "FinanceAct2026.pdf"
        dest.write_bytes(pdf_v1)
        local_before = sha256_bytes(dest.read_bytes())

        daily_update.sync_official_document("https://download1.fbr.gov.pk/Docs/FinanceAct2026.pdf", dest)

        ok1 = (
            sha256_bytes(dest.read_bytes()) == local_before
            and not dest.with_suffix(".tmp.pdf").exists()
        )
        results.append(("FIX1_same_hash_already_up_to_date", ok1, "bytes identical, temp deleted"))

        # ------------------------------------------------------
        # DEMO 2: same filename, changed remote -> "Updated"
        # ------------------------------------------------------
        print("\n--- DEMO 2: remote file CHANGED (same filename) ---")
        daily_update.http_get = lambda url: pdf_v2
        daily_update.sync_official_document("https://download1.fbr.gov.pk/Docs/FinanceAct2026.pdf", dest)

        ok2 = (
            dest.read_bytes() == pdf_v2
            and not dest.with_suffix(".tmp.pdf").exists()
        )
        results.append(("FIX1_changed_hash_updated_in_place", ok2, "same-name overwrite works"))

        # ------------------------------------------------------
        # DEMO 3: no local file yet -> "Updated" (new download)
        # ------------------------------------------------------
        print("\n--- DEMO 3: file not present locally ---")
        dest2 = workspace / "SalesTaxAct_Amended.pdf"
        daily_update.sync_official_document("https://download1.fbr.gov.pk/Docs/SalesTaxAct_Amended.pdf", dest2)

        ok3 = dest2.exists() and dest2.read_bytes() == pdf_v2
        results.append(("FIX1_new_file_downloaded", ok3, "new file created"))

        # ------------------------------------------------------
        # DEMO 4: FIX 3 — invalid PDF blocked, local file safe
        # ------------------------------------------------------
        print("\n--- DEMO 4: invalid PDF data (missing %PDF header) ---")
        daily_update.http_get = lambda url: not_pdf
        ok4 = not daily_update.download_file(
            "https://download1.fbr.gov.pk/Docs/SalesTaxAct_Amended.pdf", dest2
        )
        still_intact = dest2.exists() and dest2.read_bytes() == pdf_v2
        results.append(("FIX3_invalid_pdf_blocked", ok4 and still_intact, "WARNING logged, local file untouched"))

        # ------------------------------------------------------
        # DEMO 5: FIX 2 — salient/budget relevance
        # ------------------------------------------------------
        print("\n--- DEMO 5: finance_acts relevance filter ---")
        cases = [
            ("https://download1.fbr.gov.pk/Docs/Budget2026-27_SalientFeatures.pdf", True),
            ("https://download1.fbr.gov.pk/Docs/20266291261044366FinanceAct2026.pdf", True),
            ("https://download1.fbr.gov.pk/Docs/RandomNotification2026.pdf", False),
        ]
        ok5 = all(
            daily_update.document_is_relevant(url, "finance_acts") == expected
            for url, expected in cases
        )
        for url, expected in cases:
            got = daily_update.document_is_relevant(url, "finance_acts")
            print(f"    {'PASS' if got == expected else 'FAIL'}: {Path(url).name} -> {got}")
        results.append(("FIX2_salient_budget_relevant", ok5, "budget/salient accepted, junk rejected"))

        # ------------------------------------------------------
        # DEMO 6: FIX 3 positive — valid PDF passes
        # ------------------------------------------------------
        print("\n--- DEMO 6: valid %PDF data passes ---")
        daily_update.http_get = lambda url: pdf_v1
        dest3 = workspace / "ValidDoc.pdf"
        ok6 = daily_update.download_file("https://download1.fbr.gov.pk/Docs/ValidDoc.pdf", dest3)
        results.append(("FIX3_valid_pdf_passes", bool(ok6 and dest3.read_bytes() == pdf_v1), "normal flow unchanged"))

    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------
    print()
    print("=" * 64)
    passed = 0
    for name, ok, detail in results:
        passed += 1 if ok else 0
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  ({detail})")
    print("=" * 64)
    print(f"Total : {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(results) - passed}")
    print("=" * 64)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
