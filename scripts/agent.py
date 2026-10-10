"""
agent.py — FBR Auto-Fix Agent
=============================

Kya karta hai (3 tools + 1 loop):

  TOOL 1  test_runner      — test_pipeline.py ka wahi Layer-2 flow (reuse):
                             FBRRAGEngine.ground() -> Groq generate ->
                             strict number compare -> {q, expected_a, actual_a,
                             source, top1_score, status, tag, retrieved_sources}

  TOOL 2  failure_analyzer — har FAIL ka SIRF 1 reason (fixed taxonomy):
                             retrieval_miss          = expected source retrieved
                                                       sources mein nahi
                             generation_hallucination= source mila lekin jawab
                                                       galat (number mismatch)
                             low_confidence          = source mila, jawab sahi
                                                       path pe, lekin top1
                                                       score < 0.70
                             (priority: retrieval_miss > low_confidence >
                              generation_hallucination — root cause pehle)

  TOOL 3  fixer            — DOMINANT reason ka SIRF 1 fix (per loop):
                             retrieval_miss           -> re-chunk overlap 100->200
                             generation_hallucination -> prompt me "exact number
                                                         copy karo" line add
                             low_confidence           -> top_k 3->5

LOOP (max 2):
  Groq se 10 QA generate (sirf Groq — OpenRouter generation pe KABHI nahi)
    -> test_runner -> failure_analyzer -> 1 fix apply -> failed QAs re-test
    -> scores compare -> agla loop (ya report).

  Re-test hamesha GROQ pe (bulk rule). OpenRouter SIRF end-of-run re-test pe,
  max 10 calls (budget class, run bhar mein count hota hai).

HONESTY NOTE (re-chunk fix):
  Agent data/PDF/chunks DELETE nahi karta. retrieval_miss fix:
    1. scripts/chunk_cleaned_documents.py me OVERLAP = 120 -> 200 (recorded edit)
    2. app/config/rag_runtime_flags.json me chunks_rebuilt_overlap_200 = true
    3. REBUILD_REQUIRED = true  (run report + log me)
  FAISS index ka rebuild agent khud NAHI chalata (heavy + mid-run index change).
  Next cron run naya index use karega. Rebuild command report me print hota hai:
      python scripts/chunk_cleaned_documents.py
      python scripts/generate_embeddings.py
      python scripts/build_vector_index.py

LOG:
  Har run data/profile/auto_qa/auto_fix_log.json me APPEND hota hai
  (loop-wise pass/fail, reasons, fixes, score deltas, remaining fails).

CRON (daily 11pm, Windows Task Scheduler):
  schtasks /create /tn "FBR AutoFix Agent" /sc daily /st 23:00 /tr ^
    "\"C:\\Users\\User\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe\" -X utf8 \"D:\\All Projects\\AI Assistant fbr\\scripts\\agent.py\""

RULES:
  - Generation sirf GROQ. OpenRouter sirf re-test, max 10 calls.
  - Cache/quota layer (/answer endpoint wali) ko touch nahi karta — offline script.
  - Koi data delete nahi. Sirf 3 fixes. Har run log hota hai.
  - Golden fallback: Groq generation 0 QA de de (quota/network) to golden set
    (auto_qa.json) ke pehle N QA use hote hain — cron kabhi khaali run na chore.

Run:
  python scripts/agent.py                 # demo: 10 QA, max 2 loops
  python scripts/agent.py --target 10 --max-loops 2
  python scripts/agent.py --golden        # fresh generation ki jagah golden set
  python scripts/agent.py --selftest      # sirf analyzer/fix-picker logic test (no LLM)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))  # test_pipeline / auto_qa import ke liye

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# test_pipeline ke helpers REUSE (koi parallel system nahi):
# run_one, answer_passes, confidence_tag, llm_call, tags, TOP_K, OPENROUTER_MAX_CALLS
import test_pipeline as tp  # noqa: E402
import auto_qa as aq  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUT_DIR = PROJECT_ROOT / "data" / "profile" / "auto_qa"
LOG_FILE = OUT_DIR / "auto_fix_log.json"
GOLDEN_FILE = OUT_DIR / "auto_qa.json"

FLAGS_FILE = PROJECT_ROOT / "app" / "config" / "rag_runtime_flags.json"
CHUNKER_FILE = PROJECT_ROOT / "scripts" / "chunk_cleaned_documents.py"

DEFAULT_TARGET = 10
DEFAULT_MAX_LOOPS = 2
LOW_CONFIDENCE_THRESHOLD = 0.70   # failure_analyzer rule 3
TOP_K_FIXED = 5                   # low_confidence fix: 3 -> 5
OPENROUTER_BUDGET = tp.OPENROUTER_MAX_CALLS  # 10 — Task rule, run bhar ka budget

# Reason taxonomy (fixed — sirf ye 3)
RETRIEVAL_MISS = "retrieval_miss"
HALLUCINATION = "generation_hallucination"
LOW_CONFIDENCE = "low_confidence"

# Fix taxonomy (reason -> fix, 1:1)
FIX_RECHUNK = "rechunk_overlap_200"
FIX_PROMPT = "prompt_exact_number_line"
FIX_TOPK = "topk_3_to_5"

REASON_TO_FIX = {
    RETRIEVAL_MISS: FIX_RECHUNK,
    HALLUCINATION: FIX_PROMPT,
    LOW_CONFIDENCE: FIX_TOPK,
}

# Tie-break: jo fix sab se halka ho (runtime-only) wo pehle, heavy rebuild last.
FIX_PRIORITY = [FIX_PROMPT, FIX_TOPK, FIX_RECHUNK]

# generation_hallucination fix ka prompt line (user ke alfaaz: "exact number copy karo")
PROMPT_STRICT_LINE = (
    "Exact numbers aur dates source se word-for-word copy karo — "
    "paraphrase, rounding ya apne se number banana mana hai."
)

REBUILD_COMMANDS = (
    "python scripts/chunk_cleaned_documents.py\n"
    "  python scripts/generate_embeddings.py\n"
    "  python scripts/build_vector_index.py"
)


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Runtime state (fixes ka active/persisted status)
# ---------------------------------------------------------------------------

def load_flags() -> dict:
    """Fixes ka persisted state. Pehli run pe default bana deta hai."""
    if FLAGS_FILE.exists():
        try:
            return json.loads(FLAGS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt flag file = default se start
            pass
    return {
        "top_k": tp.TOP_K,                    # 3
        "prompt_strict": False,               # hallucination fix applied?
        "chunks_rebuilt_overlap_200": False,  # re-chunk fix applied?
    }


def save_flags(flags: dict) -> None:
    FLAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FLAGS_FILE.write_text(json.dumps(flags, indent=2), encoding="utf-8")


def active_system(flags: dict) -> str:
    """Generation system prompt — hallucination fix active ho to strict line extra."""
    base = tp.GENERATION_SYSTEM
    if flags.get("prompt_strict") and PROMPT_STRICT_LINE not in base:
        return base + " " + PROMPT_STRICT_LINE
    return base


def active_top_k(flags: dict) -> int:
    return int(flags.get("top_k") or tp.TOP_K)


# ---------------------------------------------------------------------------
# TOOL 1 — test_runner  (test_pipeline.run_one ka direct reuse)
# ---------------------------------------------------------------------------

def test_runner(qas: list[dict], rag, provider_name: str, flags: dict) -> list[dict]:
    """Har QA ka Layer-2 cycle. Active flags (top_k / system) respect karta hai."""
    system = active_system(flags)
    top_k = active_top_k(flags)
    results: list[dict] = []
    for i, qa in enumerate(qas, 1):
        r = tp.run_one(qa, rag, provider_name, top_k=top_k, system=system)
        results.append(r)
        log(f"    [{i}/{len(qas)}] {r['status']} | {r['top1_score']:.3f} | {r['tag'][:22]} | {qa['q'][:55]}")
    return results


# ---------------------------------------------------------------------------
# TOOL 2 — failure_analyzer  (fixed 3-reason taxonomy)
# ---------------------------------------------------------------------------

def _norm_source(s: str) -> str:
    """auto_qa wala normalization: Windows path + .pdf + case."""
    return (s or "").replace("\\", "/").replace(".pdf", "").lower().strip()


def failure_analyzer(result: dict) -> str:
    """
    Ek FAIL result ka reason. SIRF 3 possible values.

    Rule order (root cause pehle):
      1. expected source retrieved_sources me nahi  -> retrieval_miss
         (source hi retrieve nahi hua — generation ka dosh nahi)
      2. top1 score < 0.70                          -> low_confidence
         (source mila lekin confidence kam)
      3. warna                                      -> generation_hallucination
         (source theek mila, phir bhi jawab galat — LLM ne number banaya)
    """
    expected = _norm_source(str(result.get("source") or ""))
    retrieved = [_norm_source(s) for s in (result.get("retrieved_sources") or []) if s]
    hit = any(expected in r or r in expected for r in retrieved) if expected else False
    if not hit:
        return RETRIEVAL_MISS

    score = float(result.get("top1_score") or 0.0)
    if score < LOW_CONFIDENCE_THRESHOLD:
        return LOW_CONFIDENCE

    return HALLUCINATION


def analyze_failures(results: list[dict]) -> dict[str, list[dict]]:
    """FAIL results ko reason ke hisaab se group karta hai."""
    grouped: dict[str, list[dict]] = {RETRIEVAL_MISS: [], HALLUCINATION: [], LOW_CONFIDENCE: []}
    for r in results:
        if r.get("status") == "FAIL":
            grouped[failure_analyzer(r)].append(r)
    return grouped


# ---------------------------------------------------------------------------
# TOOL 3 — fixer
# ---------------------------------------------------------------------------

def choose_fix(grouped: dict[str, list[dict]], flags: dict) -> Optional[str]:
    """
    Dominant reason ka fix. Dominant = sab se zyada count.
    Tie pe FIX_PRIORITY (halka fix pehle). Already-active fix skip,
    uski jagah agli priority wala reason-fix try hota hai.
    """
    counts = Counter({k: len(v) for k, v in grouped.items() if v})
    if not counts:
        return None

    # dominant reason (tie -> FIX_PRIORITY order me pehla)
    def sort_key(reason: str):
        return (-counts[reason], FIX_PRIORITY.index(REASON_TO_FIX[reason]))

    ordered_reasons = sorted(counts.keys(), key=sort_key)
    for reason in ordered_reasons:
        fix = REASON_TO_FIX[reason]
        if not _fix_already_active(fix, flags):
            log(f"    dominant reason: {reason} x{counts[reason]} -> fix: {fix}")
            return fix
    # sab fixes already active — kuch naya apply nahi ho sakta
    log(f"    dominant reason: {ordered_reasons[0]} x{counts[ordered_reasons[0]]} — fix already active, skip")
    return None


def _fix_already_active(fix: str, flags: dict) -> bool:
    if fix == FIX_TOPK:
        return active_top_k(flags) >= TOP_K_FIXED
    if fix == FIX_PROMPT:
        return bool(flags.get("prompt_strict"))
    if fix == FIX_RECHUNK:
        return bool(flags.get("chunks_rebuilt_overlap_200"))
    return True


def apply_fix(fix: str, flags: dict) -> dict:
    """
    SIRF 1 fix apply. Agent data delete nahi karta — sirf ye 3 additive changes.
    Return: {type, status: applied|already_applied|error, detail}
    """
    if _fix_already_active(fix, flags):
        return {"type": fix, "status": "already_applied", "detail": "flag already set"}

    if fix == FIX_PROMPT:
        # Generation system me exact-number line (runtime state + persisted flag)
        flags["prompt_strict"] = True
        save_flags(flags)
        return {
            "type": fix,
            "status": "applied",
            "detail": f"prompt line added: \"{PROMPT_STRICT_LINE[:60]}...\"",
        }

    if fix == FIX_TOPK:
        # top_k 3 -> 5 (agent runtime + persisted flag; retriever ka default nahi chherta)
        flags["top_k"] = TOP_K_FIXED
        save_flags(flags)
        return {"type": fix, "status": "applied", "detail": f"top_k {tp.TOP_K} -> {TOP_K_FIXED}"}

    if fix == FIX_RECHUNK:
        # (a) chunker constant 120 -> 200 (recorded edit, data delete nahi)
        try:
            text = CHUNKER_FILE.read_text(encoding="utf-8")
            if re.search(r"(?m)^OVERLAP\s*=\s*200\b", text):
                detail = "chunker OVERLAP already 200"
            elif re.search(r"(?m)^OVERLAP\s*=\s*\d+", text):
                new_text = re.sub(
                    r"(?m)^OVERLAP\s*=\s*\d+.*$",
                    "OVERLAP = 200  # agent.py: retrieval_miss fix (pehle 120)",
                    text,
                    count=1,
                )
                CHUNKER_FILE.write_text(new_text, encoding="utf-8")
                detail = "chunker OVERLAP 120 -> 200"
            else:
                return {"type": fix, "status": "error", "detail": f"OVERLAP constant nahi mila: {CHUNKER_FILE.name}"}
        except Exception as e:  # noqa: BLE001
            return {"type": fix, "status": "error", "detail": f"chunker edit fail: {type(e).__name__}: {e}"}

        # (b) flag + REBUILD_REQUIRED (agent index rebuild NAHI chalata — heavy;
        #     next cron run naya index utha lega. Data kuch delete nahi hua.)
        flags["chunks_rebuilt_overlap_200"] = True
        save_flags(flags)
        return {
            "type": fix,
            "status": "applied",
            "detail": detail + "; REBUILD_REQUIRED=true; rebuild command: " + REBUILD_COMMANDS.replace("\n", " && "),
        }

    return {"type": fix, "status": "error", "detail": "unknown fix type"}


# ---------------------------------------------------------------------------
# Re-test + score comparison
# ---------------------------------------------------------------------------

def retest_failed(fails: list[dict], rag, flags: dict, golden: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Failed QAs dobara GROQ pe chalao (active fixes ke saath) aur per-QA
    score delta compare karo. OpenRouter yahan NAHI — sirf Groq.
    Return: (naye results, per-QA comparison records)
    """
    qa_by_q = {g["q"]: g for g in golden}
    new_results, comparisons = [], []
    for old in fails:
        qa = qa_by_q.get(old["q"], {"q": old["q"], "a": old["expected_a"], "source": old["source"]})
        r = tp.run_one(qa, rag, "groq", top_k=active_top_k(flags), system=active_system(flags))
        delta = round(r["top1_score"] - old["top1_score"], 4)
        comparisons.append({
            "q": old["q"],
            "old_score": old["top1_score"],
            "new_score": r["top1_score"],
            "delta": delta,
            "old_status": old["status"],
            "new_status": r["status"],
            "improved": delta > 0,
        })
        log(f"    retest {old['status']}->{r['status']} | {old['top1_score']:.3f}->{r['top1_score']:.3f} ({delta:+.3f}) | {old['q'][:50]}")
        new_results.append(r)
    return new_results, comparisons


