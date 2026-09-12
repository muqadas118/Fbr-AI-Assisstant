"""
FBR project portability tests.

Verifies the project runs when copied to another directory or
another Windows user's machine:

1. No hardcoded absolute paths in source code (app/ and scripts/)
2. .env.example exists and contains no real secrets
3. requirements.txt is correctly named and complete (including
   the Phase 10 API dependencies)
4. .gitignore protects the real .env file
5. scripts/setup_scheduler.ps1 discovers all paths dynamically
   (project root, Python, daily update script) and registers a
   daily 03:00 task with a working directory
6. Project path resolution is __file__-based (cwd-independent)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS: list[dict] = []


def _assert(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "passed": bool(cond),
            "detail": detail[:600],
        }
    )


# A hardcoded absolute path inside a string literal: a quote
# immediately followed by a drive letter and separator. Docstring
# prose (e.g. "No absolute C:\Users\... paths.") does not match.
_DRIVE_PATH_RE = re.compile(
    r"[\"'][A-Za-z]:[\\/]"
)

_USER_PATH_RE = re.compile(r"[\"']/(Users|home)/")

SOURCE_DIRS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "scripts",
]

IGNORED_SCRIPT_PARTS = {"__pycache__"}


def main() -> int:
    print("=" * 72)
    print("FBR PROJECT PORTABILITY TEST")
    print("=" * 72)

    # ----------------------------------------------------------
    # 1. No hardcoded absolute paths in source
    # ----------------------------------------------------------

    for source_dir in SOURCE_DIRS:
        violations = []

        for file_path in sorted(source_dir.rglob("*.py")):
            if any(
                part in IGNORED_SCRIPT_PARTS
                for part in file_path.parts
            ):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if _DRIVE_PATH_RE.search(content) or _USER_PATH_RE.search(
                content
            ):
                violations.append(
                    file_path.relative_to(PROJECT_ROOT).as_posix()
                )

        _assert(
            f"no_hardcoded_absolute_paths_in_{source_dir.name}",
            not violations,
            f"violations={violations}",
        )

    # ----------------------------------------------------------
    # 2. .env.example exists, documents keys, holds no secrets
    # ----------------------------------------------------------

    env_example = PROJECT_ROOT / ".env.example"

    _assert(
        "env_example_exists",
        env_example.is_file(),
        f"path={env_example}",
    )

    env_content = (
        env_example.read_text(encoding="utf-8")
        if env_example.is_file()
        else ""
    )

    secret_values = [
        line
        for line in env_content.splitlines()
        if re.match(
            r"^(GROQ_API_KEY|OPENROUTER_API_KEY)=\S+",
            line.strip(),
        )
    ]

    _assert(
        "env_example_has_no_real_secrets",
        not secret_values,
        f"secret lines={secret_values}",
    )

    _assert(
        "env_example_documents_required_keys",
        "GROQ_API_KEY=" in env_content
        and "OPENROUTER_API_KEY=" in env_content
        and "GROQ_MODEL=" in env_content
        and "OPENROUTER_MODEL=" in env_content,
        f"content={env_content!r}",
    )

    # ----------------------------------------------------------
    # 3. requirements.txt correctly named and complete
    # ----------------------------------------------------------

    requirements = PROJECT_ROOT / "requirements.txt"

    _assert(
        "requirements_txt_exists",
        requirements.is_file(),
        f"path={requirements}",
    )

    req_content = (
        requirements.read_text(encoding="utf-8")
        if requirements.is_file()
        else ""
    )

    required_packages = [
        "faiss-cpu",
        "sentence-transformers",
        "rank-bm25",
        "openai",
        "python-dotenv",
        "fastapi",
        "uvicorn",
        "httpx",
        "pydantic",
    ]

    missing = [
        package
        for package in required_packages
        if package not in req_content
    ]

    _assert(
        "requirements_txt_complete_including_api_deps",
        not missing,
        f"missing={missing}",
    )

    _assert(
        "requirements_typo_file_removed",
        not (PROJECT_ROOT / "recquirements.txt").exists(),
        "recquirements.txt still exists",
    )

    # ----------------------------------------------------------
    # 4. .gitignore protects secrets
    # ----------------------------------------------------------

    gitignore = PROJECT_ROOT / ".gitignore"

    _assert(
        "gitignore_exists",
        gitignore.is_file(),
        f"path={gitignore}",
    )

    gitignore_content = (
        gitignore.read_text(encoding="utf-8")
        if gitignore.is_file()
        else ""
    )

    _assert(
        "gitignore_protects_env_file",
        ".env" in gitignore_content.split(),
        f"content={gitignore_content!r}",
    )

    # ----------------------------------------------------------
    # 5. Portable scheduler script
    # ----------------------------------------------------------

    scheduler = PROJECT_ROOT / "scripts" / "setup_scheduler.ps1"

    _assert(
        "scheduler_script_exists",
        scheduler.is_file(),
        f"path={scheduler}",
    )

    ps1 = (
        scheduler.read_text(encoding="utf-8")
        if scheduler.is_file()
        else ""
    )

    _assert(
        "scheduler_discovers_project_root_dynamically",
        "$PSScriptRoot" in ps1
        and "Join-Path $PSScriptRoot" in ps1,
        "project root not derived from script location",
    )

    _assert(
        "scheduler_locates_python_dynamically",
        ".venv" in ps1 and "py -3" in ps1 and '"python"' in ps1,
        "python discovery missing fallbacks",
    )

    _assert(
        "scheduler_validates_dependencies",
        "pip install -r requirements.txt" in ps1,
        "dependency validation/instructions missing",
    )

    _assert(
        "scheduler_locates_update_script_dynamically",
        "Join-Path $ProjectRoot" in ps1
        and "daily_update.py" in ps1,
        "daily update script not located dynamically",
    )

    _assert(
        "scheduler_registers_daily_3am_task",
        "Register-ScheduledTask" in ps1
        and "New-ScheduledTaskTrigger" in ps1
        and "-Daily" in ps1
        and '"03:00"' in ps1,
        "daily 03:00 registration missing",
    )

    _assert(
        "scheduler_sets_working_directory",
        "-WorkingDirectory $ProjectRoot" in ps1,
        "working directory not set to project root",
    )

    _assert(
        "scheduler_has_uninstall_switch",
        "$Uninstall" in ps1
        and "Unregister-ScheduledTask" in ps1,
        "uninstall mode missing",
    )

    _assert(
        "scheduler_has_clear_success_failure_output",
        "[SUCCESS]" in ps1 and "[FAILED]" in ps1,
        "success/failure output missing",
    )

    _assert(
        "scheduler_no_machine_specific_paths",
        not re.search(
            r"[A-Za-z]:\\", ps1.replace("`n", " ")
        )
        and ("C:" + "\\Users") not in ps1
        and "D:" + "\\ALL" not in ps1,
        "machine-specific path found in scheduler",
    )

    # ----------------------------------------------------------
    # 6. Path resolution is __file__-based and cwd-independent
    # ----------------------------------------------------------

    from app.tools.search_tools import PROJECT_ROOT as TOOLS_ROOT
    from app.tools.document_tools import (
        PROJECT_ROOT as DOC_TOOLS_ROOT,
    )

    _assert(
        "tools_project_root_resolution_consistent",
        TOOLS_ROOT == DOC_TOOLS_ROOT == PROJECT_ROOT,
        f"roots differ: {TOOLS_ROOT} / {DOC_TOOLS_ROOT}",
    )

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "daily_update_portability",
        PROJECT_ROOT / "scripts" / "daily_update.py",
    )
    daily_update = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(daily_update)

    _assert(
        "daily_update_project_root_file_based",
        daily_update.PROJECT_ROOT == PROJECT_ROOT,
        f"root={daily_update.PROJECT_ROOT}",
    )

    _assert(
        "project_root_structure_valid",
        (PROJECT_ROOT / "app").is_dir()
        and (PROJECT_ROOT / "scripts").is_dir()
        and (PROJECT_ROOT / "data").is_dir(),
        "project root does not contain expected directories",
    )

    from app.hybrid_retriever import FBRHybridRetriever

    import inspect

    init_source = inspect.getsource(
        FBRHybridRetriever.__init__
    )

    _assert(
        "retriever_paths_file_based",
        "parents[1]" in init_source or "parent.parent" in init_source,
        "retriever paths not derived from __file__",
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
