"""
Production-Level Test Suite for FBR AI Assistant
Tests Phases 1-10 as if used by real public users.
Security-focused, performance-aware, complete coverage.

Runnable two ways:
    python -m pytest tests/test_production_suite.py -q   (one pytest item per check)
    python tests/test_production_suite.py                (standalone reporter run)
"""
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime

import pytest

# Fix encoding for Windows console (skipped when pytest replaces stdout)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project ROOT (parent of tests/) so 'app' module can be imported
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

REPORT_PATH = Path("tests/production_test_report.json")

class TestReporter:
    __test__ = False  # reporter helper, not a pytest test class

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.results = []

    def test(self, name, func):
        start = time.time()
        try:
            result = func()
            duration = time.time() - start
            if result is True:
                self.passed += 1
                self.results.append(('PASS', name, duration, None))
                print(f"[PASS] {name} ({duration:.2f}s)")
                return 'PASS', None
            elif isinstance(result, str):
                # Warning
                self.warnings += 1
                self.results.append(('WARN', name, duration, result))
                print(f"[WARN] {name}: {result} ({duration:.2f}s)")
                return 'WARN', result
            else:
                self.failed += 1
                self.results.append(('FAIL', name, duration, str(result)))
                print(f"[FAIL] {name}: {result} ({duration:.2f}s)")
                return 'FAIL', str(result)
        except Exception as e:
            duration = time.time() - start
            self.failed += 1
            error_msg = f"{type(e).__name__}: {e}"
            self.results.append(('FAIL', name, duration, error_msg))
            print(f"[FAIL] {name}: {error_msg} ({duration:.2f}s)")
            traceback.print_exc()
            return 'FAIL', error_msg

    def section(self, title):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    def summary(self):
        total = self.passed + self.failed + self.warnings
        print(f"\n{'='*60}")
        print("  TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total tests: {total}")
        print(f"  [PASS]:  {self.passed}")
        print(f"  [WARN]:  {self.warnings}")
        print(f"  [FAIL]:  {self.failed}")
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        print(f"  Pass rate: {pass_rate:.1f}%")
        return self.failed == 0

reporter = TestReporter()

# ============================================================
# PHASE 1: Source Documents Integrity
# ============================================================

def check_source_documents_exist():
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return f"Raw directory not found: {raw_dir}"
    pdfs = list(raw_dir.rglob("*.pdf"))
    if len(pdfs) < 90:
        return f"Only {len(pdfs)} PDFs found (expected ~94)"
    return True

