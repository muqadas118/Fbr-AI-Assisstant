import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEANED_DIR = ROOT / "data" / "profile" / "source_docs" / "cleaned"
MASTER_FILE = CLEANED_DIR / "cleaned_documents.json"
SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"

REQUIRED_FIELDS = {
    "document_id",
    "document_type",
    "title",
    "source",
    "source_path",
    "source_sha256",
    "official_source_url",
    "publication_date",
    "effective_date",
    "status",
    "sections",
    "text",
    "text_chars",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files():
    extensions = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".md", ".jsonl"}
    return {
        str(path.relative_to(SOURCE_DIR)).replace("\\", "/"): path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    }


def main():
    cleaned_dir = Path(os.environ.get("NORMALIZATION_OUTPUT_DIR", str(CLEANED_DIR)))
    master_file = cleaned_dir / "cleaned_documents.json"
    sources = source_files()
    try:
        master = json.loads(master_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: Cannot read normalized master: {exc}")
        sys.exit(1)
    if not isinstance(master, list):
        print("ERROR: Normalized master must be a list.")
        sys.exit(1)

    ids = set()
    paths = set()
    errors = []
    manual_review = 0
    extracted = 0
    for index, record in enumerate(master, 1):
        if not isinstance(record, dict):
            errors.append(f"record {index}: not an object")
            continue
        missing = REQUIRED_FIELDS - set(record)
        if missing:
            errors.append(f"record {index}: missing {sorted(missing)}")
            continue
        path = str(record["source_path"]).replace("\\", "/")
        source = str(record["source"])
        source_file = sources.get(path)
        if source_file is None or source_file.name != Path(source).name:
            errors.append(f"record {index}: source path mismatch: {path}")
        else:
            actual_hash = sha256_file(source_file)
            if record["source_sha256"] != actual_hash:
                errors.append(f"record {index}: source hash mismatch: {path}")
        if record["document_id"] in ids:
            errors.append(f"record {index}: duplicate document_id")
        ids.add(record["document_id"])
        if path in paths:
            errors.append(f"record {index}: duplicate source_path")
        paths.add(path)
        if not isinstance(record["sections"], list):
            errors.append(f"record {index}: sections is not a list")
        if not isinstance(record["text"], str) or record["text_chars"] != len(record["text"]):
            errors.append(f"record {index}: text/text_chars mismatch")
        if record["status"] == "manual_review_required":
            manual_review += 1
            if record["text"]:
                errors.append(f"record {index}: manual-review record has text")
        elif record["status"] == "extracted":
            extracted += 1
            if not record["text"].strip():
                errors.append(f"record {index}: extracted record has empty text")
        else:
            errors.append(f"record {index}: invalid status {record['status']}")
        previous = None
        for section in record["sections"]:
            if not isinstance(section, dict):
                errors.append(f"record {index}: malformed section")
                continue
            page = section.get("page")
            if page is not None and (not isinstance(page, int) or page < 1):
                errors.append(f"record {index}: invalid page")
            if not isinstance(section.get("text"), str):
                errors.append(f"record {index}: section text is not string")
            tables = section.get("tables")
            if not isinstance(tables, list):
                errors.append(f"record {index}: section tables is not list")
            if page is not None and previous is not None and page < previous:
                errors.append(f"record {index}: sections are not ordered")
            if page is not None:
                previous = page
    missing = sorted(set(sources) - paths)
    orphan = sorted(paths - set(sources))
    if missing:
        errors.append(f"missing source records: {missing}")
    if orphan:
        errors.append(f"orphan source records: {orphan}")
    ordered = [(item.get("source_path"), item.get("document_id")) for item in master if isinstance(item, dict)]
    if ordered != sorted(ordered):
        errors.append("master records are not deterministically ordered")

    print(f"Canonical source files : {len(sources)}")
    print(f"Normalized records     : {len(master)}")
    print(f"Extracted records      : {extracted}")
    print(f"Manual-review records  : {manual_review}")
    print(f"Validation errors      : {len(errors)}")
    for error in errors[:30]:
        print(f"[INVALID] {error}")
    if errors:
        print("NORMALIZATION VALIDATION: FAIL")
        sys.exit(1)
    print("NORMALIZATION VALIDATION: PASS")


if __name__ == "__main__":
    main()
