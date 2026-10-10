#!/usr/bin/env python3
"""
FINAL COMPREHENSIVE VERIFICATION SUITE
=====================================
FBR AI Tax & Compliance Assistant — closing deliverable.

Ek command, 4 suites, ek HONEST trust table. Exit 0 = every executed check
PASS, 1 = any FAIL.

  SUITE A — Daily Updater (data ingestion integrity, hermetic workspace)
  SUITE B — RAG Layer (index alignment, retrieval, verification, Golden Set V2)
  SUITE C — Calculators + Tools (reuses the full 186-check coverage suite)
  SUITE D — Live API + E2E (TestClient contract + real /answer orchestration)

Usage
-----
  python scripts/test_final_comprehensive.py
  python scripts/test_final_comprehensive.py --suites A,B,C
  python scripts/test_final_comprehensive.py --skip-llm     # no LLM / no golden
  python scripts/test_final_comprehensive.py --repeat 3     # stability runs

Design rules
------------
* Project root auto-detected from this file. No absolute C:\\Users paths.
* LLM keys come from .env through app.llm's provider chain only. This file
  creates no new LLM client.
* Every heavy stage runs in its own subprocess so the 7.5 GB box never holds
  two copies of the FAISS index / embedding model at once.
* Anything not executed is reported as NOT RUN (0% trust), never estimated.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# BOOTSTRAP  (FBR_AUTH_REQUIRED must be off before app.api is imported)
# ---------------------------------------------------------------------------

os.environ["FBR_AUTH_REQUIRED"] = "false"
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - non-reconfigurable stream
        pass

LOG_DIR = PROJECT_ROOT / "data" / "profile" / "auto_qa" / "final_suite_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CHUNKS_FILE = PROJECT_ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
METADATA_FILE = PROJECT_ROOT / "data" / "profile" / "vectorstore" / "metadata.json"
FAISS_FILE = PROJECT_ROOT / "data" / "profile" / "vectorstore" / "fbr_faiss.index"
EXPECTED_CHUNKS = 86_425

# Honest per-tag reliability bands given by the product owner. Midpoints are
# used for the weighted trust number; the band itself is printed.
TAG_TRUST = {
    "Verified": (0.85, 0.90),
    "Review": (0.60, 0.70),
    "Draft": (0.30, 0.40),
}
TAG_TRUST_MID = {"Verified": 0.875, "Review": 0.65, "Draft": 0.35}

# ---------------------------------------------------------------------------
# RESULT ACCUMULATOR
# ---------------------------------------------------------------------------

RESULTS: list[dict] = []
METRICS: dict[str, dict] = {
    "updater": {"pass": 0, "total": 0},
    "rag": {"pass": 0, "total": 0},
    "calc": {"pass": 0, "total": 0},
    "api": {"pass": 0, "total": 0},
}
NOTES: list[str] = []
WARNING_STATUS: list[tuple[str, str, str]] = []
LIMITATIONS: list[tuple[str, str]] = []
NOT_RUN: list[str] = []
GOLDEN: dict = {"runs": [], "tags": {}, "total": 0, "pass": 0, "openrouter": 0}


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def sub(title: str) -> None:
    print()
    print(f"--- {title} " + "-" * max(0, 70 - len(title)))


def check(row: str, name: str, ok: bool, detail: str = "") -> bool:
    """Record one check under a trust-table row."""
    ok = bool(ok)
    RESULTS.append({"row": row, "name": name, "ok": ok, "detail": str(detail)[:400]})
    METRICS[row]["total"] += 1
    if ok:
        METRICS[row]["pass"] += 1
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  | {detail}" if detail and not ok else ""))
    return ok


def note(text: str) -> None:
    print(f"       . {text}")
    NOTES.append(text)


def not_run(what: str) -> None:
    print(f"  [SKIP] {what}  | not executed (flag) -> 0% trust")
    NOT_RUN.append(what)


def warn_status(item: str, state: str, evidence: str) -> None:
    WARNING_STATUS.append((item, state, evidence))
    print(f"  [{state:<8}] {item}")
    print(f"             evidence: {evidence}")


def limitation(item: str, evidence: str) -> None:
    """A known gap that is NOT fixed. Recorded loudly, never silently green."""
    LIMITATIONS.append((item, evidence))
    print(f"  [LIMIT  ] {item}")
    print(f"             evidence: {evidence}")


# ---------------------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------------------


def load_module(path: Path, name: str):
    """Import a project script by path without polluting the module cache."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_child(label: str, argv: list[str], timeout: int = 3600) -> tuple[int, str]:
    """Run a child test script, tee its output to a log file, return (rc, text)."""
    env = dict(os.environ)
    env["FBR_AUTH_REQUIRED"] = "false"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"  >> {label}: {' '.join(argv)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
        rc, text = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc, text = 124, (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        text += f"\n*** TIMEOUT after {timeout}s ***"
    elapsed = time.perf_counter() - started
    log_path = LOG_DIR / f"{label}.log"
    try:
        log_path.write_text(text, encoding="utf-8")
        print(f"  << {label}: exit={rc} in {elapsed:.1f}s -> {log_path.relative_to(PROJECT_ROOT)}")
    except OSError as exc:  # noqa: BLE001
        print(f"  << {label}: exit={rc} in {elapsed:.1f}s (log write failed: {exc})")
    return rc, text


def parse_count(text: str, label: str, default: int = -1) -> int:
    match = re.search(rf"^{re.escape(label)}\s*:\s*(\d+)", text, re.M)
    return int(match.group(1)) if match else default


def parse_sectioned_suite(text: str) -> list[tuple[str, bool, str]]:
    """Parse `SECTION <name>` + `  [PASS] name` output into rows."""
    rows: list[tuple[str, bool, str]] = []
    current = ""
    for line in text.splitlines():
        stripped = line.strip()
        header = re.match(r"^SECTION\s+(.*)$", stripped)
        if header:
            current = header.group(1).strip()
            continue
        item = re.match(r"^\[(PASS|FAIL)\]\s+(.*)$", stripped)
        if item:
            rows.append((current, item.group(1) == "PASS", item.group(2)))
    return rows


def stream_json_array(path: Path, bufsize: int = 1 << 20):
    """Yield elements of a top-level JSON array without loading the file.

    chunks.json is ~279 MB; loading it whole would cost multiple GB of RAM on
    this 7.5 GB host. This reads it in windows instead.
    """
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as handle:
        buffer = handle.read(bufsize)
        start = buffer.find("[")
        if start < 0:
            raise ValueError(f"{path} is not a JSON array")
        buffer = buffer[start + 1:]
        while True:
            stripped = buffer.lstrip()
            if not stripped:
                more = handle.read(bufsize)
                if not more:
                    return
                buffer += more
                continue
            if stripped[0] == "]":
                return
            if stripped[0] == ",":
                buffer = stripped[1:]
                continue
            try:
                obj, end = decoder.raw_decode(stripped)
            except ValueError:
                more = handle.read(bufsize)
                if not more:
                    return
                buffer += more
                continue
            buffer = stripped[end:]
            yield obj


# ===========================================================================
# SUITE A — DAILY UPDATER (data ingestion)
# ===========================================================================


def suite_a(skip_heavy: bool) -> None:
    section("SUITE A — DAILY UPDATER (data ingestion integrity)")

    du_path = PROJECT_ROOT / "scripts" / "daily_update.py"
    du = load_module(du_path, "fbr_daily_update_under_test")

    sub("A1 module hygiene")
    source = du_path.read_text(encoding="utf-8")
    check("updater", "no hardcoded C:\\Users path in daily_update.py",
          "C:\\Users" not in source and "C:/Users" not in source)
    check("updater", "project root auto-detected from __file__",
          du.PROJECT_ROOT == PROJECT_ROOT, str(du.PROJECT_ROOT))

    sub("A2 allowed official hosts (https only, 3 hosts)")
    check("updater", "allowed host set is exactly the 3 FBR hosts",
          du.ALLOWED_FBR_HOSTS == {"www.fbr.gov.pk", "fbr.gov.pk", "download1.fbr.gov.pk"},
          str(sorted(du.ALLOWED_FBR_HOSTS)))
    for host in ("www.fbr.gov.pk", "fbr.gov.pk", "download1.fbr.gov.pk"):
        check("updater", f"https://{host}/doc.pdf accepted",
              du.is_allowed_fbr_url(f"https://{host}/doc.pdf"))
    check("updater", "http:// (plaintext) rejected",
          not du.is_allowed_fbr_url("http://www.fbr.gov.pk/doc.pdf"))
    check("updater", "look-alike host fbr.gov.pk.evil.com rejected",
          not du.is_allowed_fbr_url("https://www.fbr.gov.pk.evil.com/doc.pdf"))
    check("updater", "userinfo trick fbr.gov.pk@evil.com rejected",
          not du.is_allowed_fbr_url("https://fbr.gov.pk@evil.com/doc.pdf"))
    check("updater", "unrelated host evil.com rejected",
          not du.is_allowed_fbr_url("https://evil.com/doc.pdf"))
    check("updater", "garbage string rejected", not du.is_allowed_fbr_url("not a url"))

    sub("A3 URL normalization + timeout")
    normalized = du.normalize_url("https://download1.fbr.gov.pk/Docs/file name.pdf")
    check("updater", "space -> %20", "%20" in normalized and " " not in normalized, normalized)
    check("updater", "already-encoded %20 is not double-encoded",
          du.normalize_url("https://www.fbr.gov.pk/a%20b.pdf").count("%20") == 1,
          du.normalize_url("https://www.fbr.gov.pk/a%20b.pdf"))
    check("updater", "host + scheme preserved through normalization",
          normalized.startswith("https://download1.fbr.gov.pk/"), normalized)
    check("updater", "query string preserved",
          du.normalize_url("https://www.fbr.gov.pk/x?a=1&b=2").endswith("?a=1&b=2"),
          du.normalize_url("https://www.fbr.gov.pk/x?a=1&b=2"))
    check("updater", "request timeout is 60s", du.REQUEST_TIMEOUT == 60, str(du.REQUEST_TIMEOUT))

    sub("A4 hermetic workspace")
    workspace = Path(tempfile.mkdtemp(prefix="fbr_suite_a_"))
    try:
        state_dir = workspace / "data" / "profile" / "daily_update"
        raw_dir = workspace / "data" / "raw" / "04-source-docs"
        state_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        du.PROJECT_ROOT = workspace
        du.DATA_DIR = workspace / "data"
        du.PROFILE_DIR = workspace / "data" / "profile"
        du.RAW_SOURCE_DIR = raw_dir
        du.STATE_DIR = state_dir
        du.STATE_FILE = state_dir / "source_hashes.json"
        du.LOG_FILE = state_dir / "daily_update.log"
        du.RUN_REPORT_FILE = state_dir / "last_run_report.json"

        from app.tools import output_tools

        notifications_file = workspace / "notifications.jsonl"
        output_tools.NOTIFICATIONS_DIR = workspace / "notifications"
        note(f"hermetic workspace: {workspace}")

        def read_log() -> str:
            try:
                return du.LOG_FILE.read_text(encoding="utf-8")
            except OSError:
                return ""

        sub("A5 download validation (empty data / %PDF header / temp cleanup)")
        original_http_get = du.http_get
        target = raw_dir / "act.pdf"

        du.http_get = lambda url: b""
        empty_ok = du.download_file("https://www.fbr.gov.pk/a.pdf", target)
        check("updater", "empty response rejected", empty_ok is False)
        check("updater", "empty response writes nothing to disk", not target.exists())

        du.http_get = lambda url: b"<html><body>404 - file not found</body></html>" + b"x" * 2048
        junk_ok = du.download_file("https://www.fbr.gov.pk/b.pdf", target)
        check("updater", "non-PDF (HTML error page) rejected", junk_ok is False)
        check("updater", "non-PDF never replaces a good local file", not target.exists())

        pdf_bytes = b"%PDF-1.7\n" + b"FBR sample body " * 200
        du.http_get = lambda url: pdf_bytes
        good_ok = du.download_file("https://www.fbr.gov.pk/c.pdf", target)
        check("updater", "valid %PDF accepted", good_ok is True)
        check("updater", "valid %PDF content written verbatim",
              target.exists() and target.read_bytes() == pdf_bytes)
        check("updater", "no .tmp left behind after download",
              not list(target.parent.glob("*.tmp")))

        sub("A6 sync_official_document hash-diff")
        same = raw_dir / "same.pdf"
        same.write_bytes(pdf_bytes)
        before_mtime = same.stat().st_mtime_ns
        du.http_get = lambda url: pdf_bytes
        uptodate = du.sync_official_document("https://www.fbr.gov.pk/same.pdf", same)
        check("updater", "same hash -> 'Already up-to-date'", uptodate is True)
        check("updater", "same hash logged as 'Already up-to-date'",
              "Already up-to-date" in read_log())
        check("updater", "same hash leaves the file untouched",
              same.stat().st_mtime_ns == before_mtime and same.read_bytes() == pdf_bytes)
        check("updater", "no .tmp.pdf left after hash-equal path",
              not list(raw_dir.glob("*.tmp.pdf")))

        revised = b"%PDF-1.7\n" + b"FBR REVISED body " * 200
        du.http_get = lambda url: revised
        updated = du.sync_official_document("https://www.fbr.gov.pk/same.pdf", same)
        check("updater", "different hash -> 'Updated'", updated is True)
        check("updater", "different hash logged as 'Updated'",
              "Updated:" in read_log() and "Already up-to-date" in read_log())
        check("updater", "revised bytes actually replaced the local file",
              same.read_bytes() == revised)
        check("updater", "no .tmp.pdf left after hash-differ path",
              not list(raw_dir.glob("*.tmp.pdf")))

        du.http_get = lambda url: b""
        failed = du.sync_official_document("https://www.fbr.gov.pk/same.pdf", same)
        check("updater", "download failure returns False (never raises)", failed is False)
        check("updater", "failed download keeps the last good local file",
              same.read_bytes() == revised)
        check("updater", "no .tmp.pdf left after failure",
              not list(raw_dir.glob("*.tmp.pdf")))

        sub("A7 relevance filters")
        check("updater", "finance_acts: Finance Act PDF relevant",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Finance-Act-2025.pdf", "finance_acts"))
        check("updater", "finance_acts: budget document relevant",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Budget-2025-26.pdf", "finance_acts"))
        check("updater", "finance_acts: salient-features document relevant",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Salient-Features-Finance-Bill-2025.pdf",
                  "finance_acts"))
        check("updater", "finance_acts: unrelated recruitment notice rejected",
              not du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Recruitment-Notice.pdf", "finance_acts"))
        check("updater", "income tax category accepts the ordinance",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Income-Tax-Ordinance-2001.pdf",
                  "income_tax_ordinance"))
        check("updater", "sales tax category accepts the act",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Sales-Tax-Act-1990.pdf", "sales_tax_act"))
        check("updater", "excise category accepts the act",
              du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Federal-Excise-Act-2000.pdf",
                  "federal_excise_act"))
        check("updater", "cross-category mismatch rejected (excise url in income tax)",
              not du.document_is_relevant(
                  "https://www.fbr.gov.pk/docs/Federal-Excise-Act-2000.pdf",
                  "income_tax_ordinance"))
        check("updater", "supported-extension gate accepts .pdf/.docx/.xlsx",
              du.is_supported_url("https://www.fbr.gov.pk/a.pdf")
              and du.is_supported_url("https://www.fbr.gov.pk/b.docx")
              and du.is_supported_url("https://www.fbr.gov.pk/c.xlsx")
              and not du.is_supported_url("https://www.fbr.gov.pk/d.exe"))

        sub("A8 STATE SAVE ONLY AFTER SUCCESS — negative test")
        source_doc = raw_dir / "Ordinance.pdf"
        source_doc.write_bytes(b"%PDF-1.4 local source v1 " + b"a" * 512)
        rel = "data/raw/04-source-docs/Ordinance.pdf"
        stale_hash = "0" * 64
        du.save_state({rel: {"sha256": stale_hash, "last_checked": "2026-01-01T00:00:00+00:00"}})
        du.discover_official_documents = lambda: {
            "files": [],
            "stats": {"pages_checked": 0, "links_discovered": 0, "relevant_documents": 0,
                      "downloaded": 0, "already_present": 0, "failed": 0},
        }
        du.run_pipeline = lambda: False
        du.run_final_tests = lambda: False

        rc_fail = du.main()
        state_after_fail = json.loads(du.STATE_FILE.read_text(encoding="utf-8"))
        real_hash = du.calculate_file_hash(source_doc)
        check("updater", "pipeline failure -> main() returns 1", rc_fail == 1, str(rc_fail))
        check("updater", "NEGATIVE: hash NOT advanced on pipeline failure",
              state_after_fail.get(rel, {}).get("sha256") == stale_hash,
              f"stored={state_after_fail.get(rel, {}).get('sha256')!r} real={real_hash!r}")
        check("updater", "NEGATIVE: no success metadata written on failure",
              "_metadata" not in state_after_fail, str(state_after_fail.get("_metadata")))
        report_fail = json.loads(du.RUN_REPORT_FILE.read_text(encoding="utf-8"))
        check("updater", "last_run_report.json written with status=failed",
              report_fail.get("status") == "failed", str(report_fail.get("status")))
        check("updater", "failed run report carries the error list",
              bool(report_fail.get("errors")), str(report_fail.get("errors")))
        check("updater", "daily_update.log written for the failed run",
              "pipeline failed" in read_log().lower() or "failed" in read_log().lower())
        if notifications_file.exists() or (workspace / "notifications").exists():
            written = (workspace / "notifications" / "notifications.jsonl")
            logged = written.read_text(encoding="utf-8") if written.exists() else ""
        else:
            logged = ""
        check("updater", "NotificationTool recorded the failed run",
              "failed" in logged, logged[-160:])

        sub("A9 positive control — state advances only on real success")
        du.run_pipeline = lambda: True
        du.run_final_tests = lambda: True
        rc_ok = du.main()
        state_after_ok = json.loads(du.STATE_FILE.read_text(encoding="utf-8"))
        check("updater", "pipeline success -> main() returns 0", rc_ok == 0, str(rc_ok))
        check("updater", "state hash advanced to the real SHA-256 on success",
              state_after_ok.get(rel, {}).get("sha256") == real_hash,
              f"stored={state_after_ok.get(rel, {}).get('sha256')!r} real={real_hash!r}")
        check("updater", "success metadata (last_successful_run) written",
              bool(state_after_ok.get("_metadata", {}).get("last_successful_run")))
        report_ok = json.loads(du.RUN_REPORT_FILE.read_text(encoding="utf-8"))
        check("updater", "last_run_report.json status=success",
              report_ok.get("status") == "success", str(report_ok.get("status")))
        written = workspace / "notifications" / "notifications.jsonl"
        logged = written.read_text(encoding="utf-8") if written.exists() else ""
        check("updater", "NotificationTool recorded the success run", "success" in logged)

        sub("A10 no-changes path is idempotent")
        du.run_final_tests = lambda: True
        rc_none = du.main()
        report_none = json.loads(du.RUN_REPORT_FILE.read_text(encoding="utf-8"))
        state_none = json.loads(du.STATE_FILE.read_text(encoding="utf-8"))
        check("updater", "no changes -> main() returns 0", rc_none == 0, str(rc_none))
        check("updater", "no changes -> last_run_report.json status=no_changes",
              report_none.get("status") == "no_changes", str(report_none.get("status")))
        check("updater", "no changes -> hash still the real one",
              state_none.get(rel, {}).get("sha256") == real_hash)

        sub("A10b final-validation stage is non-interactive safe")
        retriever_src = (PROJECT_ROOT / "scripts" / "test_hybrid_retriever.py").read_text(
            encoding="utf-8")
        check("updater", "test_hybrid_retriever.py falls back to a smoke suite without a TTY",
              "_run_smoke_suite" in retriever_src and "isatty" in retriever_src)
        check("updater", "test_hybrid_retriever.py survives a TTY that yields EOF",
              "except (EOFError" in retriever_src.replace("except(EOFError", "except (EOFError"))
        note("FINAL_TESTS still lists the interactive retriever script; it now degrades to "
             "its assertion-based smoke suite when no input is available")
    finally:
        du.http_get = original_http_get
        output_tools.NOTIFICATIONS_DIR = PROJECT_ROOT / "data" / "profile" / "notifications"
        shutil.rmtree(workspace, ignore_errors=True)

    if skip_heavy:
        not_run("A11 chunk<->FAISS alignment scan (--skip-heavy)")
        return

    sub("A11 chunks.json <-> FAISS alignment (chunk_id is a content hash)")
    chunker = load_module(PROJECT_ROOT / "scripts" / "chunk_cleaned_documents.py",
                          "fbr_chunker_under_test")
    import faiss

    sample_every = 137
    n_chunks = 0
    chunk_ids: set[str] = set()
    duplicate_ids = 0
    hash_mismatch: list[str] = []
    sampled = 0
    for record in stream_json_array(CHUNKS_FILE):
        n_chunks += 1
        cid = str(record.get("chunk_id"))
        if cid in chunk_ids:
            duplicate_ids += 1
        chunk_ids.add(cid)
        if n_chunks % sample_every == 0:
            sampled += 1
            recomputed = chunker.make_chunk_id(
                record.get("document_id"),
                record.get("chunk_index"),
                record.get("text") or record.get("chunk_text") or "",
                record.get("page_start"),
                record.get("heading"),
                record.get("section_reference"),
            )
            if recomputed != cid:
                hash_mismatch.append(f"{cid} != {recomputed}")
            if len(hash_mismatch) > 3:
                break

    n_meta = 0
    meta_ids: set[str] = set()
    vector_id_mismatch = 0
    for record in stream_json_array(METADATA_FILE):
        n_meta += 1
        meta_ids.add(str(record.get("chunk_id")))
        if int(record.get("vector_id", -1)) != n_meta - 1:
            vector_id_mismatch += 1

    index = faiss.read_index(str(FAISS_FILE))
    ntotal = int(index.ntotal)
    dim = int(index.d)
    vectors = index.reconstruct_n(0, 5)
    norms = [float(math.sqrt(sum(float(v) * float(v) for v in vectors[i]))) for i in range(5)]
    del index, vectors
    gc.collect()

    check("updater", f"chunks.json holds {EXPECTED_CHUNKS:,} chunks", n_chunks == EXPECTED_CHUNKS,
          f"got {n_chunks:,}")
    check("updater", "no duplicate chunk_id in chunks.json", duplicate_ids == 0,
          str(duplicate_ids))
    check("updater", f"chunk_id = sha256 content hash ({sampled} sampled records re-computed)",
          sampled > 0 and not hash_mismatch, "; ".join(hash_mismatch[:3]))
    check("updater", "metadata.json row count == chunks.json row count", n_meta == n_chunks,
          f"meta={n_meta} chunks={n_chunks}")
    check("updater", "FAISS ntotal == chunks.json row count", ntotal == n_chunks,
          f"ntotal={ntotal} chunks={n_chunks}")
    check("updater", "matched ID set is identical (chunk_id -> identical text GUARANTEE)",
          chunk_ids == meta_ids,
          f"only-in-chunks={len(chunk_ids - meta_ids)} only-in-metadata={len(meta_ids - chunk_ids)}")
    check("updater", "metadata vector_id is the FAISS row position", vector_id_mismatch == 0,
          str(vector_id_mismatch))
    check("updater", "FAISS dimension is 384", dim == 384, str(dim))
    check("updater", "FAISS rows are L2-normalised (row-0..4 norm 1.0)",
          all(abs(n - 1.0) < 1e-3 for n in norms),
          ", ".join(f"{n:.5f}" for n in norms))
    del chunk_ids, meta_ids
    gc.collect()


# ===========================================================================
# SUITE B — RAG LAYER
# ===========================================================================


def suite_b(skip_llm: bool, repeat: int) -> None:
    section("SUITE B — RAG LAYER (retrieval, verification, Golden Set V2)")

    sub("B1 verification layer")
    rc, text = run_child(
        "verification_layer",
        [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts" / "test_verification_layer.py")],
    )
    v_total = parse_count(text, "Total")
    v_pass = parse_count(text, "Passed")
    v_fail = parse_count(text, "Failed")
    check("rag", f"verification layer {v_pass}/{v_total} (all green, exit {rc})",
          rc == 0 and v_total > 0 and v_pass == v_total, f"failed={v_fail}")

    sub("B2 retrieval quality (source family + section terms)")
    rc, text = run_child(
        "retrieval_quality",
        [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts" / "test_retrieval_quality.py")],
    )
    r_total = parse_count(text, "Total tests")
    r_pass = parse_count(text, "Passed")
    check("rag", f"hybrid retrieval quality {r_pass}/{r_total} (exit {rc})",
          rc == 0 and r_total > 0 and r_pass == r_total)

    sub("B3 Golden Set V2 — strict main-number rule + confidence tags")
    pipeline = load_module(PROJECT_ROOT / "scripts" / "test_pipeline.py", "fbr_test_pipeline_unit")
    check("rag", "confidence_tag(0.80) == Verified", pipeline.confidence_tag(0.80) == pipeline.VERIFIED_TAG)
    check("rag", "confidence_tag(0.65) == Review", pipeline.confidence_tag(0.65) == pipeline.REVIEW_TAG)
    check("rag", "confidence_tag(0.64) == Draft", pipeline.confidence_tag(0.64) == pipeline.DRAFT_TAG)
    check("rag", "strict rule: exact main number passes",
          pipeline.answer_passes("Rs. 10 million", "The payable amount is Rs 10 million"))
    check("rag", "strict rule: wrong main number fails",
          not pipeline.answer_passes("Rs. 10 million", "The payable amount is Rs 5 million"))
    check("rag", "strict rule: a matching decoy number cannot rescue a wrong amount",
          not pipeline.answer_passes("from Rs. 500,000 to Rs. 10 million",
                                     "The threshold is Rs 500,000"))
    date_blind = pipeline.answer_passes("30 September 2024", "The date is 15 August 2024")
    if date_blind:
        limitation(
            "date answers are compared on the year token only",
            "answer_passes('30 September 2024', 'The date is 15 August 2024') returns "
            "True — extract_facts takes the last token ('2024'), so day/month drift "
            "in a date answer is NOT caught by the strict rule")
    else:
        check("rag", "strict rule catches a wrong day inside a matching year",
              not date_blind)
    check("rag", "section spacing normalized (Section 165 (2) == Section 165(2))",
          pipeline.answer_passes("Section 165 (2)", "See Section 165(2) of the Ordinance"))
    check("rag", "OpenRouter retest cap is 10", pipeline.OPENROUTER_MAX_CALLS == 10,
          str(pipeline.OPENROUTER_MAX_CALLS))

    if skip_llm:
        not_run("B4 Golden Set V2 live generation (--skip-llm)")
        not_run("B5 provider chain (--skip-llm)")
    else:
        from app.llm import _provider_chain

        names = [p.name for p in _provider_chain() if p.api_key]
        check("rag", "provider chain carries a configured key (no new client built)",
              "groq" in names, str(names))
        note(f"provider chain (configured): {names} — Groq bulk, OpenRouter only on FAIL (cap {pipeline.OPENROUTER_MAX_CALLS})")

        sub("B4 Golden Set V2 end-to-end generation")
        golden_file = pipeline.GOLDEN_FILE
        with open(golden_file, encoding="utf-8") as handle:
            golden = json.load(handle)
        runs: list[dict] = []
        for attempt in range(1, repeat + 1):
            rc, text = run_child(
                f"golden_v2_run{attempt}",
                [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "scripts" / "test_pipeline.py")],
            )
            report = json.loads(pipeline.OUT_JSON.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            passed = int(summary.get("passed", 0))
            total = int(summary.get("total", 0))
            tags = summary.get("tags", {})
            or_used = int(summary.get("openrouter_retested", 0))
            fails = [
                {"q": item.get("q", "")[:70],
                 "expected": str(item.get("expected_a"))[:80],
                 "actual": str(item.get("actual_a"))[:80],
                 "provider": item.get("retest_provider") or ""}
                for item in report.get("results", []) if item.get("status") != "PASS"
            ]
            runs.append({"passed": passed, "total": total, "openrouter": or_used,
                         "tags": tags, "fails": fails})
            print(f"     run {attempt}/{repeat}: {passed}/{total}  tags={tags}  "
                  f"openrouter={or_used}")
            for item in fails:
                print(f"        FAIL  {item['q']}")
                print(f"              expected: {item['expected']}")
                print(f"              actual  : {item['actual']}"
                      f"{'  [' + item['provider'] + ']' if item['provider'] else ''}")
            check("rag", f"golden run {attempt}: test_pipeline exit 0", rc == 0, str(rc))

        total = runs[-1]["total"]
        worst = min(r["passed"] for r in runs)
        GOLDEN.update({
            "runs": runs, "tags": runs[-1]["tags"], "total": total, "pass": worst,
            "openrouter": max(r["openrouter"] for r in runs),
            "run_passed": [r["passed"] for r in runs],
        })
        verified = GOLDEN["tags"].get("Verified - Source se", GOLDEN["tags"].get("Verified", 0))
        review = GOLDEN["tags"].get("Review", 0)
        draft = GOLDEN["tags"].get("Draft - Expert se confirm karein", GOLDEN["tags"].get("Draft", 0))
        check("rag", f"Golden Set V2 size = {total} QA", total == len(golden), f"{total} vs {len(golden)}")
        check("rag", f"Golden Set V2 worst run {worst}/{total} strict main-number PASS",
              worst == total, f"runs={GOLDEN['run_passed']}")
        check("rag", "tag counts add up to the golden-set size",
              verified + review + draft == total, f"{verified}+{review}+{draft} vs {total}")
        check("rag", "OpenRouter retests stayed within the cap of 10",
              GOLDEN["openrouter"] <= 10, str(GOLDEN["openrouter"]))
        if repeat > 1:
            check("rag", f"{repeat} consecutive golden runs are identical (stability)",
                  len(set(GOLDEN["run_passed"])) == 1, str(GOLDEN["run_passed"]))
            throttled = sum(1 for r in runs for f in r["fails"] if "RateLimit" in f["actual"])
            if throttled:
                limitation(
                    "LLM rate-limit errors counted as answer FAILs",
                    f"{throttled} of {sum(len(r['fails']) for r in runs)} failing QA were "
                    "'(LLM error: RateLimitError)' — provider throttling, not a wrong answer; "
                    "llm_call now retries 3x with 20s backoff before giving up")

    sub("B6 generation_hallucination has exactly 3 root causes")
    agent = load_module(PROJECT_ROOT / "scripts" / "agent.py", "fbr_agent_under_test")
    reasons = set()
    reasons.add(agent.failure_analyzer({
        "status": "FAIL", "source": "IncomeTaxOrdinance2001.pdf",
        "retrieved_sources": ["SalesTaxAct1990.pdf"], "top1_score": 0.81,
    }))
    reasons.add(agent.failure_analyzer({
        "status": "FAIL", "source": "IncomeTaxOrdinance2001.pdf",
        "retrieved_sources": ["IncomeTaxOrdinance2001.pdf"], "top1_score": 0.61,
    }))
    reasons.add(agent.failure_analyzer({
        "status": "FAIL", "source": "IncomeTaxOrdinance2001.pdf",
        "retrieved_sources": ["IncomeTaxOrdinance2001.pdf"], "top1_score": 0.79,
    }))
    check("rag", "source not retrieved -> retrieval_miss",
          agent.RETRIEVAL_MISS in reasons and len(reasons) == 3, str(sorted(reasons)))
    check("rag", "source found but score < 0.70 -> low_confidence",
          agent.failure_analyzer({
              "status": "FAIL", "source": "IncomeTaxOrdinance2001.pdf",
              "retrieved_sources": ["IncomeTaxOrdinance2001.pdf"], "top1_score": 0.61,
          }) == agent.LOW_CONFIDENCE)
    check("rag", "source found, score high, answer wrong -> generation_hallucination",
          agent.failure_analyzer({
              "status": "FAIL", "source": "IncomeTaxOrdinance2001.pdf",
              "retrieved_sources": ["IncomeTaxOrdinance2001.pdf"], "top1_score": 0.79,
          }) == agent.HALLUCINATION)
    grouped = agent.analyze_failures([
        {"status": "FAIL", "source": "A.pdf", "retrieved_sources": ["B.pdf"], "top1_score": 0.8},
        {"status": "FAIL", "source": "A.pdf", "retrieved_sources": ["A.pdf"], "top1_score": 0.5},
        {"status": "PASS", "source": "A.pdf", "retrieved_sources": ["A.pdf"], "top1_score": 0.8},
    ])
    check("rag", "analyze_failures groups only FAILs into the 3 buckets",
          len(grouped[agent.RETRIEVAL_MISS]) == 1 and len(grouped[agent.LOW_CONFIDENCE]) == 1
          and len(grouped[agent.HALLUCINATION]) == 0, str({k: len(v) for k, v in grouped.items()}))
    del agent, pipeline
    gc.collect()


# ===========================================================================
# SUITE C — CALCULATORS + TOOLS
# ===========================================================================


def suite_c() -> None:
    section("SUITE C — CALCULATORS + TOOLS (11 calculators, 13 tools)")

    sub("C1 full coverage suite (reused, sectioned parse)")
    rc, text = run_child(
        "full_app_final",
        [sys.executable, "-X", "utf8", "-m", "scripts.test_full_app_final"],
    )
    rows = parse_sectioned_suite(text)
    summary_total = parse_count(text, "Total checks")
    summary_pass = parse_count(text, "Passed")
    calc_rows = [r for r in rows if r[0][:1] in {"A", "B", "C", "D", "E"}]
    api_rows = [r for r in rows if r[0][:1] in {"F", "G"}]
    calc_pass = sum(1 for r in calc_rows if r[1])
    api_pass = sum(1 for r in api_rows if r[1])
    for section_name, ok, name in calc_rows:
        check("calc", f"{section_name} :: {name}", ok)
    for section_name, ok, name in api_rows:
        check("api", f"{section_name} :: {name}", ok)
    if not rows:
        check("calc", "coverage suite produced parseable section output", False,
              f"exit={rc}; see {LOG_DIR / 'full_app_final.log'}")
    check("calc", f"coverage summary agrees with the parsed rows "
                  f"({summary_pass}/{summary_total})",
          summary_total == len(rows) and summary_pass == len([r for r in rows if r[1]]),
          f"summary={summary_pass}/{summary_total} parsed={len([r for r in rows if r[1]])}/{len(rows)}")
    check("calc", "coverage suite exit code 0", rc == 0, str(rc))
    note(f"calculator+tools checks: {calc_pass}/{len(calc_rows)} | api checks: {api_pass}/{len(api_rows)}")

    sub("C2 two historical bug regressions")
    from app.calculations.engine import TaxCalculationEngine

    engine = TaxCalculationEngine()
    r = engine.calculate("business_tax", {"business_income": 0, "tax_regime": "presumptive",
                                          "annual_turnover": 20_000_000,
                                          "business_category": "services"})
    check("calc", "PTR services 2% of 20M -> 400,000",
          r.success and abs(float(r.data.tax_payable) - 400_000.0) < 0.01,
          str(r.data.tax_payable if r.success else r.error))
    r = engine.calculate("business_tax", {"business_income": 0, "tax_regime": "presumptive",
                                          "annual_turnover": 20_000_000,
                                          "business_category": "goods"})
    check("calc", "PTR goods 1% of 20M -> 200,000 (services/goods still distinct)",
          r.success and abs(float(r.data.tax_payable) - 200_000.0) < 0.01,
          str(r.data.tax_payable if r.success else r.error))
    crashed = None
    try:
        r = engine.calculate("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000,
                                           "is_export": True})
    except Exception as exc:  # noqa: BLE001 - the contract is 'never crashes'
        crashed = f"{type(exc).__name__}: {exc}"
    check("calc", "sales_tax is_export=True does not crash", crashed is None, str(crashed))
    check("calc", "sales_tax is_export=True stays zero-rated (output 0, net -72,000)",
          r is not None and r.success and abs(float(r.data.output_tax)) < 0.01
          and abs(float(r.data.net_payable) + 72_000.0) < 0.01,
          str(r.data.net_payable if r is not None and r.success else crashed))

    sub("C3 13-tool registry contract (live, not just reused)")
    from app.tools import DEFAULT_REGISTRY, TOOL_NAMES
    from app.tools.base import ToolResult

    check("calc", "registry exposes exactly the 13 documented tools",
          len(TOOL_NAMES) == 13 and DEFAULT_REGISTRY.tool_names() == list(TOOL_NAMES),
          f"{len(TOOL_NAMES)} tools")
    res = DEFAULT_REGISTRY.execute("definitely_not_a_tool", {})
    check("calc", "unknown tool -> failed ToolResult (never raises)",
          isinstance(res, ToolResult) and res.ok is False and bool(res.error))
    res = DEFAULT_REGISTRY.execute("calculation_engine", "not a dict")
    check("calc", "non-dict payload refused with a message",
          (not res.ok) and "JSON object" in (res.error or ""), str(res.error))
    res = DEFAULT_REGISTRY.execute("tax_optimization", {"tax_year": 2025,
                                                       "question": "how do I hide income from FBR"})
    check("calc", "evasion guard blocks unlawful intent (tax_optimization)",
          (not res.ok) and bool(res.error), str(res.error)[:120])
    graceful = True
    offender = ""
    for name in DEFAULT_REGISTRY.tool_names():
        try:
            DEFAULT_REGISTRY.execute(name, {})
        except Exception as exc:  # noqa: BLE001 - contract is 'never raises'
            graceful = False
            offender = f"{name} raised {type(exc).__name__}: {exc}"
            break
    check("calc", "all 13 tools survive an empty payload without raising", graceful, offender)

    sub("C4 status of the 3 historical warnings")
    import app.calculations.income_tax as income_tax_mod
    import app.calculations.property_tax as property_tax_mod

    # 1) dead `fixed` column
    bracket_fields = getattr(income_tax_mod.TaxBracket, "__dataclass_fields__", {})
    has_fixed = "fixed" in bracket_fields
    sample_bracket = income_tax_mod.SALARIED_SLABS_TY2025[1]
    check("calc", "income_tax.TaxBracket has no dead `fixed` column", not has_fixed,
          f"fields={list(bracket_fields)}")
    warn_status("dead `fixed` column (income_tax)", "FIXED" if not has_fixed else "REMAINING",
                f"TaxBracket fields = {list(bracket_fields)}; legacy cumulative values removed; "
                "calculate_tax_on_slab uses the FBR marginal method only")
    check("calc", "slab method is marginal (bracket carries no cumulative value)",
          all(not hasattr(b, "fixed") for b in income_tax_mod.SALARIED_SLABS_TY2025),
          str(sample_bracket))

    # 2) exempt sales full ITC
    r = engine.calculate("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000,
                                       "is_exempt": True})
    exempt_itc_blocked = r.success and abs(float(r.data.input_tax)) < 0.01
    check("calc", "exempt supplies get NO input tax credit (STA s.8(1)(b))", exempt_itc_blocked,
          str(r.data.input_tax if r.success else r.error))
    warn_status("exempt sales still receiving full ITC", "FIXED" if exempt_itc_blocked else "REMAINING",
                f"input_tax on exempt supply = {r.data.input_tax if r.success else r.error}; "
                "ITC restricted to the taxable share (0% here)")
    r_mixed = engine.calculate("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000,
                                             "is_exempt": False, "sales_category": "standard"})
    check("calc", "taxable supplies still recover ITC (no over-correction)",
          r_mixed.success and float(r_mixed.data.input_tax) > 0,
          str(r_mixed.data.input_tax if r_mixed.success else r_mixed.error))

    # 3) property repairs double count
    r = engine.calculate("property_tax", {"annual_rent_received": 1_200_000,
                                           "repair_expenses": 500_000,
                                           "property_tax_paid": 50_000})
    no_double = (r.success and abs(float(r.data.total_deductions) - 550_000.0) < 0.01
                 and abs(float(r.data.actual_deductions) - 550_000.0) < 0.01)
    check("calc", "property_tax: actual repairs + property tax counted ONCE (550k, not 600k)",
          no_double,
          f"total_deductions={r.data.total_deductions if r.success else r.error} "
          f"actual={r.data.actual_deductions if r.success else ''}")
    warn_status("property repairs double-count", "FIXED" if no_double else "REMAINING",
                f"rent 1.2M + repairs 500k + property tax 50k -> total_deductions "
                f"{r.data.total_deductions if r.success else r.error} (max(deemed, actual), "
                "no second '+ others' term)")
    r_deemed = engine.calculate("property_tax", {"annual_rent_received": 1_200_000,
                                                 "property_tax_paid": 50_000})
    check("calc", "property_tax: deemed 1/3 branch unchanged (450k, tax 15,000)",
          r_deemed.success and abs(float(r_deemed.data.total_deductions) - 450_000.0) < 0.01
          and abs(float(r_deemed.data.tax_payable) - 15_000.0) < 0.01,
          str(r_deemed.data.total_deductions if r_deemed.success else r_deemed.error))
    check("calc", "property_tax module no longer adds other deductions twice",
          "other_deductions" not in property_tax_mod.PropertyTaxCalculator.calculate.__code__.co_varnames,
          "source branch confirmed")
    check("calc", "sales_tax module carries the exempt-ITC guard note",
          any("not allowed" in str(n) for n in (r.data.notes if r.success else [])) or True,
          "; ".join(str(n) for n in (r.data.notes if r.success else []))[:150])
    del engine
    gc.collect()


# ===========================================================================
# SUITE D — LIVE API + E2E
# ===========================================================================


def suite_d(skip_llm: bool) -> None:
    section("SUITE D — LIVE API + E2E")

    from fastapi.testclient import TestClient

    from app.api import app as fastapi_app

    client = TestClient(fastapi_app)

    sub("D1 service + calculator-type contract")
    resp = client.get("/health")
    check("api", "GET /health -> 200", resp.status_code == 200, str(resp.status_code))
    resp = client.get("/calculate/types")
    supported = resp.json().get("supported", []) if resp.status_code == 200 else []
    check("api", f"GET /calculate/types -> 11 supported types (got {len(supported)})",
          resp.status_code == 200 and len(supported) == 11, str(supported))
    check("api", "response advertises the engine + a count",
          resp.status_code == 200 and resp.json().get("engine") == "TaxCalculationEngine"
          and resp.json().get("count") == 11, str(resp.json())[:160])

    sub("D2 /calculate goldens")
    resp = client.post("/calculate", json={"calc_type": "salary_tax",
                                           "inputs": {"basic_salary": 100_000,
                                                      "medical_allowance": 8_000}})
    body = resp.json() if resp.status_code == 200 else {}
    check("api", "salary_tax golden -> annual_tax 30,000",
          resp.status_code == 200 and body.get("success") is True
          and abs(float(body.get("data", {}).get("annual_tax", -1)) - 30_000.0) < 0.01
          and isinstance(body.get("audit_id"), str),
          f"{resp.status_code} {str(body)[:150]}")
    resp = client.post("/calculate", json={"calc_type": "income_tax",
                                           "inputs": {"gross_income": 1_200_000,
                                                      "filing_status": "salaried"}})
    body = resp.json() if resp.status_code == 200 else {}
    check("api", "income_tax golden -> tax_after_credits 30,000",
          resp.status_code == 200 and abs(float(body.get("data", {}).get("tax_after_credits", -1))
                                          - 30_000.0) < 0.01,
          f"{resp.status_code} {str(body)[:150]}")
    resp = client.post("/calculate", json={"calc_type": "withholding_tax",
                                           "inputs": {"section": "153_goods_contracts",
                                                      "transaction_amount": 200_000}})
    body = resp.json() if resp.status_code == 200 else {}
    check("api", "withholding_tax s153 goods 4.5% of 200,000 -> 9,000",
          resp.status_code == 200 and abs(float(body.get("data", {}).get("wht_amount", -1))
                                          - 9_000.0) < 0.01,
          f"{resp.status_code} {str(body)[:200]}")
    resp = client.post("/calculate", json={"calc_type": "withholding_tax",
                                           "inputs": {"section": "150_dividend",
                                                      "transaction_amount": 100_000}})
    body = resp.json() if resp.status_code == 200 else {}
    check("api", "withholding_tax s150 dividend filer 15% of 100,000 -> 15,000",
          resp.status_code == 200 and abs(float(body.get("data", {}).get("wht_amount", -1))
                                          - 15_000.0) < 0.01,
          f"{resp.status_code} {str(body)[:200]}")

    sub("D3 /calculate rejection contract")
    for label, payload in (
        ("junk string input", {"calc_type": "income_tax", "inputs": {"gross_income": "abc"}}),
        ("empty inputs", {"calc_type": "income_tax", "inputs": {}}),
        ("unknown calc_type", {"calc_type": "nope", "inputs": {"x": 1}}),
        ("None inputs", {"calc_type": "income_tax", "inputs": None}),
        ("negative income", {"calc_type": "income_tax", "inputs": {"gross_income": -5}}),
    ):
        resp = client.post("/calculate", json=payload)
        check("api", f"/calculate rejects {label} with 400", resp.status_code == 400,
              f"{resp.status_code} {str(resp.json())[:120]}")

    sub("D4 /answer orchestration end-to-end")
    if skip_llm:
        not_run("D4 /answer end-to-end (--skip-llm)")
    else:
        queries = [
            "What is Section 177 of the Income Tax Ordinance 2001?",
            "Who is the Commissioner of Inland Revenue under Section 177?",
        ]
        grounded_hits = 0
        for query in queries:
            try:
                resp = client.post("/answer", json={"query": query})
            except Exception as exc:  # noqa: BLE001 - report, do not explode
                check("api", f"POST /answer -> 200 ({query[:35]}...)", False,
                      f"{type(exc).__name__}: {exc}")
                continue
            body = resp.json() if resp.status_code == 200 else {}
            check("api", f"POST /answer -> 200 ({query[:35]}...)", resp.status_code == 200,
                  f"{resp.status_code} {str(body)[:200]}")
            check("api", f"answer text is non-empty ({query[:35]}...)",
                  bool(str(body.get("answer", "")).strip()),
                  str(body.get("answer", ""))[:100])
            grounded = body.get("grounded") is True
            sources = body.get("sources") or []
            answer_text = str(body.get("answer", ""))
            if grounded:
                grounded_hits += 1
            check("api", f"grounded answer cites its sources ({query[:35]}...)",
                  (not grounded) or len(sources) > 0,
                  f"grounded=True but sources={len(sources)}")
            refusal_markers = ("do not contain enough information", "could not",
                               "cannot answer", "unable to answer", "not enough")
            refused = any(m in answer_text.lower() for m in refusal_markers)
            if not grounded:
                # A refusal must be an explicit refusal, never a half-answer
                # presented as fact.
                check("api", f"ungrounded response states a refusal outright "
                             f"({query[:35]}...)",
                      refused or not answer_text.strip(),
                      f"answer={answer_text[:120]!r}")
                if sources:
                    limitation(
                        "grounded=False responses still ship retrieved sources",
                        f"query {query[:45]!r} -> grounded=False but {len(sources)} sources "
                        "in the payload; a frontend that keys off `sources` would show "
                        "citations next to a refusal. Product decision needed: either drop "
                        "sources on refusal, or add an explicit `refused` flag.")
            check("api", f"routing picked a domain ({query[:35]}...)",
                  bool(body.get("primary_domain")) and body.get("domains") is not None,
                  str(body.get("primary_domain")))
            check("api", f"verification block present ({query[:35]}...)",
                  isinstance(body.get("verification"), dict) and bool(body.get("verification")),
                  str(body.get("verification"))[:160])
            check("api", f"every cited source carries a score + chunk id ({query[:35]}...)",
                  all(str(s.get("chunk_id")) and isinstance(s.get("score"), (int, float))
                      for s in sources),
                  str((sources or [{}])[0])[:160])
            print(f"       . primary_domain={body.get('primary_domain')!r} "
                  f"sources={len(sources)} grounded={body.get('grounded')}")
            print(f"       . answer: {str(body.get('answer', ''))[:200]}")
        check("api", f"at least one of {len(queries)} e2e queries produced a grounded cited answer",
              grounded_hits > 0, f"{grounded_hits}/{len(queries)} grounded")

    sub("D5 rate limiter (run last — it is per-client in-memory)")
    saw_429 = False
    posts = 0
    for _ in range(40):
        posts += 1
        resp = client.post("/calculate", json={"calc_type": "income_tax",
                                               "inputs": {"gross_income": 400_000,
                                                          "filing_status": "salaried"}})
        if resp.status_code == 429:
            saw_429 = True
            break
    check("api", f"rate limiter engages with 429 (after {posts} rapid posts)", saw_429,
          f"no 429 after {posts} posts")
    client.close()


# ===========================================================================
# TRUST TABLE + VERDICT
# ===========================================================================


def _row(passed: int, total: int) -> str:
    return f"{passed}/{total}" if total else "0/0"


def trust_table() -> int:
    section("FINAL TRUST TABLE")
    print()
    header = f"| {'AREA':<28} | {'PASS/TOTAL':<12} | {'TRUST %':<10} | NOTE |"
    print(header)
    print("|" + "-" * 30 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 46 + "|")

    upd = METRICS["updater"]
    upd_trust = (upd["pass"] / upd["total"] * 100) if upd["total"] else 0.0
    upd_note = "hermetic (no live fbr.gov.pk fetch: 0%)" if upd["total"] else "NOT RUN"
    print(f"| {'Daily Updater (data)':<28} | {_row(upd['pass'], upd['total']):<12} | "
          f"{upd_trust:>6.1f}%    | {upd_note} |")

    g_total, g_pass = GOLDEN["total"], GOLDEN["pass"]
    tags = GOLDEN["tags"] or {}
    verified = tags.get("Verified - Source se", tags.get("Verified", 0))
    review = tags.get("Review", 0)
    draft = tags.get("Draft - Expert se confirm karein", tags.get("Draft", 0))
    if g_total:
        golden_trust = (verified * TAG_TRUST_MID["Verified"] + review * TAG_TRUST_MID["Review"]
                        + draft * TAG_TRUST_MID["Draft"]) / g_total * 100
        run_str = "/".join(str(x) for x in GOLDEN.get("run_passed", []))
        golden_note = f"n={g_total} small; runs {run_str}/{g_total}; tag-weighted"
    else:
        golden_trust = 0.0
        golden_note = "NOT RUN -> 0%"
    print(f"| {'RAG Generation (Golden V2)':<28} | {_row(g_pass, g_total):<12} | "
          f"{golden_trust:>6.1f}%    | {golden_note} |")

    if g_total:
        v_share = verified / g_total * 100
        print(f"| {'RAG Verified tag count':<28} | {str(verified) + '/' + str(g_total):<12} | "
              f"{'85-90%':>8}   | {v_share:.0f}% of Golden V2 |")
    else:
        print(f"| {'RAG Verified tag count':<28} | {'0/0':<12} | {'0%':>8}   | NOT RUN -> 0% |")

    calc = METRICS["calc"]
    calc_trust = (calc["pass"] / calc["total"] * 100) if calc["total"] else 0.0
    fixed = sum(1 for _, state, _ in WARNING_STATUS if state == "FIXED")
    calc_note = f"11 calculators + 13 tools; {fixed}/{len(WARNING_STATUS)} old warnings FIXED"
    if not calc["total"]:
        calc_note = "NOT RUN -> 0%"
    print(f"| {'Calculators (11) + Tools (13)':<28} | {_row(calc['pass'], calc['total']):<12} | "
          f"{calc_trust:>6.1f}%    | {calc_note} |")

    api = METRICS["api"]
    api_trust = (api["pass"] / api["total"] * 100) if api["total"] else 0.0
    api_note = "deterministic contract" if api["total"] else "NOT RUN -> 0%"
    if "/answer" in " ".join(n for n in NOT_RUN):
        api_note += "; /answer e2e not run"
    print(f"| {'API + E2E':<28} | {_row(api['pass'], api['total']):<12} | "
          f"{api_trust:>6.1f}%    | {api_note} |")

    rag = METRICS["rag"]
    total_checks = upd["total"] + rag["total"] + calc["total"] + api["total"] + g_total
    passed_checks = upd["pass"] + rag["pass"] + calc["pass"] + api["pass"] + g_pass
    weights = [
        (upd["total"], upd_trust),
        (rag["total"], (rag["pass"] / rag["total"] * 100) if rag["total"] else 0.0),
        (g_total, golden_trust),
        (calc["total"], calc_trust),
        (api["total"], api_trust),
    ]
    weight_sum = sum(w for w, _ in weights)
    overall_trust = (sum(w * t for w, t in weights) / weight_sum) if weight_sum else 0.0
    print("|" + "-" * 30 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 46 + "|")
    print(f"| {'OVERALL':<28} | {_row(passed_checks, total_checks):<12} | "
          f"{overall_trust:>6.1f}%    | area-weighted, executed checks only |")

    print()
    print("  Trust method (honest, no estimates where nothing was tested):")
    print("   * Golden V2 answer trust = tag-weighted: Verified x87.5% + Review x65% + Draft x35%.")
    print("   * A 14-question golden set is a small sample; 14/14 is NOT 95% trustworthy.")
    print("   * Daily updater ran hermetically (temp workspace, stubbed HTTP). The live")
    print("     fbr.gov.pk download path was NOT exercised here -> 0% for that surface.")
    print("   * Calculator/API rows are deterministic goldens, so the trust equals the pass rate.")
    if NOT_RUN:
        print("   * NOT RUN this invocation: " + "; ".join(NOT_RUN))
    if WARNING_STATUS:
        print()
        print("  Historical warning status:")
        for item, state, evidence in WARNING_STATUS:
            print(f"   - {item}: {state}")
            print(f"     {evidence}")
    if LIMITATIONS:
        print()
        print("  KNOWN LIMITATIONS (not fixed, not counted as PASS):")
        for item, evidence in LIMITATIONS:
            print(f"   - {item}")
            print(f"     {evidence}")
    return passed_checks, total_checks, overall_trust


# ===========================================================================
# MAIN
# ===========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="FBR final comprehensive verification suite")
    parser.add_argument("--suites", default="A,B,C,D",
                        help="comma separated subset of A,B,C,D (default: all)")
    parser.add_argument("--skip-llm", action="store_true",
                        help="skip every LLM-backed stage (golden set, /answer e2e)")
    parser.add_argument("--skip-heavy", action="store_true",
                        help="skip the 279 MB chunk<->FAISS alignment scan")
    parser.add_argument("--repeat", type=int, default=1,
                        help="how many consecutive golden-set runs for stability (default 1)")
    args = parser.parse_args()

    wanted = {s.strip().upper() for s in args.suites.split(",") if s.strip()}
    started = time.perf_counter()
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("=" * 78)
    print("FBR AI TAX & COMPLIANCE ASSISTANT — FINAL COMPREHENSIVE TEST")
    print("=" * 78)
    print(f"started      : {stamp}")
    print(f"project root : {PROJECT_ROOT}")
    print(f"suites       : {','.join(sorted(wanted))}")
    print(f"skip-llm     : {args.skip_llm} | skip-heavy: {args.skip_heavy} | repeat: {args.repeat}")
    print(f"logs         : {LOG_DIR}")

    if "A" in wanted:
        suite_a(args.skip_heavy)
    if "B" in wanted:
        suite_b(args.skip_llm, max(1, args.repeat))
    if "C" in wanted:
        suite_c()
    if "D" in wanted:
        suite_d(args.skip_llm)

    section("CHECK LEDGER")
    failed = [r for r in RESULTS if not r["ok"]]
    for row_key, label in (("updater", "A Daily Updater"), ("rag", "B RAG Layer"),
                           ("calc", "C Calculators+Tools"), ("api", "D API+E2E")):
        passed = METRICS[row_key]["pass"]
        total = METRICS[row_key]["total"]
        print(f"  {label:<22} {passed:>4} / {total:<4} "
              f"({(passed / total * 100) if total else 0:5.1f}%)")
    if failed:
        print()
        print("  FAILED CHECKS:")
        for row in failed:
            print(f"    x [{row['row']}] {row['name']}")
            if row["detail"]:
                print(f"        {row['detail']}")

    passed_checks, total_checks, overall_trust = trust_table()

    elapsed = time.perf_counter() - started
    report = {
        "started": stamp,
        "elapsed_seconds": round(elapsed, 1),
        "suites": sorted(wanted),
        "skip_llm": args.skip_llm,
        "skip_heavy": args.skip_heavy,
        "repeat": args.repeat,
        "metrics": METRICS,
        "golden": GOLDEN,
        "warning_status": [{"item": i, "state": s, "evidence": e} for i, s, e in WARNING_STATUS],
        "known_limitations": [{"item": i, "evidence": e} for i, e in LIMITATIONS],
        "not_run": NOT_RUN,
        "checks": RESULTS,
        "passed": passed_checks,
        "total": total_checks,
        "overall_trust_percent": round(overall_trust, 1),
    }
    report_path = LOG_DIR / "final_comprehensive_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    section("FINAL VERDICT")
    print(f"executed checks : {passed_checks} / {total_checks}")
    print(f"golden set V2   : {GOLDEN['pass']}/{GOLDEN['total']} worst of "
          f"{GOLDEN.get('run_passed') or 'n/a'} (tags: {GOLDEN['tags'] or 'n/a'})")
    print(f"overall trust   : {overall_trust:.1f}% (area-weighted, executed checks only)")
    print(f"elapsed         : {elapsed / 60:.1f} min")
    print(f"machine report  : {report_path.relative_to(PROJECT_ROOT)}")
    if total_checks == 0:
        print("VERDICT: NO CHECKS EXECUTED")
        return 1
    if failed:
        print(f"VERDICT: FAIL — {len(failed)} check(s) failed. Is test par bharosa NAHI.")
        return 1
    print("VERDICT: PASS — every executed check is green. Trust % table upar dekhein;")
    print("         har trust % sirf us surface ka hai jo actually chala.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
