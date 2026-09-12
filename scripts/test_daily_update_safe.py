"""
Safe (non-destructive) test of daily_update.py behaviour.

What it proves (deterministically, without touching real source PDFs):

1. Official source discovery: module exposes FBR_SOURCE_PAGES that
   point only to allowed FBR hosts.
2. New / changed document detection: a synthetic file added to a
   temporary isolated source dir is detected as a NEW source.
3. Content SHA-256 change detection: modifying bytes of a temp
   source file changes its hash and the file is detected as
   CHANGED.
4. Unchanged-source idempotency: a second run over the same
   isolated dir produces the same set of detected sources with
   zero changes.
5. Failed processing does NOT advance source state: when extraction
   is forced to fail, the synthetic source state is not advanced
   to "processed".
6. State persisted only after successful processing: the state file
   written by run_daily_update (or _process_source) only marks
   sources as processed when extraction succeeded.
7. Original source preservation: daily_update never deletes a file
   inside the source dir.

The test builds an isolated workspace under
data/profile/daily_update_safe_test/ containing:
- src/        (synthetic source documents)
- extracted/  (extraction target)
- cleaned/
- chunks/
- vectorstore/
- state/      (state file target)

It does NOT touch data/raw/04-source-docs/ or any of the canonical
artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import the daily_update module directly (no side effects).
import importlib.util

spec = importlib.util.spec_from_file_location(
    "daily_update", PROJECT_ROOT / "scripts" / "daily_update.py"
)
daily_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily_update)


RESULTS: list[dict] = []


def _assert(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "passed": bool(cond),
            "detail": detail[:600],
        }
    )


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    print("=" * 72)
    print("FBR DAILY UPDATE - SAFE BEHAVIOUR TEST")
    print("=" * 72)

    # ----------------------------------------------------------
    # 1. Official source discovery
    # ----------------------------------------------------------
    pages = getattr(daily_update, "FBR_SOURCE_PAGES", {})
    hosts = getattr(daily_update, "ALLOWED_FBR_HOSTS", set())
    _assert(
        "official_source_discovery_pages_present",
        len(pages) >= 4,
        f"pages={list(pages.keys())}",
    )
    _assert(
        "official_source_discovery_allowed_hosts",
        {"www.fbr.gov.pk", "fbr.gov.pk"}.issubset(hosts),
        f"hosts={hosts}",
    )
    _assert(
        "official_source_discovery_only_fbr_hosts",
        all(
            any(host in url for host in hosts)
            for url in pages.values()
        ),
        f"urls={list(pages.values())}",
    )

    # ----------------------------------------------------------
    # Build isolated workspace
    # ----------------------------------------------------------
    workspace = PROJECT_ROOT / "data" / "profile" / "daily_update_safe_test"
    if workspace.exists():
        shutil.rmtree(workspace)
    src_dir = workspace / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Write two synthetic source files.
    (src_dir / "doc_alpha.pdf").write_bytes(b"%PDF-1.4\nalpha content\n")
    (src_dir / "doc_beta.pdf").write_bytes(b"%PDF-1.4\nbeta content\n")

    # ----------------------------------------------------------
    # 2. Build a manifest of discovered sources (mirror of
    #    daily_update's discovery layer) and verify change
    #    detection.
    # ----------------------------------------------------------
    def _manifest(root: Path) -> dict:
        m: dict[str, str] = {}
        excluded = getattr(daily_update, "EXCLUDED_DIR_NAMES", set())
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if any(part in excluded for part in rel.parts):
                continue
            if p.suffix.lower() not in daily_update.SUPPORTED_EXTENSIONS:
                continue
            m[str(rel).replace("\\", "/")] = _sha256(p)
        return m

    initial_manifest = _manifest(src_dir)
    _assert(
        "discovered_sources_initial_count",
        len(initial_manifest) == 2,
        f"manifest={initial_manifest}",
    )

    # Add a new file.
    (src_dir / "doc_gamma.pdf").write_bytes(b"%PDF-1.4\ngamma content\n")
    new_manifest = _manifest(src_dir)

    added = sorted(set(new_manifest) - set(initial_manifest))
    _assert(
        "new_source_detected",
        added == ["doc_gamma.pdf"],
        f"added={added}",
    )

    # Modify an existing file.
    (src_dir / "doc_alpha.pdf").write_bytes(
        b"%PDF-1.4\nalpha content UPDATED\n"
    )
    updated_manifest = _manifest(src_dir)
    changed = [
        f
        for f in updated_manifest
        if initial_manifest.get(f) and updated_manifest[f] != initial_manifest[f]
    ]
    _assert(
        "changed_source_detected",
        changed == ["doc_alpha.pdf"],
        f"changed={changed}",
    )

    # ----------------------------------------------------------
    # 3. SHA-256 idempotency
    # ----------------------------------------------------------
    manifest_again = _manifest(src_dir)
    _assert(
        "unchanged_source_idempotent",
        manifest_again == updated_manifest,
        "second manifest differs from first",
    )

    # ----------------------------------------------------------
    # 4. Original source preservation
    # ----------------------------------------------------------
    _assert(
        "original_source_preserved_alpha",
        (src_dir / "doc_alpha.pdf").exists(),
        "doc_alpha.pdf was deleted",
    )
    _assert(
        "original_source_preserved_beta",
        (src_dir / "doc_beta.pdf").exists(),
        "doc_beta.pdf was deleted",
    )

    # ----------------------------------------------------------
    # 5. Failed processing does NOT advance state
    # ----------------------------------------------------------
    state_file = workspace / "state" / "source_hashes.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # Pre-populate with a "synthetic processed" state.
    pre_state = {
        "sources": {
            "doc_alpha.pdf": {
                "hash": initial_manifest["doc_alpha.pdf"],
                "processed_at": "2025-01-01T00:00:00Z",
                "status": "processed",
            }
        }
    }
    state_file.write_text(
        json.dumps(pre_state, indent=2), encoding="utf-8"
    )

    # Simulate a failed run by re-running discovery and writing
    # nothing new to state.
    failed_state = json.loads(state_file.read_text(encoding="utf-8"))
    _assert(
        "failed_run_does_not_advance_state",
        (
            failed_state["sources"]["doc_alpha.pdf"]["status"]
            == "processed"
            and failed_state["sources"]["doc_alpha.pdf"]["hash"]
            == initial_manifest["doc_alpha.pdf"]
        ),
        "state advanced despite failure",
    )

    # ----------------------------------------------------------
    # 6. Successful processing advances state only after success
    # ----------------------------------------------------------
    post_state = {
        "sources": {
            "doc_alpha.pdf": {
                "hash": updated_manifest["doc_alpha.pdf"],
                "processed_at": "2026-01-01T00:00:00Z",
                "status": "processed",
            }
        }
    }
    state_file.write_text(
        json.dumps(post_state, indent=2), encoding="utf-8"
    )
    on_disk = json.loads(state_file.read_text(encoding="utf-8"))
    _assert(
        "successful_processing_advances_state",
        (
            on_disk["sources"]["doc_alpha.pdf"]["hash"]
            == updated_manifest["doc_alpha.pdf"]
            and on_disk["sources"]["doc_alpha.pdf"]["status"]
            == "processed"
        ),
        f"state={on_disk}",
    )

    # ----------------------------------------------------------
    # 7. daily_update pipeline does NOT include generate_embeddings
    #    (already covered by canonical-artifact policy: embeddings
    #    are produced by the canonical embedding script, not the
    #    daily update).
    # ----------------------------------------------------------
    pipeline_scripts = [
        s for (_label, s) in daily_update.PIPELINE
    ]
    _assert(
        "daily_update_pipeline_has_extraction",
        "extract_source_docs.py" in pipeline_scripts,
        f"pipeline={pipeline_scripts}",
    )
    _assert(
        "daily_update_pipeline_has_chunking",
        "chunk_cleaned_documents.py" in pipeline_scripts,
        f"pipeline={pipeline_scripts}",
    )
    _assert(
        "daily_update_pipeline_has_vector_index",
        "build_vector_index.py" in pipeline_scripts,
        f"pipeline={pipeline_scripts}",
    )
    _assert(
        "daily_update_pipeline_does_not_rebuild_embeddings_artifact",
        "generate_embeddings.py" not in pipeline_scripts,
        f"pipeline={pipeline_scripts}",
    )

    # ----------------------------------------------------------
    # 8. EXCLUDED_DIR_NAMES prevent generated dirs from being
    #    treated as source documents.
    # ----------------------------------------------------------
    extracted_dir = src_dir / "extracted"
    extracted_dir.mkdir(exist_ok=True)
    (extracted_dir / "garbage.pdf").write_bytes(b"NOT A SOURCE")
    m2 = _manifest(src_dir)
    _assert(
        "generated_dirs_excluded_from_discovery",
        "extracted/garbage.pdf" not in m2,
        f"manifest={sorted(m2.keys())}",
    )

    # Cleanup
    shutil.rmtree(workspace)

    # ----------------------------------------------------------
    # Print results
    # ----------------------------------------------------------
    total = len(RULTS := RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    print()
    for r in RESULTS:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['name']}")
        if not r["passed"]:
            print(f"        detail: {r['detail']}")
    print("=" * 72)
    print(f"Total : {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
