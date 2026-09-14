import json
import logging
import time
from pathlib import Path

import win32com.client as win32
import pywintypes

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = PROJECT_ROOT / "data" / "raw" / "04-source-docs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "profile" / "source_docs" / "extracted"

TARGETS = [
    "CapitalValueTax_DepositsForm.doc",
    "CPR_ComputerizedPaymentReceipt.doc",
    "CPR_Format_BulkData.doc",
    "TaxDepositForm.doc",
]


def extract_doc(source_path, output_path):
    word = None
    doc = None

    try:
        word = win32.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0

        doc = word.Documents.Open(
            str(source_path),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
        )

        paragraphs = []
        for p in doc.Paragraphs:
            text = p.Range.Text.replace("\r", "").replace("\x07", "").strip()
            text = "".join(
                character
                for character in text
                if character.isprintable()
            ).strip()
            if text:
                paragraphs.append(text)

        tables = []

        for table in doc.Tables:
            rows = []

            for row in table.Rows:
                cells = []

                for cell in row.Cells:
                    text = (
                        cell.Range.Text
                        .replace("\r", "")
                        .replace("\x07", "")
                        .strip()
                    )
                    text = "".join(
                        character
                        for character in text
                        if character.isprintable()
                    ).strip()
                    cells.append(text)

                rows.append(cells)

            tables.append(rows)

        full_text = "\n".join(paragraphs)

        has_meaningful_table_content = any(
            cell
            for table in tables
            for row in table
            for cell in row
        )

        status = "extracted"

        if not paragraphs and not has_meaningful_table_content:
            status = "manual_review_required"

        data = {
            "source": source_path.name,
            "sha256": __import__("hashlib")
                .sha256(source_path.read_bytes())
                .hexdigest(),
            "status": status,
            "data": {
                "format": "doc",
                "paragraphs": paragraphs,
                "tables": tables,
                "paragraph_count": len(paragraphs),
                "table_count": len(tables),
                "text_chars": len(full_text),
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return (
            True,
            status,
            len(paragraphs),
            len(tables),
            len(full_text),
        )

    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except (AttributeError, OSError, pywintypes.com_error) as exc:
            logger.debug("Error closing document: %s", exc)

        try:
            if word is not None:
                word.Quit()
        except (AttributeError, OSError, pywintypes.com_error) as exc:
            logger.debug("Error quitting Word: %s", exc)

        time.sleep(1)


def main():
    print("=" * 60)
    print("FBR REMAINING LEGACY DOC RETRY")
    print("=" * 60)

    success = 0
    failed = 0

    for index, name in enumerate(TARGETS, 1):

        source = SOURCE_DIR / name
        output = OUTPUT_DIR / Path(name).with_suffix(".json")

        print(f"[{index}/{len(TARGETS)}] {name}")

        if not source.exists():
            print("    STATUS: SOURCE FILE NOT FOUND")
            failed += 1
            continue

        try:
            ok, status, paragraphs, tables, chars = extract_doc(
                source,
                output,
            )

            if ok:
                if status == "manual_review_required":
                    print("    STATUS: MANUAL REVIEW REQUIRED")
                else:
                    print("    STATUS: EXTRACTED")
                print(f"    Paragraphs  : {paragraphs}")
                print(f"    Tables      : {tables}")
                print(f"    Text chars  : {chars}")
                print(f"    Output      : {output.name}")
                success += 1
            else:
                print("    STATUS: FAILED")
                failed += 1

        except (OSError, ValueError, RuntimeError) as e:
            print("    STATUS: FAILED")
            print(f"    ERROR: {type(e).__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print("RETRY SUMMARY")
    print("=" * 60)
    print(f"Targeted DOCs        : {len(TARGETS)}")
    print(f"Successfully extracted: {success}")
    print(f"Failed               : {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()