"""Diagnostic script: LLM health + Customs corpus inspection.

DO NOT commit — temporary diagnostic script.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ============================================================
# PART 1: LLM DIAGNOSTICS
# ============================================================

print("=" * 72)
print("LLM DIAGNOSTICS")
print("=" * 72)

from app.llm import LLMError, generate_answer, provider_status

print("\n--- Provider Status ---")
print(json.dumps(provider_status(), indent=2))

print("\n--- Live LLM Test (Groq primary) ---")
t0 = time.time()
try:
    out = generate_answer(
        "What is sales tax?",
        "Sales Tax Act 1990 section 3: every supplier shall charge 17%.",
    )
    elapsed = time.time() - t0
    print(f"  OK in {elapsed:.1f}s  len={len(out)}")
    print(f"  ANSWER: {out[:200]}")
except LLMError as e:
    print(f"  LLMError: {e}")

print("\n--- Missing API Key Handling ---")
from app import llm

orig_key = llm.GROQ_API_KEY
llm.GROQ_API_KEY = None
try:
    out = generate_answer("test", "context")
    print("  UNEXPECTED: no error raised")
except LLMError as e:
    print(f"  LLMError raised correctly: {str(e)[:200]}")
finally:
    llm.GROQ_API_KEY = orig_key

print("\n--- Too-Short Question (RAG engine) ---")
from app.rag_engine import FBRRAGEngine

engine = FBRRAGEngine()
r = engine.answer("ab")
print(f"  answer: {r['answer'][:200]}")
print(f"  grounded: {r['grounded']}")
print(f"  sources: {len(r['sources'])}")

print("\n--- Sufficient Evidence → LLM Generation ---")
r2 = engine.answer(
    "What is section 177 of the Income Tax Ordinance 2001?"
)
print(f"  answer_len: {len(r2['answer'])}")
print(f"  sources_count: {len(r2['sources'])}")
print(f"  grounded: {r2['grounded']}")
print(f"  answer_snippet: {r2['answer'][:200]}")

print("\n--- Out-of-Domain → Safe Refusal ---")
r3 = engine.answer("What is the quantum physics equation for black holes?")
print(f"  answer: {r3['answer'][:200]}")
print(f"  grounded: {r3['grounded']}")
print(f"  sources: {len(r3['sources'])}")

# ============================================================
# PART 2: CUSTOMS CORPUS INSPECTION
# ============================================================

print("\n" + "=" * 72)
print("CUSTOMS CORPUS INSPECTION")
print("=" * 72)

# 2a. Find customs-related raw markdown files
raw_md = ROOT / "data" / "raw" / "01-markdown"
raw_jsonl = ROOT / "data" / "raw" / "02-jsonl"
profile_md = ROOT / "data" / "profile" / "markdown"
profile_jsonl = ROOT / "data" / "profile" / "jsonl"
source_extracted = ROOT / "data" / "raw" / "04-source-docs"
cleaned = ROOT / "data" / "profile" / "source_docs" / "cleaned"
chunks_file = ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"

CUSTOMS_KEYWORDS = ["customs", "cd_act", "weboa"]


def _is_customs(path_str: str) -> bool:
    return any(kw in path_str.lower() for kw in CUSTOMS_KEYWORDS)


print("\n--- Custom docs in raw/01-markdown ---")
if raw_md.exists():
    customs_raw = [f for f in os.listdir(raw_md) if _is_customs(f)]
    print(f"  count: {len(customs_raw)}")
    for f in customs_raw:
        sz = (raw_md / f).stat().st_size
        print(f"  {sz:>8}  {f}")
else:
    print("  raw/01-markdown/ NOT FOUND")

print("\n--- Custom docs in raw/02-jsonl ---")
if raw_jsonl.exists():
    customs_jsonl = [f for f in os.listdir(raw_jsonl) if _is_customs(f)]
    print(f"  count: {len(customs_jsonl)}")
    for f in customs_jsonl:
        sz = (raw_jsonl / f).stat().st_size
        print(f"  {sz:>8}  {f}")
else:
    print("  raw/02-jsonl/ NOT FOUND")

print("\n--- Custom docs in raw/04-source-docs (extraction input) ---")
if source_extracted.exists():
    all_extracted = os.listdir(source_extracted)
    customs_in_extracted = [f for f in all_extracted if _is_customs(f)]
    print(f"  total files in 04-source-docs: {len(all_extracted)}")
    print(f"  customs files in 04-source-docs: {len(customs_in_extracted)}")
    for f in customs_in_extracted:
        print(f"  {f}")
else:
    print("  raw/04-source-docs/ NOT FOUND")

print("\n--- Custom docs in cleaned/cleaned_documents.json ---")
if cleaned.exists() and (cleaned / "cleaned_documents.json").exists():
    with open(cleaned / "cleaned_documents.json", "r", encoding="utf-8") as fh:
        docs = json.load(fh)
    customs_in_cleaned = [
        d for d in docs
        if _is_customs(str(d.get("source_path", "")))
        or _is_customs(str(d.get("source", "")))
    ]
    print(f"  total docs: {len(docs)}")
    print(f"  customs docs: {len(customs_in_cleaned)}")
    for d in customs_in_cleaned:
        print(f"  {d.get('source_path', '?')}")

print("\n--- Custom chunks in chunks.json ---")
if chunks_file.exists():
    with open(chunks_file, "r", encoding="utf-8") as fh:
        chunks = json.load(fh)
    customs_chunks = [
        c for c in chunks
        if _is_customs(str(c.get("source", "")))
        or _is_customs(str(c.get("source_path", "")))
    ]
    print(f"  total chunks: {len(chunks)}")
    print(f"  customs chunks: {len(customs_chunks)}")
else:
    print("  chunks.json NOT FOUND")

print("\n--- Custom sources in FAISS metadata.json ---")
metadata_file = ROOT / "data" / "profile" / "vectorstore" / "metadata.json"
if metadata_file.exists():
    with open(metadata_file, "r", encoding="utf-8") as fh:
        meta = json.load(fh)
    customs_in_faiss = [
        m for m in meta
        if _is_customs(str(m.get("source", "")))
        or _is_customs(str(m.get("source_path", "")))
    ]
    print(f"  total metadata rows: {len(meta)}")
    print(f"  customs metadata rows: {len(customs_in_faiss)}")
else:
    print("  metadata.json NOT FOUND")

print("\n--- Customs markdown content overview ---")
if profile_md.exists():
    for f in sorted(os.listdir(profile_md)):
        if _is_customs(f):
            content = (profile_md / f).read_text(encoding="utf-8")
            first_line = content.split("\n")[0].strip()
            print(f"  {f}: {len(content)} chars, first line: {first_line[:80]}")

print("\n" + "=" * 72)
print("DIAGNOSTICS COMPLETE")
print("=" * 72)
