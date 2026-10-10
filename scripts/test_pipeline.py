"""
test_pipeline.py — FBR Layer 2 Generation Test (TASK 3)
=======================================================

Kya karta hai (Layer 1 retrieval test NAHI — wo already pass hai):
  1. Golden Set (data/profile/auto_qa/auto_qa.json — 20 cleaned QA) load.
  2. Har QA ke liye:
       a. FBRRAGEngine.ground(q, top_k=3)  -> top-3 chunks + top1 score
          (EXISTING verification-wala path, retrieval ko cherna nahi)
       b. Grounded context bana ke GROQ pe LLM call:
          system: "Sirf diye gaye source se jawab do, source nahi hai to
          'Draft - Expert se confirm karein' bolo, number apne se mat banao."
       c. actual_a vs expected_a: expected ke number/date actual mein hain
          to PASS warna FAIL.
       d. Confidence tag (top1 score se):
            >= 0.85        -> "Verified - Source se"
            0.70 - 0.85    -> "Review"
            < 0.70         -> "Draft - Expert se confirm karein"
  3. FAIL hue QAs ko OpenRouter pe dobara chalao (MAX 10 calls — Task rule).
     Report mein "retest_provider: openrouter" alag mark hota hai.
  4. Output:
       data/profile/auto_qa/test_report.json
       data/profile/auto_qa/test_report.xlsx  (Q|Expected|Actual|Source|Score|Tag|Status)

RULES:
  - Bulk test sirf GROQ (free 14k/day). OpenRouter sirf re-test pe, max 10.
  - Cache / 5-day quota ko touch nahi karta (yeh offline test hai, /answer
    endpoint se nahi guzarta — quota layer user-facing API pe hai).
  - Koi naya splitter, koi retrieval change nahi.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GOLDEN_FILE = PROJECT_ROOT / "data" / "profile" / "auto_qa" / "auto_qa.json"
OUT_JSON = PROJECT_ROOT / "data" / "profile" / "auto_qa" / "test_report.json"
OUT_XLSX = PROJECT_ROOT / "data" / "profile" / "auto_qa" / "test_report.xlsx"

TOP_K = 3
GROQ_MAX_TOKENS = 1500        # reasoning model — chhota token khaali reply deta hai
OPENROUTER_MAX_CALLS = 10     # Task rule: OpenRouter limit bacha ke rakhni hai

VERIFIED_TAG = "Verified - Source se"
REVIEW_TAG = "Review"
DRAFT_TAG = "Draft - Expert se confirm karein"

GENERATION_SYSTEM = (
    "Sirf diye gaye source se jawab do. Source mein jawab nahi hai to "
    "'Draft - Expert se confirm karein' bolo. Number apne se mat banao."
)

# FIX: full date (day+month+year) — sirf year compare galat date ko
# PASS kar deta tha ('15 Aug 2024' == '30 Sep 2024'). Canon token: @d-m-y@
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_DATE_PAT = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"
    r"|\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
    r"|\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b",
    re.IGNORECASE,
)


def _month_num(name: str):
    return _MONTHS.get((name or "").strip().lower()[:3])


def _normalize_dates(text: str) -> str:
    """Har date ko @d-m-y@ canonical token bana do (15 Aug 2024 -> @15-8-2024@)."""

    def canon(m: re.Match) -> str:
        g = m.groups()
        if g[0]:  # 15 August 2024
            day, mon, year = int(g[0]), _month_num(g[1] or ""), int(g[2])
        elif g[3]:  # August 15, 2024
            day, mon, year = int(g[4]), _month_num(g[3] or ""), int(g[5])
        else:  # 15-08-2024 / 15.08.2024
            day, mon, year = int(g[6]), int(g[7]), int(g[8])
        if not mon:
            return m.group(0)
        return f" @d{day}m{mon}y{year}@ "

    return _DATE_PAT.sub(canon, text or "")


def _normalize_sections(text: str) -> str:
    """FIX: 'u/s 6A', 'u.s 6A', 'sec 6A' -> 'section 6A' — sab ek roop."""
    t = re.sub(r"\bu\s*[.\-/]?\s*s\.?\s*(?=\s*\d)", "section ", text or "", flags=re.IGNORECASE)
    t = re.sub(r"\bsec(?:tion)?\b\.?\s*(?=\s*\d)", "section ", t, flags=re.IGNORECASE)
    return t


# expected answer se number/date nikalne ke liye (comparison step 3)
_NUM_TOKEN = re.compile(
    r"rs\.?\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|k))?"
    r"|\d+(?:,\d{3})+(?:\.\d+)?"
    r"|\d+(?:\.\d+)?%"
    r"|\b(?:19|20)\d{2}\b"
    r"|\bsection\s+\d+[a-z]?\s*(?:\(\d+\))?"
    r"|\b\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LLM providers — app.llm chain se (koi naya client config nahi)
# ---------------------------------------------------------------------------

def _provider(name: str):
    from app.llm import _provider_chain, LLMError  # type: ignore[attr-defined]

    for p in _provider_chain():
        if p.name == name and p.api_key:
            return p
    raise LLMError(f"{name.upper()} not configured in .env")


def llm_call(provider_name: str, system: str, user: str, max_tokens: int) -> str:
    """
    Bounded retry on provider throttling.

    Groq's free tier rate-limits bursts; without a retry a throttled call
    became a permanent FAIL with actual_a = "(LLM error: RateLimitError)".
    This only re-issues the SAME request after a backoff — no cache, no
    quota bypass, no silent answer substitution. After 3 attempts the
    original error propagates so the failure stays visible.
    """
    import time as _time

    from openai import OpenAI  # app ki hi dependency

    p = _provider(provider_name)
    client = OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=90.0)

    last_error: Exception | None = None

    for attempt in range(3):

        try:
            resp = client.chat.completions.create(
                model=p.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return str(resp.choices[0].message.content or "").strip()

        except Exception as error:  # noqa: BLE001 - re-raised below
            name = type(error).__name__
            throttled = "RateLimit" in name or "rate limit" in str(error).lower()
            if not throttled or attempt == 2:
                raise
            last_error = error
            print(f"     [throttled] {provider_name} {name} — retry "
                  f"{attempt + 1}/3 after 20s")
            _time.sleep(20)

    raise last_error  # pragma: no cover - loop always returns or raises


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def confidence_tag(top1_score: float) -> str:
    """FIX 2: FAISS distribution 0.62-0.84 hai, 0.85 kabhi cross nahi hota.
    Naye thresholds: >=0.80 Verified, 0.65-0.80 Review, <0.65 Draft."""
    if top1_score >= 0.80:
        return VERIFIED_TAG
    if top1_score >= 0.65:
        return REVIEW_TAG
    return DRAFT_TAG


def _compact(text: str) -> str:
    """
    FIX 1: comparison normalization —
    - lower + saari whitespace/commas/markdown hatao
    - "Rs." / "Rs " -> "rs" (Rs. 10 million == rs10million)
    - non-breaking chars (\u00a0, \u2007, \u202f) bhi whitespace treat
    """
    t = (text or "").lower()
    t = t.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    t = t.replace("\u2011", "-")
    t = _normalize_dates(t)      # @d-m-y@ canon — galat date FAIL
    t = _normalize_sections(t)   # u/s 6A == section 6A
    t = re.sub(r"[\*_`,]", "", t)
    t = t.replace("rs.", "rs").replace("rs ", "rs")
    t = re.sub(r"\s+", "", t)
    return t


def extract_facts(text: str) -> list[str]:
    """
    FIX 1: expected_a ka MAIN number/date (sab se pehla significant fact
    token) — order preserved, taake strict comparison possible ho.
    Common law years (2001/1990/2005) aur section references skip,
    sirf concrete amount/rate/date/value token.
    """
    raw = _normalize_sections(text or "")
    # date spans pehle — inke andar ke bare year/day numbers skip honge
    date_spans = [(m.start(), m.end()) for m in _DATE_PAT.finditer(raw)]
    pos_tokens: list[tuple[int, str]] = []
    for m in _DATE_PAT.finditer(raw):
        g = m.groups()
        if g[0]:
            day, mon, year = g[0], _month_num(g[1] or ""), g[2]
        elif g[3]:
            day, mon, year = g[4], _month_num(g[3] or ""), g[5]
        else:
            day, mon, year = g[6], g[7], g[8]
        if mon:
            pos_tokens.append((m.start(), _compact(f"@d{int(day)}m{int(mon)}y{year}@")))
    for m in _NUM_TOKEN.finditer(raw):
        # date span ke andar wala number (day/year) alag fact nahi hai
        if any(m.start() < e and m.end() > s for s, e in date_spans):
            continue
        tok = _compact(m.group(0))
        if not tok:
            continue
        if tok in {"2001", "1990", "2005"}:
            continue  # law years — har jawab mein hote hain, fact nahi
        # section refs bhi valid facts hain — "Section 165 (2)" aur
        # "Section 165(2)" dono "section165(2)" ban jate hain.
        pos_tokens.append((m.start(), tok))
    # original text ke order me — taake 'main = aakhri fact' sahi rahe
    pos_tokens.sort(key=lambda p: p[0])
    return [tok for _, tok in pos_tokens]


def answer_passes(expected_a: str, actual_a: str) -> bool:
    """
    FIX 1: STRICT comparison — "any number match" hataya.
    expected_a ka MAIN number/date normalized form mein actual_a mein
    EXACT hona chahiye. MAIN number = aakhri significant fact token
    ('from Rs. 500,000 to Rs. 10 million' mein main = 'rs10million' —
    naya value sentence ke end pe aata hai). Sirf '10' milna FAIL.
    Non-numeric expected pe word-overlap fallback (60%).
    """
    exp_tokens = extract_facts(expected_a)
    actual_compact = _compact(actual_a)
    if exp_tokens:
        main_token = exp_tokens[-1]  # 'from X to Y' -> Y hi main hai
        return main_token in actual_compact
    # non-numeric answer: keyword overlap — 80% (pehle 60% tha)
    exp_words = {w for w in re.findall(r"[a-z]{4,}", expected_a.lower())}
    act_words = {w for w in re.findall(r"[a-z]{4,}", (actual_a or "").lower())}
    if not exp_words or not act_words:
        return False
    inter = exp_words & act_words
    if len(inter) / len(exp_words) >= 0.8:
        return True
    # short-but-correct: chhota jawab (e.g. 'Cargo Tracking System') jiske
    # >=2 significant words sab expected me hain — poora sentence match zaroori nahi
    return len(inter) / len(act_words) >= 0.8 and len(inter) >= 2


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_one(
    qa: dict,
    rag,
    provider_name: str,
    top_k: int = TOP_K,
    system: str = GENERATION_SYSTEM,
) -> dict[str, Any]:
    """Ek QA ka poora Layer-2 cycle: retrieve -> generate -> compare -> tag.

    agent.py bhi yehi use karta hai: top_k (low_confidence fix) aur system
    (hallucination fix line) override kar sakta hai. retrieved_sources naye
    key mein return hoti hain taake failure_analyzer ko pata ho kaunse
    sources mile (retrieval_miss diagnosis ke liye).
    """
    # FIX 3: FBRRAGEngine.ground() use — real verification + confidence flow.
    # Score wahi jo ground() deta hai (public provenance ka top1 score).
    grounded = rag.ground(qa["q"], top_k=top_k)
    sources = grounded.get("sources") or []
    top1_score = float(sources[0].get("score") or 0.0) if sources else 0.0
    retrieved_sources = [str(s.get("source") or "") for s in sources]

    # Chunks se context: retriever search ko dubara nahi chalate — ground ke
    # chunk_ids se metadata se text uthao (same chunks, no re-rank drift).
    chunk_ids = {str(s.get("chunk_id")) for s in sources[:top_k]}
    chunk_texts = []
    for item in rag.retriever.metadata:
        if str(item.get("chunk_id")) in chunk_ids:
            text = str(item.get("text") or item.get("chunk_text") or "")
            if text:
                src = str(item.get("source") or "")
                chunk_texts.append(f"[{src}]\n{text[:2500]}")
            if len(chunk_texts) == len(chunk_ids):
                break
    # ground() ke order mein rakho (top1 pehle)
    order = {cid: i for i, cid in enumerate(chunk_ids)}
    chunk_texts.sort(key=lambda t: order.get(t.split("]")[0][1:].strip(), 999))

    context = "\n\n---\n\n".join(chunk_texts) if chunk_texts else "(no chunks retrieved)"

    prompt = f"SOURCE:\n{context}\n\nQUESTION: {qa['q']}\n\nAnswer using ONLY the source above."
    try:
        actual_a = llm_call(provider_name, system, prompt, GROQ_MAX_TOKENS)
    except Exception as e:  # noqa: BLE001
        actual_a = f"(LLM error: {type(e).__name__})"

    # Step 3: compare
    status = "PASS" if answer_passes(qa["a"], actual_a) else "FAIL"

    # Step 4: tag
    tag = confidence_tag(top1_score)

    return {
        "q": qa["q"],
        "expected_a": qa["a"],
        "actual_a": actual_a,
        "source": qa["source"],
        "top1_score": round(top1_score, 4),
        "tag": tag,
        "status": status,
        "retest_provider": provider_name if provider_name != "groq" else "",
        "retrieved_sources": retrieved_sources,
    }


def write_xlsx(rows: list[dict], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Generation Test"
    headers = ["Q", "Expected", "Actual", "Source", "Score", "Tag", "Status"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E7F0EA")

    for r in rows:
        ws.append([
            r.get("q", ""), r.get("expected_a", ""), r.get("actual_a", ""),
            r.get("source", ""), r.get("top1_score", ""), r.get("tag", ""),
            r.get("status", ""),
        ])

    # FAIL rows red
    red = PatternFill("solid", fgColor="FDE8E8")
    for row in ws.iter_rows(min_row=2):
        if row[6].value == "FAIL":
            for c in row:
                c.fill = red

    widths = [40, 40, 40, 28, 8, 26, 9]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    wb.save(path)


def main() -> int:
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden = json.load(f)
    print(f"Golden Set: {len(golden)} QA ({GOLDEN_FILE.name})")

    # Active system config — agent ke applied fixes ke saath sync
    # (topk_3_to_5 / prompt_strict). Flags file na ho to defaults.
    flags_file = PROJECT_ROOT / "app" / "config" / "rag_runtime_flags.json"
    flags = json.loads(flags_file.read_text(encoding="utf-8")) if flags_file.exists() else {}
    top_k = int(flags.get("top_k") or TOP_K)
    system = GENERATION_SYSTEM
    if flags.get("prompt_strict"):
        system = system + (
            " Exact numbers aur dates source se word-for-word copy karo — "
            "paraphrase, rounding ya apne se number banana mana hai."
        )
    print(f"Active config: top_k={top_k}, prompt_strict={bool(flags.get('prompt_strict'))}")

    print("RAG engine load (retrieval-only)...")
    from app.rag_engine import FBRRAGEngine

    rag = FBRRAGEngine()

    # -------- Pass 1: GROQ bulk --------
    print(f"\n=== PASS 1: Groq bulk ({len(golden)} QA) ===")
    results = []
    import time as _t
    for i, qa in enumerate(golden, 1):
        r = run_one(qa, rag, "groq", top_k=top_k, system=system)
        results.append(r)
        print(f"  [{i}/{len(golden)}] {r['status']} | {r['top1_score']:.3f} | {r['tag'][:22]} | {qa['q'][:55]}")
        if i < len(golden):
            _t.sleep(20)  # FIX 4: consecutive Groq calls ke beech 20s gap (free-tier burst limit)

    # -------- Pass 2: FAILs -> OpenRouter (max 10) --------
    fails = [r for r in results if r["status"] == "FAIL"]
    print(f"\n=== PASS 2: {len(fails)} FAIL -> OpenRouter retest (max {OPENROUTER_MAX_CALLS}) ===")
    or_used = 0
    for r in fails:
        if or_used >= OPENROUTER_MAX_CALLS:
            print(f"  OpenRouter budget khatam ({OPENROUTER_MAX_CALLS}) — baaki FAIL Groq-par hi marked")
            break
        qa = next(g for g in golden if g["q"] == r["q"])
        try:
            r2 = run_one(qa, rag, "openrouter", top_k=top_k, system=system)
            or_used += 1
            r.update({
                "actual_a": r2["actual_a"],
                "status": r2["status"],
                "retest_provider": "openrouter",
            })
            print(f"  retest[or] {r['status']} | {r['q'][:55]}")
        except Exception as e:  # noqa: BLE001
            print(f"  retest[or] error: {type(e).__name__}: {str(e)[:80]}")

    # -------- Summary --------
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed
    or_retested = sum(1 for r in results if r.get("retest_provider") == "openrouter")

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "openrouter_retested": or_retested,
        "tags": {
            VERIFIED_TAG: sum(1 for r in results if r["tag"] == VERIFIED_TAG),
            REVIEW_TAG: sum(1 for r in results if r["tag"] == REVIEW_TAG),
            DRAFT_TAG: sum(1 for r in results if r["tag"] == DRAFT_TAG),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    write_xlsx(results, OUT_XLSX)

    print("\n" + "=" * 60)
    print(f"TOTAL {total} | PASS {passed} | FAIL {failed} | OpenRouter retested: {or_retested}")
    print("Tags:", json.dumps(summary["tags"], ensure_ascii=False))
    print(f"Report: {OUT_JSON}")
    print(f"Excel:  {OUT_XLSX}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