def merge_results(results: list[dict], new_results: list[dict]) -> list[dict]:
    """Retest results ko master list me merge (q se match)."""
    new_by_q = {r["q"]: r for r in new_results}
    return [new_by_q.get(r["q"], r) for r in results]


# ---------------------------------------------------------------------------
# OpenRouter final re-test (budget 10, sirf yahan)
# ---------------------------------------------------------------------------

def openrouter_final_retest(fails: list[dict], rag, flags: dict, golden: list[dict]) -> tuple[int, list[dict]]:
    """Budget ke andar leftover FAILs OpenRouter pe. Return (calls_used, new_results)."""
    qa_by_q = {g["q"]: g for g in golden}
    used, out = 0, []
    for old in fails:
        if used >= OPENROUTER_BUDGET:
            log(f"    OpenRouter budget khatam ({OPENROUTER_BUDGET}) — baaki FAIL as-is")
            break
        qa = qa_by_q.get(old["q"], {"q": old["q"], "a": old["expected_a"], "source": old["source"]})
        try:
            r = tp.run_one(qa, rag, "openrouter", top_k=active_top_k(flags), system=active_system(flags))
            used += 1
            r["retest_provider"] = "openrouter"
            out.append(r)
            log(f"    [or {used}/{OPENROUTER_BUDGET}] {old['status']}->{r['status']} | {old['q'][:50]}")
        except Exception as e:  # noqa: BLE001 — provider down = Groq result hi final
            log(f"    [or] error: {type(e).__name__}: {str(e)[:80]}")
    return used, out


