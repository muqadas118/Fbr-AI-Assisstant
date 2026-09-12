import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK_DIR = ROOT / "data" / "profile" / "source_docs" / "chunks"
CHUNK_FILE = CHUNK_DIR / "chunks.json"
NORMALIZED_DIR = ROOT / "data" / "profile" / "source_docs" / "cleaned"
SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"

REQUIRED = {"chunk_id", "document_id", "source", "source_path", "source_sha256", "document_type", "title", "publication_date", "effective_date", "page_start", "page_end", "heading", "section_reference", "chunk_index", "chunk_text", "text", "text_chars", "table_data"}

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    chunk_file = Path(os.environ.get("CHUNK_FILE", str(CHUNK_FILE)))
    normalized_file = Path(os.environ.get("NORMALIZED_FILE", str(NORMALIZED_DIR / "cleaned_documents.json")))
    chunks = json.loads(chunk_file.read_text(encoding="utf-8"))
    documents = json.loads(normalized_file.read_text(encoding="utf-8"))
    docs = {d["document_id"]: d for d in documents}
    ids = set()
    errors = []
    per_doc = {}
    for index, chunk in enumerate(chunks, 1):
        missing = REQUIRED - set(chunk) if isinstance(chunk, dict) else REQUIRED
        if missing:
            errors.append(f"chunk {index}: missing {sorted(missing)}")
            continue
        cid = chunk["chunk_id"]
        if cid in ids:
            errors.append(f"chunk {index}: duplicate chunk_id")
        ids.add(cid)
        doc = docs.get(chunk["document_id"])
        if doc is None:
            errors.append(f"chunk {index}: orphan document_id")
            continue
        if chunk["source_path"] != doc["source_path"] or chunk["source_sha256"] != doc["source_sha256"] or chunk["source"] != doc["source"]:
            errors.append(f"chunk {index}: provenance mismatch")
        if not isinstance(chunk["chunk_text"], str) or not chunk["chunk_text"].strip() or chunk["text"] != chunk["chunk_text"] or chunk["text_chars"] != len(chunk["chunk_text"]):
            errors.append(f"chunk {index}: invalid text")
        start, end = chunk["page_start"], chunk["page_end"]
        if start is not None and (not isinstance(start, int) or start < 1):
            errors.append(f"chunk {index}: invalid page_start")
        if end is not None and (not isinstance(end, int) or end < 1 or (start is not None and end < start)):
            errors.append(f"chunk {index}: invalid page_end")
        if not isinstance(chunk["chunk_index"], int) or chunk["chunk_index"] < 0:
            errors.append(f"chunk {index}: invalid chunk_index")
        per_doc.setdefault(chunk["document_id"], []).append(chunk)
        if chunk["table_data"] is not None and not isinstance(chunk["table_data"], dict):
            errors.append(f"chunk {index}: invalid table_data")
    for document in documents:
        records = per_doc.get(document["document_id"], [])
        if document["status"] == "manual_review_required" and records:
            errors.append(f"manual-review document has chunks: {document['source_path']}")
        indices = [item["chunk_index"] for item in records]
        if indices != list(range(len(indices))):
            errors.append(f"non-contiguous chunk indexes: {document['source_path']}")
        source = SOURCE_DIR / document["source_path"]
        if not source.is_file() or sha256_file(source) != document["source_sha256"]:
            errors.append(f"source hash mismatch: {document['source_path']}")
    print(f"Normalized documents : {len(documents)}")
    print(f"Chunks               : {len(chunks)}")
    print(f"Documents with chunks: {len(per_doc)}")
    print(f"Validation errors    : {len(errors)}")
    for error in errors[:30]:
        print(f"[INVALID] {error}")
    if errors:
        print("CHUNK VALIDATION: FAIL")
        sys.exit(1)
    print("CHUNK VALIDATION: PASS")

if __name__ == "__main__":
    main()
