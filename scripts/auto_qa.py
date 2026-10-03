"""
auto_qa.py — FBR Auto QA Generation (TASK 1)
============================================

Kya karta hai:
  1. EXISTING canonical chunks (data/profile/source_docs/chunks/chunks.json)
     se per-PDF top-3 chunks uthata hai. NAYA SPLITTER KUCH NAHI BANATA —
     same chunks jo RAG index mein hain, wohi use hote hain.
  2. Har chunk pe Groq se 2 sawal banwata hai:
        - 1 FACT question   (rate / threshold / definition / section number)
        - 1 PENALTY question (penalty / surcharge / default surcharge / fine)
     JSON format: {"q": "", "a": "", "source": ""}
     Chunk mein date/number na ho to chunk SKIP (Task rule).
  3. Generate hote hi AUTO-FILTER chalata hai (retrieval round-trip):
        - Generated sawal ko wapas APNE RAG (FBRRAGEngine.ground —
          LLM call NAHI, sirf retrieval) mein daalta hai.
        - Agar expected source top-3 mein nahi aata -> QA DELETE.
        - Pass hone wale hi output JSON mein jaate hain.

Sirf GROQ use hota hai (OpenRouter generate pe BILKUL nahi — Task rule).
Model app ki .env se aata hai (GROQ_API_KEY / GROQ_MODEL) — app.llm
ka provider chain reuse karta hai, naya client nahi banata.

Run:
    python scripts/auto_qa.py                 # default 40 QA target
    python scripts/auto_qa.py --target 20     # kam QA
    python scripts/auto_qa.py --max-pdfs 10   # sirf pehli 10 PDFs

Output:
    data/profile/auto_qa/auto_qa.json
    data/profile/auto_qa/auto_qa_rejected.json   (filter se delete hue)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# .env load (app ke dev conventions ke mutabiq)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHUNKS_PATH = PROJECT_ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
OUT_DIR = PROJECT_ROOT / "data" / "profile" / "auto_qa"
OUT_FILE = OUT_DIR / "auto_qa.json"
REJECT_FILE = OUT_DIR / "auto_qa_rejected.json"

TOP_CHUNKS_PER_PDF = 3          # Task rule: har PDF ke sirf top 3 chunks
QUESTIONS_PER_CHUNK = 2         # 1 fact + 1 penalty
TARGET_QA_DEFAULT = 40          # 1 ghante ka target (user rule)
GROQ_MAX_TOKENS = 1500          # gpt-oss-120b reasoning model hai —
                                # chhota max_tokens khaali reply deta hai
                                # (live test: ~80 tokens sirf reasoning)
GROQ_TEMPERATURE = 0.3

# Chunk skip rule: date/number hona chahiye warna QA banega hi nahi
_HAS_NUMBER = re.compile(r"\d")
_HAS_DATE_HINT = re.compile(
    r"\b(19|20)\d{2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|"
    r"\b(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    re.IGNORECASE,
)

# JSON extraction — Groq kabhi kabhi ```json fences wrap karta hai
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.DOTALL)

GENERATION_PROMPT = """You generate exam-quality Q&A pairs from FBR (Pakistan Federal Board of Revenue) source text.

From the SOURCE CHUNK below, write exactly 2 questions:
1. "fact" — asks about a concrete fact: a rate, threshold, amount, definition, or section number that appears in the chunk.
2. "penalty" — asks about a penalty, surcharge, fine, or consequence for non-compliance that appears in the chunk.

STRICT RULES:
- Every answer MUST contain the specific number, date, or rate copied EXACTLY from the chunk.
- If the chunk has NO penalty/consequence content, return only the fact question (1 item).
- Answer must be 1-3 sentences, factual, in English. No opinions, no guesses.
- "source" must be the source document name given in the chunk header.

Return ONLY a JSON array, no markdown fences, no commentary:
[{{"type": "fact", "q": "...", "a": "...", "source": "..."}},
 {{"type": "penalty", "q": "...", "a": "...", "source": "..."}}]

