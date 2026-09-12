import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "profile" / "source_docs" / "cleaned"
OUTPUT_DIR = ROOT / "data" / "profile" / "source_docs" / "chunks"
MASTER_NAME = "cleaned_documents.json"
TARGET_SIZE = 1600
MAX_SIZE = 2200
OVERLAP = 120


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def split_long_text(text):
    text = normalize_text(text)
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) == 1:
        paragraphs = [line.strip() for line in text.split("\n") if line.strip()]
    chunks = []
    current = []
    current_size = 0
    for paragraph in paragraphs:
        pieces = [paragraph]
        if len(paragraph) > MAX_SIZE:
            pieces = []
            start = 0
            while start < len(paragraph):
                end = min(start + TARGET_SIZE, len(paragraph))
                if end < len(paragraph):
                    boundary = max(paragraph.rfind(". ", start, end), paragraph.rfind("; ", start, end), paragraph.rfind(" ", start, end))
                    if boundary > start + TARGET_SIZE // 2:
                        end = boundary + 1
                pieces.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(end - OVERLAP, start + 1)
        for piece in pieces:
            addition = len(piece) + (2 if current else 0)
            if current and current_size + addition > TARGET_SIZE:
                chunks.append("\n\n".join(current))
                current = []
                current_size = 0
            if piece:
                current.append(piece)
                current_size += len(piece) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def render_row(row):
    if not isinstance(row, list):
        return ""
    return " | ".join(str(cell).strip() for cell in row if cell is not None and str(cell).strip())


def table_chunks(table, heading):
    rows = [row for row in table if isinstance(row, list) and render_row(row)]
    if not rows:
        return []
    header = rows[0]
    result = []
    current = []
    size = len(render_row(header))
    for row in rows[1:] if len(rows) > 1 else rows:
        rendered = render_row(row)
        if current and size + len(rendered) + 1 > MAX_SIZE:
            selected = [header] + current if len(rows) > 1 else current
            text = normalize_text("\n".join(filter(None, [heading or "", *(render_row(item) for item in selected)])))
            result.append((text, {"header": header if len(rows) > 1 else None, "rows": current}))
            current = []
            size = len(render_row(header))
        current.append(row)
        size += len(rendered) + 1
    if current:
        selected = [header] + current if len(rows) > 1 else current
        text = normalize_text("\n".join(filter(None, [heading or "", *(render_row(item) for item in selected)])))
        result.append((text, {"header": header if len(rows) > 1 else None, "rows": current}))
    return result


def make_chunk_id(document_id, index, text, page_start, heading, section_reference):
    raw = json.dumps([document_id, index, text, page_start, heading, section_reference], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def chunk_document(document):
    if document.get("status") == "manual_review_required":
        return []
    chunks = []
    for section in document.get("sections", []):
        page = section.get("page")
        heading = section.get("heading")
        reference = section.get("section_reference")
        tables = section.get("tables", [])
        paragraph_text = section.get("paragraph_text")
        source_text = paragraph_text if tables and isinstance(paragraph_text, str) else section.get("text", "")
        for text in split_long_text(source_text):
            chunks.append((text, page, page, heading, reference, None))
        for table in tables:
            for text, table_data in table_chunks(table, heading):
                chunks.append((text, page, page, heading, reference, table_data))
    records = []
    for index, (text, page_start, page_end, heading, reference, table_data) in enumerate(chunks):
        record = {
            "chunk_id": make_chunk_id(document["document_id"], index, text, page_start, heading, reference),
            "document_id": document["document_id"],
            "source": document["source"],
            "source_path": document["source_path"],
            "source_sha256": document["source_sha256"],
            "document_type": document["document_type"],
            "title": document["title"],
            "publication_date": document["publication_date"],
            "effective_date": document["effective_date"],
            "page_start": page_start,
            "page_end": page_end,
            "heading": heading,
            "section_reference": reference,
            "chunk_index": index,
            "chunk_text": text,
            "text": text,
            "text_chars": len(text),
            "table_data": table_data,
        }
        records.append(record)
    return records


def normalized_files(input_dir):
    return sorted(path for path in input_dir.rglob("*.json") if path.name != MASTER_NAME)


def main():
    input_dir = Path(os.environ.get("CHUNK_INPUT_DIR", str(INPUT_DIR)))
    output_dir = Path(os.environ.get("CHUNK_OUTPUT_DIR", str(OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "chunks.json"
    temporary = output_file.with_suffix(".json.tmp")
    total_documents = 0
    total_chunks = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("[\n")
        first = True
        for path in normalized_files(input_dir):
            document = json.loads(path.read_text(encoding="utf-8"))
            records = chunk_document(document)
            for record in records:
                if not first:
                    stream.write(",\n")
                stream.write(json.dumps(record, ensure_ascii=False, indent=2))
                first = False
                total_chunks += 1
            total_documents += 1
        stream.write("\n]\n")
    os.replace(temporary, output_file)
    print(f"Documents processed : {total_documents}")
    print(f"Total chunks        : {total_chunks}")
    print(f"Target size         : {TARGET_SIZE}")
    print(f"Maximum size        : {MAX_SIZE}")
    print(f"Output              : {output_file}")


if __name__ == "__main__":
    main()
