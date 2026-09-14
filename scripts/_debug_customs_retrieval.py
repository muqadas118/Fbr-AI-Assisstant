"""Debug: inspect retrieval for customs queries after ingestion."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from app.hybrid_retriever import FBRHybridRetriever

r = FBRHybridRetriever()

QUERIES = [
    "What is customs duty on imported goods?",
    "What is DIRBS?",
]

for q in QUERIES:
    print("=" * 72)
    print(f"QUERY: {q}")
    hits = r.search(q, top_k=10)
    for i, hit in enumerate(hits):
        meta = r.metadata[hit["index"]]
        src = str(meta.get("source", ""))
        text = str(meta.get("text", ""))[:90].replace("\n", " ")
        print(
            f"  [{i}] h={hit.get('score', 0):.4f} v={hit.get('semantic_score', 0):.4f} "
            f"b={hit.get('bm25_score', 0):.4f} src={src}"
        )
        print(f"      {text}")

    sem = r._semantic_search(q, top_k=10)
    print("  -- pure semantic top-10 --")
    for idx, score in sorted(sem.items(), key=lambda kv: -kv[1]):
        src = str(r.metadata[idx].get("source", ""))
        flag = " <== CUSTOMS" if src.startswith("customs/") else ""
        print(f"      v={score:.4f} row={idx} src={src}{flag}")

    bm = r._bm25_search(q, top_k=10)
    print("  -- pure bm25 top-10 --")
    for idx, score in sorted(bm.items(), key=lambda kv: -kv[1]):
        src = str(r.metadata[idx].get("source", ""))
        flag = " <== CUSTOMS" if src.startswith("customs/") else ""
        print(f"      b={score:.4f} row={idx} src={src}{flag}")

print("=" * 72)
print("Customs chunk sample (last 5 rows of metadata):")
for idx in range(len(r.metadata) - 5, len(r.metadata)):
    meta = r.metadata[idx]
    print(
        f"  row={idx} vector_id={meta.get('vector_id')} src={meta.get('source')} "
        f"text={str(meta.get('text', ''))[:80]!r}"
    )

query_vec = r.model.encode(
    ["What is customs duty on imported goods?"],
    normalize_embeddings=True,
    convert_to_numpy=True,
).astype("float32")

customs_rows = [
    idx
    for idx, meta in enumerate(r.metadata)
    if str(meta.get("source", "")).startswith("customs/")
]
print(f"customs rows in metadata: {len(customs_rows)}")
scores, rows = r.index.search(query_vec, 20)
print("top-20 FAISS rows for the query:")
for score, row in zip(scores[0], rows[0]):
    src = str(r.metadata[int(row)].get("source", ""))
    print(f"  v={score:.4f} row={int(row)} src={src}")