SOURCE CHUNK (source: {source}):
{chunk_text}
"""


# ---------------------------------------------------------------------------
# Chunk loading — EXISTING chunks, no new splitting
# ---------------------------------------------------------------------------

def load_chunks_grouped_by_source(top_per_pdf: int) -> list[dict[str, str]]:
    """
    Canonical chunks.json ko source (PDF) ke hisaab se group karta hai aur
    har PDF ke pehle `top_per_pdf` chunks (file order = document order)
    return karta hai. Yehi chunks RAG index mein hain.
    """
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        grouped[str(c.get("source") or "unknown")].append(c)

    picked: list[dict] = []
    for source, group in grouped.items():
        # file order preserved (document order); top 3 le lo
        for chunk in group[:top_per_pdf]:
            text = str(chunk.get("chunk_text") or chunk.get("text") or "").strip()
            if len(text) < 200:
                continue  # bahut chhota chunk — sawal banane layak nahi
            picked.append({
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "source": source,
                "text": text,
            })
    return picked


# ---------------------------------------------------------------------------
# Groq call — app.llm ka configured Groq provider reuse (OpenAI client)
# ---------------------------------------------------------------------------

def _groq_provider():
    """app.llm se Groq provider uthata hai (key/model/base_url wahi jo app use karti hai)."""
    from app.llm import _provider_chain, LLMError  # type: ignore[attr-defined]

    for p in _provider_chain():
        if p.name == "groq" and p.api_key:
            return p
    raise LLMError("GROQ_API_KEY not configured — generation sirf Groq pe hai, OpenRouter allowed nahi")


def groq_chat(system: str, user: str) -> str:
    """Ek Groq chat call — sirf generate ke liye. OpenRouter yahan kabhi nahi."""
    from openai import OpenAI  # app ka hi dependency — naya install nahi

    p = _groq_provider()
    client = OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=90.0)
    resp = client.chat.completions.create(
        model=p.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
    )
    return str(resp.choices[0].message.content or "")


# ---------------------------------------------------------------------------
# QA generation per chunk
# ---------------------------------------------------------------------------

def chunk_eligible(text: str) -> bool:
    """Task rule: chunk mein date/number na ho to skip karo."""
    return bool(_HAS_NUMBER.search(text) or _HAS_DATE_HINT.search(text))


def parse_qa_json(raw: str, fallback_source: str) -> list[dict[str, str]]:
    """Groq reply se JSON array nikaalta hai. Fences/extra text tolerant."""
    text = raw.strip()
    candidates: list[str] = []

    m = _JSON_BLOCK.search(text)
    if m:
        candidates.append(m.group(1))
    # direct bhi try karo (fences ke bina)
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                continue
            out: list[dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                q = str(item.get("q") or "").strip()
                a = str(item.get("a") or "").strip()
                src = str(item.get("source") or fallback_source).strip() or fallback_source
                qtype = str(item.get("type") or "fact").strip()
                if q and a:
                    out.append({"type": qtype, "q": q, "a": a, "source": src})
            if out:
                return out
        except json.JSONDecodeError:
            continue
    return []


def generate_for_chunk(chunk: dict[str, str]) -> list[dict[str, str]]:
    """Ek chunk se 1-2 QA banwata hai (fact + penalty)."""
    if not chunk_eligible(chunk["text"]):
        return []

    prompt = GENERATION_PROMPT.format(source=chunk["source"], chunk_text=chunk["text"][:6000])
    raw = groq_chat(
        system="You are a precise FBR tax-exam item writer. Output only valid JSON.",
        user=prompt,
    )
    qas = parse_qa_json(raw, chunk["source"])
    # chunk reference attach karo (auto-filter ke liye)
    for qa in qas:
        qa["chunk_id"] = chunk["chunk_id"]
    return qas


# ---------------------------------------------------------------------------
# AUTO-FILTER — generated sawal ko wapas APNE RAG mein daal ke check karo
# (LLM call nahi hoti — FBRRAGEngine.ground() sirf retrieval karta hai)
# ---------------------------------------------------------------------------

def auto_filter(qas: list[dict[str, str]], rag_engine) -> tuple[list[dict], list[dict]]:
    """
    Har generated sawal ko RAG retrieval mein wapas daalo.
    Pass: expected source top-3 retrieved sources mein ho.
    Fail: top-3 mein expected source nahi -> QA reject (delete).
    """
    passed: list[dict] = []
    rejected: list[dict] = []

    for qa in qas:
        try:
            grounded = rag_engine.ground(qa["q"], top_k=3)  # top-3 rule
            sources = [
                str(s.get("source") or "")
                for s in (grounded.get("sources") or [])
            ]
            top3_sources = [s for s in sources[:3] if s]
        except Exception as e:  # noqa: BLE001 — retrieval fail = reject (safe side)
            rejected.append({**qa, "reject_reason": f"retrieval_error: {type(e).__name__}"})
            continue

        expected = qa["source"]
        # TASK 2 fix: Windows "\\" -> "/" aur ".pdf" normalize karke compare
        # (pehle raw lower-in-lower tha jis se path-style mismatches reject ho rahe the)
        expected_norm = expected.replace("\\", "/").replace(".pdf", "").lower().strip()
        top3_norm = [s.replace("\\", "/").replace(".pdf", "").lower().strip() for s in top3_sources]
        hit = any(
            expected_norm in s or s in expected_norm
            for s in top3_norm
        )
        if hit:
            passed.append({**qa, "filter_top3_sources": top3_sources})
        else:
            rejected.append({**qa, "reject_reason": "source_not_in_top3", "filter_top3_sources": top3_sources})

    return passed, rejected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="FBR auto QA generation (Groq only) + retrieval auto-filter")
    ap.add_argument("--target", type=int, default=TARGET_QA_DEFAULT, help="kitne QA chahiye (default 40)")
    ap.add_argument("--max-pdfs", type=int, default=0, help="sirf pehli N PDFs process karo (0 = all)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Existing canonical chunks load ho rahe hain (naya splitter nahi)...")
    chunks = load_chunks_grouped_by_source(TOP_CHUNKS_PER_PDF)
    if args.max_pdfs:
        # max-pdfs: pehli N sources ke chunks hi rakho
        seen: set[str] = set()
        limited: list[dict] = []
        for c in chunks:
            if c["source"] not in seen:
                seen.add(c["source"])
                if len(seen) > args.max_pdfs:
                    break
            limited.append(c)
        chunks = limited
    print(f"      {len(set(c['source'] for c in chunks))} PDFs, {len(chunks)} chunks eligible")

    print("[2/4] RAG engine load (sirf retrieval ke liye — LLM call filter mein nahi)...")
    from app.rag_engine import FBRRAGEngine  # heavy import yahan (FAISS + model)

    rag = FBRRAGEngine()

    print(f"[3/4] Groq se QA generate (target {args.target}) — sirf Groq, OpenRouter nahi...")
    all_qas: list[dict] = []
    errors = 0
    for i, chunk in enumerate(chunks, 1):
        if len(all_qas) >= args.target:
            break
        try:
            batch = generate_for_chunk(chunk)
        except Exception as e:  # noqa: BLE001 — ek chunk fail ho to baaki chalte rahen
            errors += 1
            print(f"      chunk {chunk['chunk_id']} gen error: {type(e).__name__}: {str(e)[:120]}")
            continue
        if batch:
            all_qas.extend(batch)
            print(f"      [{i}] {chunk['source']}: +{len(batch)} QA (total {len(all_qas)})")
        else:
            print(f"      [{i}] {chunk['source']}: skipped (no numbers/date ya Groq ne 0 diye)")

    all_qas = all_qas[: args.target]

    print(f"[4/4] AUTO-FILTER: {len(all_qas)} QA wapas RAG retrieval mein (top-3 source check)...")
    passed, rejected = auto_filter(all_qas, rag)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(passed, f, ensure_ascii=False, indent=2)
    with open(REJECT_FILE, "w", encoding="utf-8") as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"Generated: {len(all_qas)} | Passed filter: {len(passed)} | Rejected: {len(rejected)} | Gen errors: {errors}")
    print(f"Output:   {OUT_FILE}")
    print(f"Rejected: {REJECT_FILE}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
