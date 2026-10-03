import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "profile" / "source_docs" / "extracted"
OUTPUT_DIR = ROOT / "data" / "profile" / "source_docs" / "cleaned"
SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"
MASTER_NAME = "cleaned_documents.json"


def clean_text(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return "\n".join(line.strip() for line in value.split("\n") if line.strip()).strip()


def normalize_source_path(source):
    return str(source).replace("\\", "/").lstrip("./")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_source(source, extraction_path):
    relative = normalize_source_path(source)
    direct = SOURCE_DIR / relative
    if direct.is_file():
        return direct, relative
    candidates = sorted(SOURCE_DIR.rglob(Path(relative).name))
    if len(candidates) == 1:
        return candidates[0], str(candidates[0].relative_to(SOURCE_DIR)).replace("\\", "/")
    fallback = SOURCE_DIR / extraction_path.relative_to(INPUT_DIR).with_suffix(Path(relative).suffix)
    if fallback.is_file():
        return fallback, str(fallback.relative_to(SOURCE_DIR)).replace("\\", "/")
    return None, relative


def table_text(table):
    rows = []
    if not isinstance(table, list):
        return ""
    for row in table:
        if not isinstance(row, list):
            continue
        cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def build_sections(data):
    root = data.get("data") if isinstance(data.get("data"), dict) else data.get("extracted_data")
    if not isinstance(root, dict):
        root = {}
    fmt = str(root.get("format") or data.get("extension") or "").lower().lstrip(".")
    sections = []
    pages = root.get("pages_data")
    if isinstance(pages, list):
        for item in pages:
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            text = clean_text(item.get("text", ""))
            section = {"page": page if isinstance(page, int) else None, "heading": None, "section_reference": None, "text": text, "tables": []}
            if text or page is not None:
                sections.append(section)
    sheets = root.get("sheets")
    if isinstance(sheets, list):
        for item in sheets:
            if not isinstance(item, dict):
                continue
            rows = item.get("rows", [])
            table_values = [rows] if isinstance(rows, list) and rows else []
            heading = str(item.get("sheet")).strip() or None
            sections.append({"page": None, "heading": heading, "section_reference": None, "text": heading or "", "tables": table_values})
    paragraphs = root.get("paragraphs")
    tables = root.get("tables")
    if isinstance(paragraphs, list) or isinstance(tables, list):
        paragraph_text = [clean_text(x) for x in paragraphs or [] if clean_text(x)]
        paragraph_text = clean_text("\n\n".join(paragraph_text))
        table_values = [x for x in tables or [] if isinstance(x, list)]
        table_parts = [table_text(x) for x in table_values]
        combined = clean_text("\n".join([paragraph_text] + [x for x in table_parts if x]))
        if combined or paragraph_text or table_values:
            sections.append({"page": None, "heading": None, "section_reference": None, "paragraph_text": paragraph_text, "text": combined, "tables": table_values})
    md_sections = root.get("sections")
    if isinstance(md_sections, list) and fmt == "markdown":
        for item in md_sections:
            if not isinstance(item, dict):
                continue
            text = clean_text(str(item.get("text", "")))
            heading = clean_text(str(item.get("heading") or "")) or None
            if text:
                sections.append({"page": None, "heading": heading, "section_reference": None, "text": text, "tables": []})
    entries = root.get("entries")
    if isinstance(entries, list) and fmt == "jsonl":
        for item in entries:
            if not isinstance(item, dict):
                continue
            question = clean_text(str(item.get("question", "")))
            answer = clean_text(str(item.get("answer", "")))
            if not question or not answer:
                continue
            provenance = clean_text(str(item.get("source") or ""))
            heading = clean_text(str(item.get("section") or item.get("category") or "")) or None
            parts = [f"Q: {question}", f"A: {answer}"]
            if provenance:
                parts.append(f"Source: {provenance}")
            text = clean_text("\n".join(parts))
            sections.append({"page": None, "heading": heading, "section_reference": heading, "text": text, "tables": []})
    if not sections:
        direct = clean_text(root.get("text") or root.get("content") or data.get("text") or data.get("content") or "")
        if direct:
            sections.append({"page": None, "heading": None, "section_reference": None, "text": direct, "tables": []})
    return sections, fmt


def make_id(source_path):
    return hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:16]


def normalize_record(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    source = data.get("source") or data.get("source_file") or path.stem
    source_path_obj, source_path = resolve_source(source, path)
    if source_path_obj is None:
        raise FileNotFoundError(f"Cannot resolve source: {source}")
    source_hash = sha256_file(source_path_obj)
    recorded_hash = data.get("sha256")
    if recorded_hash and recorded_hash != source_hash:
        raise ValueError(f"Source hash mismatch: {source}")
    sections, fmt = build_sections(data)
    text = clean_text("\n\n".join(section["text"] for section in sections if section["text"]))
    status = data.get("status") or ("manual_review_required" if not text else "extracted")
    return {
        "document_id": make_id(source_path),
        "document_type": fmt or None,
        "title": None,
        "source": source,
        "source_path": source_path,
        "source_sha256": source_hash,
        "official_source_url": None,
        "publication_date": None,
        "effective_date": None,
        "status": status,
        "sections": sections,
        "text": text,
        "text_chars": len(text),
    }


def main():
    input_dir = Path(os.environ.get("NORMALIZATION_INPUT_DIR", str(INPUT_DIR)))
    output_dir = Path(os.environ.get("NORMALIZATION_OUTPUT_DIR", str(OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    errors = []
    files = sorted(path for path in input_dir.rglob("*.json") if path.name != MASTER_NAME)
    for path in files:
        try:
            record = normalize_record(path)
            records.append(record)
            relative = path.relative_to(input_dir)
            target = output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    records.sort(key=lambda item: (item["source_path"], item["document_id"]))
    master = output_dir / MASTER_NAME
    master.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted JSON files : {len(files)}")
    print(f"Normalized records   : {len(records)}")
    print(f"Manual-review records: {sum(item['status'] == 'manual_review_required' for item in records)}")
    print(f"Errors               : {len(errors)}")
    print(f"Output               : {master}")
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