# ---------------------------------------------------------------------------
# QA source: Groq fresh generation (golden fallback ke saath)
# ---------------------------------------------------------------------------

def generate_qas(target: int, rag) -> tuple[list[dict], str]:
    """
    auto_qa.py ka reuse: existing chunks -> Groq (sirf Groq) -> 2 QA/chunk
    -> retrieval auto-filter. OpenRouter generation pe BILKUL nahi.
    0 QA bache to golden set fallback (cron safety).
    """
    log("  [gen] existing canonical chunks load (naya splitter nahi)...")
    chunks = aq.load_chunks_grouped_by_source(aq.TOP_CHUNKS_PER_PDF)
    log(f"  [gen] {len(set(c['source'] for c in chunks))} PDFs, {len(chunks)} chunks eligible")

    all_qas: list[dict] = []
    for i, chunk in enumerate(chunks, 1):
        if len(all_qas) >= target:
            break
        try:
            batch = aq.generate_for_chunk(chunk)
        except Exception as e:  # noqa: BLE001 — ek chunk fail to baaki chalte rahen
            log(f"  [gen] chunk {chunk['chunk_id']} error: {type(e).__name__}: {str(e)[:80]}")
            continue
        if batch:
            all_qas.extend(batch)
            log(f"  [gen] [{i}] {chunk['source']}: +{len(batch)} QA (total {len(all_qas)})")
    all_qas = all_qas[:target]

    log(f"  [gen] auto-filter: {len(all_qas)} QA wapas RAG retrieval me (top-3 source check)...")
    passed, rejected = aq.auto_filter(all_qas, rag)
    log(f"  [gen] passed {len(passed)} | rejected {len(rejected)}")

    if passed:
        return passed, "fresh_groq"

    log("  [gen] 0 QA bache — GOLDEN SET fallback (cron safety, generation fail tha)")
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden = json.load(f)
    return golden[:target], "golden_fallback"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_agent(target: int, max_loops: int, use_golden: bool) -> dict:
    t0 = time.time()
    flags = load_flags()
    fixes_applied: list[dict] = []
    openrouter_used = 0
    loops: list[dict] = []

    log("=" * 64)
    log("FBR AUTO-FIX AGENT")
    log("=" * 64)
    log(f"target={target} max_loops={max_loops} | flags: top_k={flags.get('top_k')} "
        f"prompt_strict={flags.get('prompt_strict')} rechunk200={flags.get('chunks_rebuilt_overlap_200')}")

    log("RAG engine load (FAISS + embeddings)...")
    from app.rag_engine import FBRRAGEngine

    rag = FBRRAGEngine()

    # ---- Step 1: QA set (Groq fresh ya golden) ----
    if use_golden:
        with open(GOLDEN_FILE, encoding="utf-8") as f:
            qas = json.load(f)[:target]
        mode = "golden"
        log(f"\n[1] Golden set se {len(qas)} QA (fresh generation skip — --golden)")
    else:
        log(f"\n[1] Groq se {target} QA generate (sirf Groq — OpenRouter generation pe nahi)...")
        qas, mode = generate_qas(target, rag)
    log(f"    QA set: {len(qas)} ({mode})")

    # ---- Step 2: Loop ----
    results = test_runner(qas, rag, "groq", flags)
    golden_copy = qas  # retest me q->qa lookup ke liye

    for loop_no in range(1, max_loops + 1):
        fails = [r for r in results if r["status"] == "FAIL"]
        log(f"\n[loop {loop_no}/{max_loops}] fails={len(fails)}/{len(results)}")
        if not fails:
            log("    sab PASS — loop khatam")
            break

        grouped = analyze_failures(fails)
        reasons = {k: len(v) for k, v in grouped.items() if v}
        log(f"    reasons: {json.dumps(reasons, ensure_ascii=False)}")

        fix = choose_fix(grouped, flags)
        if fix is None:
            log("    koi naya fix apply nahi ho sakta — ruk rahe hain")
            break

        fix_result = apply_fix(fix, flags)
        fixes_applied.append({"loop": loop_no, **fix_result})
        log(f"    fix: {fix_result['type']} -> {fix_result['status']} ({fix_result['detail'][:90]})")

        log(f"    re-test {len(fails)} failed QA (GROQ, active fixes ke saath)...")
        new_results, comparisons = retest_failed(fails, rag, flags, golden_copy)
        results = merge_results(results, new_results)

        improved = sum(1 for c in comparisons if c["improved"])
        became_pass = sum(1 for c in comparisons if c["new_status"] == "PASS")
        loops.append({
            "loop": loop_no,
            "tested": len(results),
            "failed_before": len(fails),
            "reasons": reasons,
            "fix_applied": fix_result,
            "retests": comparisons,
            "scores_improved": improved,
            "scores_worsened": len(comparisons) - improved,
            "became_pass": became_pass,
        })
        log(f"    loop {loop_no} result: improved {improved}/{len(comparisons)} | PASS bane {became_pass}")

    # ---- Step 3: Final leftover FAILs -> OpenRouter re-test (max budget) ----
    final_fails = [r for r in results if r["status"] == "FAIL"]
    or_retests: list[dict] = []
    if final_fails:
        log(f"\n[final] {len(final_fails)} FAIL -> OpenRouter re-test (budget {OPENROUTER_BUDGET}, used {openrouter_used})")
        used, or_retests = openrouter_final_retest(final_fails, rag, flags, golden_copy)
        openrouter_used += used
        results = merge_results(results, or_retests)

    # ---- Step 4: Final report ----
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = len(results) - passed
    remaining = []
    for r in results:
        if r["status"] != "FAIL":
            continue
        remaining.append({
            "q": r["q"],
            "source": r["source"],
            "reason": failure_analyzer(r),
            "top1_score": r["top1_score"],
            "openrouter_retest": r.get("retest_provider") == "openrouter",
            "actual_a": (r.get("actual_a") or "")[:300],
        })

    report = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "fixes_applied": fixes_applied,
        "remaining_failed_with_reason": remaining,
    }

    rebuild_required = bool(flags.get("chunks_rebuilt_overlap_200")) and not _index_rebuilt_since_flag()

    run_entry = {
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "target": target,
        "max_loops": max_loops,
        "qa_generation": {"requested": target, "got": len(qas)},
        "loops": loops,
        "final": report,
        "openrouter_calls_used": openrouter_used,
        "openrouter_budget": OPENROUTER_BUDGET,
        "rebuild_required": rebuild_required,
        "flags_after": flags,
        "duration_sec": round(time.time() - t0, 1),
    }
    append_log(run_entry)

    log("\n" + "=" * 64)
    log(f"REPORT: total {report['total']} | PASS {report['passed']} | FAIL {report['failed']}")
    log(f"fixes_applied: {json.dumps([{f['type']: f['status']} for f in fixes_applied], ensure_ascii=False)}")
    for rem in remaining:
        log(f"  REMAIN FAIL [{rem['reason']}] score={rem['top1_score']:.3f} or_retest={rem['openrouter_retest']} | {rem['q'][:60]}")
    if rebuild_required:
        log("\nREBUILD REQUIRED (re-chunk fix laga hai, index purana hai):")
        log("  " + REBUILD_COMMANDS)
    log(f"OpenRouter calls: {openrouter_used}/{OPENROUTER_BUDGET}")
    log(f"Log: {LOG_FILE}")
    log("=" * 64)
    return run_entry