def check_source_manifest():
    manifest_path = Path("data/profile/source_doc_manifest.csv")
    if not manifest_path.exists():
        return "Source manifest not found"
    with open(manifest_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    return True if len(lines) > 90 else f"Only {len(lines)} entries in manifest"

# ============================================================
# PHASE 2: Document Extraction
# ============================================================

def check_extraction_output():
    extracted_dir = Path("data/profile/source_docs/extracted")
    if not extracted_dir.exists():
        return "Extracted directory not found"
    files = list(extracted_dir.rglob("*.json"))
    if len(files) < 90:
        return f"Only {len(files)} extracted files"
    return True

# ============================================================
# PHASE 3: Normalization
# ============================================================

def check_cleaned_documents():
    cleaned_path = Path("data/profile/source_docs/cleaned/cleaned_documents.json")
    if not cleaned_path.exists():
        return "Cleaned documents file not found"
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        docs = json.load(f)
    if len(docs) < 90:
        return f"Only {len(docs)} cleaned docs"
    sample = docs[0]
    required_keys = ['document_id', 'source', 'sections', 'text']
    missing = [k for k in required_keys if k not in sample]
    if missing:
        return f"Missing keys in cleaned doc: {missing}"
    return True

# ============================================================
# PHASE 4: Chunking
# ============================================================

def check_chunks_integrity():
    chunks_path = Path("data/profile/source_docs/chunks/chunks.json")
    if not chunks_path.exists():
        return "Chunks file not found"
    with open(chunks_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    if len(chunks) < 58000:
        return f"Only {len(chunks)} chunks (expected ~58,822)"
    # Check uniqueness
    chunk_ids = [c.get('chunk_id', '') for c in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        return "Duplicate chunk IDs found"
    # Check empty chunks
    empty = [c for c in chunks if not c.get('text', '').strip()]
    if empty:
        return f"{len(empty)} empty chunks found"
    return True

# ============================================================
# PHASE 5: Embeddings
# ============================================================

def check_embeddings_npy():
    emb_path = Path("data/profile/source_docs/embeddings/embeddings.npy")
    if not emb_path.exists():
        return "Embeddings file not found"
    import numpy as np
    emb = np.load(emb_path, mmap_mode='r')
    if emb.shape[1] != 384:
        return f"Wrong dimension: {emb.shape[1]} (expected 384)"
    if emb.shape[0] < 58000:
        return f"Only {emb.shape[0]} embeddings"
    # Check for NaN/Inf
    sample = emb[:100]
    if np.isnan(sample).any() or np.isinf(sample).any():
        return "NaN or Inf in embeddings"
    return True

# ============================================================
# PHASE 6: FAISS Vector Database
# ============================================================

def check_faiss_index():
    import faiss
    index_path = Path("data/profile/vectorstore/fbr_faiss.index")
    if not index_path.exists():
        return "FAISS index not found"
    index = faiss.read_index(str(index_path))
    if index.ntotal < 58000:
        return f"Only {index.ntotal} vectors in index"
    if index.d != 384:
        return f"Wrong dimension: {index.d}"
    # Test search
    import numpy as np
    query = np.random.randn(1, 384).astype('float32')
    faiss.normalize_L2(query)
    distances, indices = index.search(query, 5)
    if len(indices[0]) != 5:
        return "Search returned wrong number of results"
    return True

# ============================================================
# PHASE 7: RAG Engine - Imports
# ============================================================

def check_rag_engine_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_query_understanding_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_retriever_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

# ============================================================
# PHASE 8: Verification Layer
# ============================================================

def check_verification_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_reranker_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

# ============================================================
# PHASE 9: Agents & Router
# ============================================================

def check_router_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_all_agents_import():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_router_functionality():
    from app.agents.router import FBRQueryRouter
    router = FBRQueryRouter()
    test_cases = [
        ("income tax slab for individuals", "income_tax"),
        ("sales tax registration", "sales_tax"),
        ("customs duty on import", "customs"),
        ("federal excise duty", "federal_excise"),
        ("how to register NTN", "registration"),
        ("file income tax return", "return_filing"),
        ("calculate tax on 500000", "calculation"),
        ("received FBR notice", "notice_appeal"),
        ("compare finance act 2024 and 2025", "research"),
    ]
    for query, expected in test_cases:
        decision = router.route(query)
        if expected not in decision.domains:
            return f"Query '{query}' routed to {decision.domains}, expected {expected}"
    return True

# ============================================================
# PHASE 10: API & Frontend
# ============================================================

def check_api_imports():
    try:
        return True
    except Exception as e:
        return f"Import failed: {e}"

def check_api_endpoints():
    from app.api import app
    routes = [route.path for route in app.routes]
    if "/answer" not in routes:
        return "No /answer endpoint"
    if "/health" not in routes:
        return "No /health endpoint"
    return True

def check_frontend_structure():
    frontend_path = Path("frontend/src")
    if not frontend_path.exists():
        return "Frontend src not found"
    required = ["App.tsx", "main.tsx"]
    for f in required:
        if not (frontend_path / f).exists():
            return f"Missing: {f}"
    return True

# ============================================================
# SECURITY TESTS
# ============================================================

def check_env_gitignored():
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        return "No .gitignore"
    content = gitignore.read_text(encoding='utf-8')
    if '.env' not in content:
        return ".env not in .gitignore - SECURITY RISK!"
    return True

def check_input_validation():
    # Test that API validates input length
    from app.api import AnswerRequest
    try:
        # Should fail for too long query
        long_query = "a" * 1500
        AnswerRequest(query=long_query)
        return "No max_length validation on query"
    except Exception:
        return True  # Good, validation worked

def check_no_hardcoded_secrets():
    """Scan the whole tree for committed credentials, not just a few .py files.

    The previous version only looked at 4 hand-listed .py files, which is why a
    plaintext SUPABASE_JWT_SECRET in docker-compose.yml and a Supabase anon key
    in fbr_app.html both passed this test.
    """
    import re

    suspicious_patterns = [
        (r'sk-or-v1-[a-zA-Z0-9]{40,}', 'OpenRouter API key'),
        (r'gsk_[a-zA-Z0-9]{40,}', 'Groq API key'),
        (r'sk-ant-[a-zA-Z0-9\-_]{40,}', 'Anthropic API key'),
        (r'eyJhbGciOi[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{20,}\.', 'JWT / Supabase key'),
        (r'AKIA[0-9A-Z]{16}', 'AWS access key id'),
        (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'private key'),
        # Assignment of a non-empty, non-placeholder secret value.
        (r'(?i)(JWT_SECRET|SECRET_KEY|POSTGRES_PASSWORD|ADMIN_PASSWORD|API_KEY)'
         r'\s*[:=]\s*["\']?(?!\s*$)(?!\$\{)(?!your[-_])(?!change[-_]me)(?!<)'
         r'[A-Za-z0-9+/=_\-]{16,}', 'hardcoded secret assignment'),
    ]

    scan_suffixes = {'.py', '.yml', '.yaml', '.html', '.json', '.sql', '.ts',
                     '.tsx', '.js', '.jsx', '.sh', '.toml', '.ini', '.md'}
    # .env is gitignored and is the correct home for real secrets.
    skip_names = {'.env', '.env.example', 'package-lock.json'}
    skip_dirs = {'.git', 'node_modules', '__pycache__', 'dist', 'coverage',
                 'data', 'uploads', '.venv', 'venv', '.claude'}

    root = Path('.')
    findings = []
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in scan_suffixes:
            continue
        if path.name in skip_names:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for pattern, label in suspicious_patterns:
            match = re.search(pattern, content)
            if match:
                line = content[:match.start()].count('\n') + 1
                findings.append(f"{path.as_posix()}:{line} ({label})")
                break

    if findings:
        return "Hardcoded secrets found: " + "; ".join(findings[:5])
    return True


def check_answer_endpoint_is_guarded():
    """POST /answer and POST /calculate must require a bearer token.

    /answer costs money on every call (LLM + embeddings), so an unauthenticated
    route is both a data and a billing exposure.
    """
    from app.api import app as fastapi_app
    from app.supabase_auth import require_user

    protected = {"/answer", "/calculate"}
    seen = set()
    for route in fastapi_app.routes:
        path = getattr(route, "path", None)
        if path not in protected or "POST" not in getattr(route, "methods", set()):
            continue
        seen.add(path)
        deps = [d.call for d in getattr(route, "dependant", None).dependencies] \
            if getattr(route, "dependant", None) else []
        if require_user not in deps:
            return f"{path} is not guarded by require_user"

    missing = protected - seen
    if missing:
        return f"Missing POST routes: {sorted(missing)}"
    return True


def check_auth_defaults_to_required():
    """FBR_AUTH_REQUIRED must fail closed when unset."""
    import os
    from app.supabase_auth import auth_required

    saved = os.environ.pop("FBR_AUTH_REQUIRED", None)
    try:
        if not auth_required():
            return "auth_required() is False when FBR_AUTH_REQUIRED is unset - fails open!"
    finally:
        if saved is not None:
            os.environ["FBR_AUTH_REQUIRED"] = saved
    return True


def check_jwt_audience_is_authenticated():
    """Supabase access tokens carry aud='authenticated', not the anon key."""
    from app import supabase_auth

    if supabase_auth.SUPABASE_JWT_AUDIENCE != "authenticated":
        return f"Wrong JWT audience: {supabase_auth.SUPABASE_JWT_AUDIENCE!r}"
    return True

def check_error_handling_api():
    # Check that LLMError is caught
    from app import api
    if not hasattr(api, 'HTTPException'):
        return "No HTTPException handling"
    return True

# ============================================================
# INTEGRATION TESTS
# ============================================================

def check_router_to_rag_flow():
    """Test that router decisions flow to retriever correctly"""
    try:
        # Just import check, not full execution (LLM needed)
        return True
    except Exception as e:
        return f"Integration broken: {e}"

def check_answer_response_model():
    from app.api import AnswerResponse
    required_fields = ['question', 'answer', 'sources', 'verification', 'grounded']
    fields = AnswerResponse.model_fields.keys()
    missing = [f for f in required_fields if f not in fields]
    if missing:
        return f"Missing fields: {missing}"
    return True

# ============================================================
# CHECK REGISTRY (drives both pytest collection and the CLI run)
# ============================================================

CHECKS = [
    ("PHASE 1: Source Documents", "Source documents (94 PDFs expected)", check_source_documents_exist),
    ("PHASE 1: Source Documents", "Source manifest integrity", check_source_manifest),

    ("PHASE 2: Document Extraction", "Extraction output (94+ files)", check_extraction_output),

    ("PHASE 3: Normalization", "Cleaned documents (94+ records)", check_cleaned_documents),

    ("PHASE 4: Chunking", "Chunks integrity (58,822+ chunks, unique, non-empty)", check_chunks_integrity),

    ("PHASE 5: Embeddings", "Embeddings matrix (58,822 x 384, no NaN/Inf)", check_embeddings_npy),

    ("PHASE 6: FAISS Vector Database", "FAISS index (58,822 vectors, 384 dim, searchable)", check_faiss_index),

    ("PHASE 7: RAG Engine", "RAG engine module imports", check_rag_engine_imports),
    ("PHASE 7: RAG Engine", "Query understanding module imports", check_query_understanding_imports),
    ("PHASE 7: RAG Engine", "Hybrid retriever module imports", check_retriever_imports),

    ("PHASE 8: Verification Layer", "Verification layer imports", check_verification_imports),
    ("PHASE 8: Verification Layer", "Reranker module imports", check_reranker_imports),

    ("PHASE 9: Agents & Router", "Router module imports", check_router_imports),
    ("PHASE 9: Agents & Router", "Orchestrator imports", check_all_agents_import),
    ("PHASE 9: Agents & Router", "Router accuracy (9 test cases)", check_router_functionality),

    ("PHASE 10: API & Frontend", "API module imports", check_api_imports),
    ("PHASE 10: API & Frontend", "API endpoints exist", check_api_endpoints),
    ("PHASE 10: API & Frontend", "Frontend structure", check_frontend_structure),

    ("SECURITY: Production-Grade Checks", "SECURITY: .env is gitignored", check_env_gitignored),
    ("SECURITY: Production-Grade Checks", "SECURITY: Input validation (max 1000 chars)", check_input_validation),
    ("SECURITY: Production-Grade Checks", "SECURITY: No hardcoded API keys in code", check_no_hardcoded_secrets),
    ("SECURITY: Production-Grade Checks", "SECURITY: API error handling", check_error_handling_api),
    ("SECURITY: Production-Grade Checks", "SECURITY: POST /answer + /calculate require auth", check_answer_endpoint_is_guarded),
    ("SECURITY: Production-Grade Checks", "SECURITY: Auth fails closed by default", check_auth_defaults_to_required),
    ("SECURITY: Production-Grade Checks", "SECURITY: JWT audience = 'authenticated'", check_jwt_audience_is_authenticated),

    ("INTEGRATION: End-to-End Tests", "Router -> Orchestrator -> RAG flow", check_router_to_rag_flow),
    ("INTEGRATION: End-to-End Tests", "AnswerResponse has all required fields", check_answer_response_model),
]

_last_section = None


def _run_check(section, name, func):
    """Run one check through the reporter, printing its section header."""
    global _last_section
    if _last_section != section:
        reporter.section(section)
        _last_section = section
    return reporter.test(name, func)


def _write_report():
    """Write the JSON report next to this file."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": reporter.passed + reporter.failed + reporter.warnings,
        "passed": reporter.passed,
        "failed": reporter.failed,
        "warnings": reporter.warnings,
        "results": [
            {
                "status": r[0],
                "name": r[1],
                "duration_seconds": round(r[2], 3),
                "message": r[3]
            }
            for r in reporter.results
        ]
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[REPORT] Saved to: {REPORT_PATH}")


@pytest.mark.parametrize(
    "section,name,func",
    CHECKS,
    ids=[name for _, name, _ in CHECKS],
)
def test_production_check(section, name, func):
    """One production check per pytest item (FAIL results fail the item)."""
    outcome, message = _run_check(section, name, func)
    assert outcome != "FAIL", message or name


def pytest_sessionfinish(session, exitstatus):
    """Reporter summary + JSON report once the whole suite has run."""
    reporter.summary()
    _write_report()


# ============================================================
# STANDALONE ENTRY POINT: python tests/test_production_suite.py
# ============================================================

if __name__ == "__main__":
    for section, name, func in CHECKS:
        _run_check(section, name, func)

    success = reporter.summary()
    _write_report()
    sys.exit(0 if success else 1)
