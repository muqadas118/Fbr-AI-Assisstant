"""
FBR daily monitoring tests.

Covers the monitoring additions to the daily update layer:

1. Run report (last_run_report.json): written for every outcome,
   records status, timestamp, affected files (with change types)
   and errors; atomic write leaves no temp files; write failures
   are swallowed.
2. Update notification: recorded through the reusable notification
   tool; notification failures NEVER break the update pipeline.
3. finalize_run writes report + notification together.
4. Every main() exit path calls finalize_run (verified by AST
   source inspection of daily_update.py).
5. Knowledge-base safety invariants remain: pipeline order
   preserved, state advanced only after success.
6. Scheduler-adjacent: the daily update script is locatable
   relative to the project root (no absolute paths).

All tests run against temporary directories — the real state,
knowledge base and source documents are never touched.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location(
    "daily_update_monitoring",
    PROJECT_ROOT / "scripts" / "daily_update.py",
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


def main() -> int:
    print("=" * 72)
    print("FBR DAILY MONITORING TEST")
    print("=" * 72)

    workspace = Path(
        tempfile.mkdtemp(prefix="daily_monitoring_test_")
    )

    try:
        # ------------------------------------------------------
        # 1. Run report content
        # ------------------------------------------------------

        report_path = workspace / "last_run_report.json"

        with mock.patch.object(
            daily_update, "STATE_DIR", workspace
        ), mock.patch.object(
            daily_update, "RUN_REPORT_FILE", report_path
        ):
            changed = [
                (PROJECT_ROOT / "data" / "raw" / "a.pdf", "NEW"),
                (PROJECT_ROOT / "data" / "raw" / "b.pdf", "CHANGED"),
            ]

            report = daily_update.write_run_report(
                "success",
                changed=changed,
                discovery_stats={
                    "relevant_documents": 7,
                    "failed": 2,
                },
            )

        on_disk = json.loads(
            report_path.read_text(encoding="utf-8")
        )

        _assert(
            "run_report_written",
            report_path.is_file(),
            f"path={report_path}",
        )

        _assert(
            "run_report_records_status_and_timestamp",
            on_disk["status"] == "success"
            and "T" in on_disk["timestamp"],
            f"report={on_disk}",
        )

        _assert(
            "run_report_records_documents_and_change_types",
            on_disk["documents_processed_count"] == 2
            and on_disk["documents_processed"][0]["change_type"]
            == "NEW"
            and on_disk["documents_processed"][1]["change_type"]
            == "CHANGED",
            f"docs={on_disk['documents_processed']}",
        )

        _assert(
            "run_report_records_discovery_stats",
            on_disk["official_documents_discovered"] == 7
            and on_disk["official_download_failures"] == 2,
            f"report={on_disk}",
        )

        _assert(
            "run_report_atomic_no_temp_left",
            not list(workspace.glob("*.tmp")),
            f"files={[p.name for p in workspace.iterdir()]}",
        )

        # ------------------------------------------------------
        # 2. Run report records errors (failed status)
        # ------------------------------------------------------

        failed_report_path = workspace / "failed_report.json"

        with mock.patch.object(
            daily_update, "STATE_DIR", workspace
        ), mock.patch.object(
            daily_update, "RUN_REPORT_FILE", failed_report_path
        ):
            failed_report = daily_update.write_run_report(
                "failed",
                errors=["Processing pipeline failed."],
            )

        failed_on_disk = json.loads(
            failed_report_path.read_text(encoding="utf-8")
        )

        _assert(
            "run_report_records_errors",
            failed_on_disk["status"] == "failed"
            and failed_on_disk["errors"]
            == ["Processing pipeline failed."],
            f"report={failed_on_disk}",
        )

        # ------------------------------------------------------
        # 3. Report write failure is swallowed
        # ------------------------------------------------------

        blocker = workspace / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")

        with mock.patch.object(
            daily_update, "STATE_DIR", blocker / "sub"
        ), mock.patch.object(
            daily_update,
            "RUN_REPORT_FILE",
            blocker / "sub" / "last_run_report.json",
        ):
            swallowed = daily_update.write_run_report("no_changes")

        _assert(
            "run_report_write_failure_swallowed",
            isinstance(swallowed, dict)
            and swallowed["status"] == "no_changes",
            "write failure propagated",
        )

        # ------------------------------------------------------
        # 4. Notification recorded via the notification tool
        # ------------------------------------------------------

        notification_calls: list[dict] = []

        class _RecordingNotificationTool:
            def run(self, payload):
                notification_calls.append(dict(payload))
                from app.tools.base import ToolResult

                return ToolResult(
                    tool="notification",
                    ok=True,
                    data={"status": "recorded"},
                )

        with mock.patch(
            "app.tools.output_tools.NotificationTool",
            _RecordingNotificationTool,
        ):
            daily_update.record_update_notification(
                "success",
                {"documents_processed_count": 3, "errors": []},
            )

        _assert(
            "notification_recorded_via_tool",
            len(notification_calls) == 1
            and notification_calls[0]["type"] == "update"
            and "success" in notification_calls[0]["subject"],
            f"calls={notification_calls}",
        )

        _assert(
            "notification_payload_has_no_credentials",
            notification_calls
            and set(notification_calls[0].keys())
            == {"type", "subject", "message", "metadata"},
            f"payload keys={sorted(notification_calls[0].keys())}",
        )

        # ------------------------------------------------------
        # 5. Notification failure never breaks the pipeline
        # ------------------------------------------------------

        class _ExplodingNotificationTool:
            def run(self, payload):
                raise RuntimeError("notification backend down")

        with mock.patch(
            "app.tools.output_tools.NotificationTool",
            _ExplodingNotificationTool,
        ):
            try:
                daily_update.record_update_notification(
                    "success",
                    {"documents_processed_count": 1},
                )
                did_not_raise = True
            except Exception:
                did_not_raise = False

        _assert(
            "notification_failure_does_not_raise",
            did_not_raise,
            "notification failure propagated",
        )

        # ------------------------------------------------------
        # 6. finalize_run writes report + notification
        # ------------------------------------------------------

        finalize_report_calls: list = []
        finalize_notification_calls: list = []

        with mock.patch.object(
            daily_update,
            "write_run_report",
            side_effect=lambda status, **kw: finalize_report_calls.append(
                status
            )
            or {"status": status, "errors": [], "documents_processed_count": 0},
        ), mock.patch.object(
            daily_update,
            "record_update_notification",
            side_effect=lambda status, report: (
                finalize_notification_calls.append((status, report))
            ),
        ):
            daily_update.finalize_run(
                "no_changes",
                discovery_stats={"relevant_documents": 4},
            )

        _assert(
            "finalize_run_writes_report_and_notification",
            finalize_report_calls == ["no_changes"]
            and len(finalize_notification_calls) == 1
            and finalize_notification_calls[0][0] == "no_changes",
            f"reports={finalize_report_calls} notifications={finalize_notification_calls}",
        )

    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    # ----------------------------------------------------------
    # 7. Every main() exit path finalizes the run (AST check)
    # ----------------------------------------------------------

    source_path = (
        PROJECT_ROOT / "scripts" / "daily_update.py"
    )

    tree = ast.parse(
        source_path.read_text(encoding="utf-8")
    )

    main_function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "main"
    )

    finalize_statuses = [
        call.args[0].value
        for call in ast.walk(main_function)
        if isinstance(call, ast.Call)
        and getattr(call.func, "id", "") == "finalize_run"
        and call.args
        and isinstance(call.args[0], ast.Constant)
    ]

    _assert(
        "every_exit_path_finalizes_run",
        sorted(finalize_statuses)
        == [
            "baseline_initialized",
            "failed",
            "failed",
            "failed",
            "no_changes",
            "success",
        ],
        f"statuses={sorted(finalize_statuses)}",
    )

    returns_in_main = sum(
        1
        for node in ast.walk(main_function)
        if isinstance(node, ast.Return)
    )

    _assert(
        "main_exit_paths_covered",
        returns_in_main == len(finalize_statuses),
        f"returns={returns_in_main} finalize calls={len(finalize_statuses)}",
    )

    # ----------------------------------------------------------
    # 8. Knowledge-base safety invariants preserved
    # ----------------------------------------------------------

    pipeline_scripts = [
        script for (_label, script) in daily_update.PIPELINE
    ]

    _assert(
        "pipeline_order_preserved",
        pipeline_scripts
        == [
            "extract_source_docs.py",
            "validate_source_doc_extraction.py",
            "clean_extracted_documents.py",
            "validate_cleaned_documents.py",
            "chunk_cleaned_documents.py",
            "build_vector_index.py",
        ],
        f"pipeline={pipeline_scripts}",
    )

    _assert(
        "state_saved_only_after_success_in_source",
        source_path.read_text(encoding="utf-8").count(
            "was NOT advanced."
        )
        >= 2,
        "failure paths must not advance state",
    )

    # ----------------------------------------------------------
    # 9. Daily update script locatable relative to project root
    # ----------------------------------------------------------

    _assert(
        "daily_update_script_locatable",
        (PROJECT_ROOT / "scripts" / "daily_update.py").is_file()
        and str(daily_update.PROJECT_ROOT) == str(PROJECT_ROOT),
        "daily update script not found relative to project root",
    )

    # ----------------------------------------------------------
    # Print results
    # ----------------------------------------------------------

    total = len(RESULTS)
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