def _index_rebuilt_since_flag() -> bool:
    """Re-chunk fix ke baad index rebuild hua ya nahi — chunker OVERLAP==200 aur
    chunks.json ka mtime chunker-edit ke baad ka ho to rebuild hua maan lo."""
    try:
        chunker_mtime = CHUNKER_FILE.stat().st_mtime
        chunks_file = PROJECT_ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
        return chunks_file.stat().st_mtime > chunker_mtime
    except OSError:
        return False


def append_log(entry: dict) -> None:
    """auto_fix_log.json me APPEND (har run ka record — kabhi overwrite nahi)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []
    if LOG_FILE.exists():
        try:
            existing = json.loads(LOG_FILE.read_text(encoding="utf-8"))
            history = existing if isinstance(existing, list) else [existing]
        except Exception:  # noqa: BLE001 — corrupt log = nayi history se start (purana backup nahi mit'ta)
            history = []
    history.append(entry)
    LOG_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def selftest() -> int:
    """Analyzer + fix-picker ka logic test — NO LLM, NO RAG. CI/cron ke liye bhi."""
    cases = [
        # (result, expected_reason)
        ({"status": "FAIL", "source": "IncomeTax.pdf", "top1_score": 0.80,
          "retrieved_sources": ["SalesTax.pdf", "FinanceAct2025.pdf"]}, RETRIEVAL_MISS),
        ({"status": "FAIL", "source": "IncomeTax.pdf", "top1_score": 0.62,
          "retrieved_sources": ["IncomeTax.pdf"]}, LOW_CONFIDENCE),
        ({"status": "FAIL", "source": "IncomeTax.pdf", "top1_score": 0.83,
          "retrieved_sources": ["IncomeTax.pdf"]}, HALLUCINATION),
    ]
    ok = True
    for res, expected in cases:
        got = failure_analyzer(res)
        status = "OK " if got == expected else "BAD"
        if got != expected:
            ok = False
        log(f"  [{status}] analyzer: {got} (expected {expected}) | score={res['top1_score']}")

    # fix-picker: teeno reason 1-1 -> tie -> sab-se halka active fix pehle
    grouped = {RETRIEVAL_MISS: [{}], HALLUCINATION: [{}], LOW_CONFIDENCE: [{}]}
    fresh_flags = {"top_k": tp.TOP_K, "prompt_strict": False, "chunks_rebuilt_overlap_200": False}
    got = choose_fix(grouped, fresh_flags)
    exp = REASON_TO_FIX[sorted(
        grouped.keys(), key=lambda r: (-len(grouped[r]), FIX_PRIORITY.index(REASON_TO_FIX[r]))
    )[0]]
    status = "OK " if got == exp == FIX_PROMPT else "BAD"
    if got != exp or got != FIX_PROMPT:
        ok = False
    log(f"  [{status}] tie-break: dominant tie -> {got} (expected {FIX_PROMPT} — halka fix pehle)")

    # already-active fix skip
    active_flags = {"top_k": TOP_K_FIXED, "prompt_strict": True, "chunks_rebuilt_overlap_200": False}
    got = choose_fix(grouped, active_flags)
    status = "OK " if got == FIX_RECHUNK else "BAD"
    if got != FIX_RECHUNK:
        ok = False
    log(f"  [{status}] active-skip: prompt+topk active -> {got} (expected {FIX_RECHUNK})")

    log("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="FBR Auto-Fix Agent (test_runner + failure_analyzer + fixer)")
    ap.add_argument("--target", type=int, default=DEFAULT_TARGET, help="kitne QA (default 10)")
    ap.add_argument("--max-loops", type=int, default=DEFAULT_MAX_LOOPS, help="max fix loops (default 2)")
    ap.add_argument("--golden", action="store_true", help="fresh Groq generation ki jagah golden set use karo")
    ap.add_argument("--selftest", action="store_true", help="sirf analyzer/fix-picker logic test (no LLM)")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    try:
        run_agent(args.target, args.max_loops, args.golden)
        return 0
    except Exception as e:  # noqa: BLE001 — cron me stack trace stdout pe aur exit code 2
        log(f"FATAL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
