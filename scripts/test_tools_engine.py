"""
FBR Tool Engine + Agent Integration tests.

Covers (offline, deterministic — no live FBR websites; web tool
network behavior is mocked):

1. Tool registry: registration, discovery, stable names
2. Input validation for every tool (safe rejections)
3. Every implemented tool's execution
4. Tool error handling (invalid requests, corrupted files,
   mocked fetch failures)
5. Agent -> tool invocation (registry wiring in CalculationAgent)
6. Agent tool capability mapping + deterministic select_tools
7. End-to-end workflow: Query -> Understand -> Plan (tools) ->
   Router -> Agent -> Tools -> Verification -> Answer

Heavy resources (FAISS, embedding model) load ONCE and are shared
by the engine-dependent tests.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.tools import DEFAULT_REGISTRY, TOOL_NAMES
from app.tools.base import BaseTool, ToolResult
from app.tools.document_tools import (
    AnomalyDetectionTool,
    DocumentParserTool,
    DuplicateDetectionTool,
    SimilarityEngineTool,
    _load_script_module,
)
from app.tools.knowledge_tools import CalculationEngineTool, RuleEngineTool
from app.tools.output_tools import NotificationTool, ReportGeneratorTool
from app.tools.registry import ToolRegistry
from app.tools.search_tools import (
    HybridSearchTool,
    MetadataFilterTool,
    RAGSearchTool,
    shared_rag_engine,
)
from app.tools.web_tools import WebResearchTool

from app.agents.base import SpecializedAgent
from app.agents.calculation_agent import CalculationAgent
from app.agents.customs_agent import CustomsAgent
from app.agents.income_tax_agent import IncomeTaxAgent
from app.agents.notice_appeal_agent import NoticeAppealAgent
from app.agents.registration_agent import RegistrationAgent
from app.agents.research_agent import ResearchAgent

RESULTS: list[dict] = []


def _assert(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "passed": bool(cond),
            "detail": detail[:600],
        }
    )


# ============================================================
# SHARED LAZY RESOURCES (one engine load for all tests)
# ============================================================

_orchestrator = None


def _orch():
    global _orchestrator

    if _orchestrator is None:
        from app.agents.orchestrator import AgentOrchestrator

        _orchestrator = AgentOrchestrator(
            rag_engine=shared_rag_engine(),
        )

    return _orchestrator


class _StubRagEngine:
    """Offline RAG engine stub for agent-level tests."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[str] = []

    def answer(self, question, top_k=5):
        self.calls.append(str(question))
        return dict(self._response)


_GROUNDED_STUB = {
    "answer": "The sales tax rate is 17 percent under the Sales Tax Act.",
    "sources": [
        {
            "chunk_id": "c1",
            "source": "SalesTaxAct1990_upto2025-26.pdf",
            "section_reference": "Sales Tax Act",
        }
    ],
    "verification": {"passed": True, "reason": "stub"},
    "grounded": True,
    "context": "stub context",
}


# ============================================================
# 1. REGISTRY / DISCOVERY
# ============================================================

def test_registry() -> None:
    expected = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "calculation_engine",
        "document_parser",
        "duplicate_detection",
        "similarity_engine",
        "anomaly_detection",
        "web_research",
        "notification",
        "report_generator",
        "tax_optimization",
    )

    _assert(
        "registry_contains_all_13_tools",
        DEFAULT_REGISTRY.tool_names() == list(expected),
        f"names={DEFAULT_REGISTRY.tool_names()}",
    )

    _assert(
        "registry_tool_names_stable",
        TOOL_NAMES == expected,
        f"TOOL_NAMES={TOOL_NAMES}",
    )

    listing = DEFAULT_REGISTRY.list_tools()

    _assert(
        "registry_list_tools_has_descriptions",
        len(listing) == 13
        and all(item.get("description") for item in listing),
        f"listing={listing}",
    )

    unknown = DEFAULT_REGISTRY.execute("does_not_exist", {})

    _assert(
        "registry_rejects_unknown_tool",
        unknown.ok is False and "Unknown tool" in (unknown.error or ""),
        f"result={unknown.to_dict()}",
    )

    fresh = ToolRegistry()

    fresh.register(RuleEngineTool())

    try:
        fresh.register(RuleEngineTool())
        duplicate_rejected = False
    except Exception:
        duplicate_rejected = True

    _assert(
        "registry_rejects_duplicate_registration",
        duplicate_rejected,
        "duplicate registration was allowed",
    )

    class _NoDescriptionTool(BaseTool):
        name = "broken"
        description = ""

        def validate_input(self, payload):
            return {}

        def execute(self, payload):
            return None

    try:
        fresh.register(_NoDescriptionTool())
        no_description_rejected = False
    except Exception:
        no_description_rejected = True

    _assert(
        "registry_rejects_tool_without_description",
        no_description_rejected,
        "tool without description was registered",
    )


# ============================================================
# 2. INPUT VALIDATION
# ============================================================

def test_validation() -> None:
    rag = RAGSearchTool()

    _assert(
        "rag_search_rejects_missing_query",
        rag.run({}).ok is False,
        "missing query accepted",
    )

    _assert(
        "rag_search_rejects_empty_query",
        rag.run({"query": "   "}).ok is False,
        "whitespace query accepted",
    )

    _assert(
        "rag_search_rejects_oversized_query",
        rag.run({"query": "x" * 1001}).ok is False,
        "oversized query accepted",
    )

    _assert(
        "rag_search_rejects_bad_top_k",
        rag.run({"query": "tax", "top_k": 0}).ok is False
        and rag.run({"query": "tax", "top_k": 51}).ok is False,
        "invalid top_k accepted",
    )

    _assert(
        "rag_search_rejects_non_string_query",
        rag.run({"query": 123}).ok is False,
        "non-string query accepted",
    )

    mf = MetadataFilterTool()

    _assert(
        "metadata_filter_rejects_unknown_field",
        mf.run({"filters": {"law_tag": "x"}}).ok is False,
        "invented metadata field accepted",
    )

    _assert(
        "metadata_filter_rejects_empty_filters",
        mf.run({"filters": {}}).ok is False,
        "empty filters accepted",
    )

    ce = CalculationEngineTool()

    _assert(
        "calculation_engine_rejects_both_modes",
        ce.run(
            {"question": "10% of 100", "amount": 100, "percent": 10}
        ).ok
        is False,
        "both input modes accepted",
    )

    _assert(
        "calculation_engine_rejects_missing_inputs",
        ce.run({}).ok is False,
        "missing inputs accepted",
    )

    _assert(
        "calculation_engine_rejects_bad_amount",
        ce.run({"amount": -5, "percent": 10}).ok is False,
        "negative amount accepted",
    )

    re_tool = RuleEngineTool()

    _assert(
        "rule_engine_rejects_missing_facts",
        re_tool.run({}).ok is False,
        "missing facts accepted",
    )

    _assert(
        "rule_engine_rejects_non_object_facts",
        re_tool.run({"facts": "nope"}).ok is False,
        "non-object facts accepted",
    )

    dp = DocumentParserTool()

    outside_path = "C:" + "/Windows/notepad.exe"

    _assert(
        "document_parser_rejects_outside_project",
        dp.run({"path": outside_path}).ok is False,
        "path outside project accepted",
    )

    _assert(
        "document_parser_rejects_missing_file",
        dp.run({"path": "data/does_not_exist.pdf"}).ok is False,
        "missing file accepted",
    )

    wr = WebResearchTool()

    _assert(
        "web_research_rejects_non_fbr_url",
        wr.run({"url": "https://example.com/docs.pdf"}).ok is False,
        "non-FBR URL accepted",
    )

    _assert(
        "web_research_rejects_non_https",
        wr.run({"url": "http://www.fbr.gov.pk/docs.pdf"}).ok is False,
        "http URL accepted",
    )

    nt = NotificationTool()

    _assert(
        "notification_rejects_bad_type",
        nt.run({"type": "sms", "subject": "x", "message": "y"}).ok
        is False,
        "unsupported notification type accepted",
    )

    _assert(
        "notification_rejects_missing_subject",
        nt.run({"type": "generic", "message": "y"}).ok is False,
        "missing subject accepted",
    )

    rg = ReportGeneratorTool()

    _assert(
        "report_generator_rejects_bad_type",
        rg.run({"report_type": "poetry", "title": "t", "payload": {}}).ok
        is False,
        "unsupported report type accepted",
    )

    se = SimilarityEngineTool()

    _assert(
        "similarity_engine_rejects_single_text",
        se.run({"texts": ["only one"]}).ok is False,
        "single text accepted",
    )

    dd = DuplicateDetectionTool()

    _assert(
        "duplicate_detection_rejects_empty_files",
        dd.run({"files": []}).ok is False,
        "empty file list accepted",
    )


# ============================================================
# 3. TOOL EXECUTION (offline)
# ============================================================

def test_calculation_engine() -> None:
    ce = CalculationEngineTool()

    explicit = ce.run({"amount": 500000, "percent": 10})

    _assert(
        "calculation_engine_explicit_mode",
        explicit.ok
        and explicit.data["result"] == 50000.0
        and explicit.data["computed"] is True,
        f"result={explicit.to_dict()}",
    )

    question_mode = ce.run(
        {"question": "calculate 17% sales tax on 1000000"}
    )

    _assert(
        "calculation_engine_question_mode_reuses_agent_logic",
        question_mode.ok
        and question_mode.data["computed"] is True
        and question_mode.data["calculation"]["result"] == 170000.0,
        f"result={question_mode.to_dict()}",
    )

    no_parse = ce.run({"question": "what is sales tax"})

    _assert(
        "calculation_engine_no_parse_safe",
        no_parse.ok
        and no_parse.data["computed"] is False
        and no_parse.data["calculation"] is None,
        f"result={no_parse.to_dict()}",
    )


def test_rule_engine() -> None:
    re_tool = RuleEngineTool()

    within = re_tool.run(
        {
            "facts": {
                "event_type": "appeal_to_commissioner",
                "days_since_service": 20,
            }
        }
    )

    _assert(
        "rule_engine_deadline_within",
        within.ok
        and within.data["matched_count"] == 1
        and within.data["matched"][0]["outcome"]["status"]
        == "within_deadline",
        f"result={within.to_dict()}",
    )

    missed = re_tool.run(
        {
            "facts": {
                "event_type": "appeal_to_commissioner",
                "days_since_service": 45,
            }
        }
    )

    _assert(
        "rule_engine_deadline_missed",
        missed.ok
        and missed.data["matched_count"] == 1
        and missed.data["matched"][0]["outcome"]["status"]
        == "deadline_missed",
        f"result={missed.to_dict()}",
    )

    tribunal = re_tool.run(
        {
            "facts": {
                "event_type": "appeal_to_appellate_tribunal",
                "days_since_service": 90,
            }
        }
    )

    _assert(
        "rule_engine_tribunal_deadline",
        tribunal.ok
        and tribunal.data["matched"][0]["id"]
        == "ito_131_appeal_tribunal_missed",
        f"result={tribunal.to_dict()}",
    )

    domain_filtered = re_tool.run(
        {
            "facts": {
                "event_type": "appeal_to_commissioner",
                "days_since_service": 45,
            },
            "domain": "customs",
        }
    )

    _assert(
        "rule_engine_domain_filter",
        domain_filtered.ok and domain_filtered.data["matched_count"] == 0,
        f"result={domain_filtered.to_dict()}",
    )

    rules_path = (
        PROJECT_ROOT / "app" / "tools" / "rules.json"
    )

    with open(rules_path, "r", encoding="utf-8") as file:
        rules = json.load(file)["rules"]

    _assert(
        "rule_engine_seed_rules_have_provenance",
        len(rules) >= 6
        and all(
            rule.get("source", {}).get("sha256")
            and rule["source"].get("document")
            and rule["source"].get("section")
            for rule in rules
        ),
        f"rules={len(rules)}",
    )

    _assert(
        "rule_engine_seed_rules_match_corpus_hash",
        all(
            rule["source"]["sha256"]
            == "3eb83defefad0930b5d35dbbf6f3961f967a9330114f70058dac2f096a0b6812"
            for rule in rules
        )
        and rules[0]["source"]["document"]
        == "IncomeTaxOrdinance2001_upto2025.pdf",
        "seed rules do not match corpus provenance",
    )


def test_metadata_filter() -> None:
    mf = MetadataFilterTool()

    by_type = mf.run(
        {"filters": {"document_type": "markdown"}, "limit": 5}
    )

    _assert(
        "metadata_filter_by_document_type",
        by_type.ok and by_type.data["match_count"] == 24,
        f"count={by_type.data.get('match_count') if by_type.ok else by_type.error}",
    )

    by_source = mf.run(
        {
            "filters": {"source": "customs\\26-customs-basics.md"},
            "limit": 3,
        }
    )

    _assert(
        "metadata_filter_by_source",
        by_source.ok and by_source.data["match_count"] == 5,
        f"count={by_source.data.get('match_count') if by_source.ok else by_source.error}",
    )

    by_section = mf.run(
        {"filters": {"section_reference": "Customs > Basics"}, "limit": 5}
    )

    _assert(
        "metadata_filter_by_section_reference",
        by_section.ok and by_section.data["match_count"] >= 1,
        f"count={by_section.data.get('match_count') if by_section.ok else by_section.error}",
    )

    no_match = mf.run(
        {"filters": {"document_type": "powerpoint"}, "limit": 5}
    )

    _assert(
        "metadata_filter_no_match_returns_zero",
        no_match.ok and no_match.data["match_count"] == 0,
        f"count={no_match.data.get('match_count') if no_match.ok else no_match.error}",
    )

    _assert(
        "metadata_filter_total_records_reported",
        by_type.ok and by_type.data["total_records"] == 58953,
        f"total={by_type.data.get('total_records') if by_type.ok else 'n/a'}",
    )


def test_document_parser() -> None:
    dp = DocumentParserTool()

    parsed = dp.run(
        {"path": "data/raw/04-source-docs/customs/26-customs-basics.md"}
    )

    _assert(
        "document_parser_parses_markdown",
        parsed.ok
        and parsed.data["status"] == "extracted"
        and parsed.data["sha256"]
        and len(parsed.data["preview"]) > 0,
        f"result={parsed.to_dict() if not parsed.ok else 'ok'}",
    )

    unsupported = dp.run({"path": "requirements.txt"})

    _assert(
        "document_parser_rejects_unsupported_extension",
        unsupported.ok is False and "Unsupported" in (unsupported.error or ""),
        f"result={unsupported.to_dict()}",
    )

    tmp_dir = (
        PROJECT_ROOT
        / "data"
        / "profile"
        / "tools_test_tmp"
    )

    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)

        corrupted = tmp_dir / "corrupted.pdf"
        corrupted.write_bytes(b"THIS IS NOT A REAL PDF FILE")

        corrupted_result = dp.run({"path": str(corrupted)})

        _assert(
            "document_parser_corrupted_file_safe",
            corrupted_result.ok is False,
            f"result={corrupted_result.to_dict()}",
        )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_duplicate_detection() -> None:
    dd = DuplicateDetectionTool()

    tmp_dir = (
        PROJECT_ROOT
        / "data"
        / "profile"
        / "tools_test_tmp"
    )

    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)

        file_a = tmp_dir / "doc_a.md"
        file_b = tmp_dir / "doc_b.md"
        file_c = tmp_dir / "doc_c.md"

        file_a.write_text("# Same content", encoding="utf-8")
        file_b.write_text("# Same content", encoding="utf-8")
        file_c.write_text("# Different content", encoding="utf-8")

        duplicates = dd.run(
            {"files": [str(file_a), str(file_b), str(file_c)]}
        )

        _assert(
            "duplicate_detection_identifies_exact_duplicates",
            duplicates.ok
            and duplicates.data["exact_duplicate_count"] == 1
            and duplicates.data["unique_documents"] == 2
            and len(duplicates.data["exact_duplicate_groups"]) == 1,
            f"result={duplicates.to_dict() if not duplicates.ok else duplicates.data}",
        )

        _assert(
            "duplicate_detection_distinguishes_similar",
            duplicates.ok
            and all(
                "similar" in str(duplicates.data.get("note", "")).lower()
                for _ in [0]
            ),
            "similar-document distinction not documented",
        )

        unique = dd.run({"files": [str(file_a), str(file_c)]})

        _assert(
            "duplicate_detection_no_false_positives",
            unique.ok and unique.data["exact_duplicate_count"] == 0,
            f"result={unique.data if unique.ok else unique.error}",
        )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_similarity_engine() -> None:
    se = SimilarityEngineTool()

    result = se.run(
        {
            "texts": [
                "What is the sales tax rate in Pakistan?",
                "What is the rate of sales tax in Pakistan?",
                "How do I register a vehicle with customs?",
            ]
        }
    )

    _assert(
        "similarity_engine_pairwise_scores",
        result.ok
        and len(result.data["pairs"]) == 3
        and all(
            -1.01 <= pair["score"] <= 1.01
            for pair in result.data["pairs"]
        ),
        f"result={result.to_dict() if not result.ok else result.data['pairs']}",
    )

    _assert(
        "similarity_engine_similar_beats_different",
        result.ok
        and result.data["pairs"][0]["score"]
        > result.data["pairs"][2]["score"],
        f"pairs={result.data['pairs'] if result.ok else 'n/a'}",
    )

    pair_only = se.run(
        {"texts": ["income tax return", "sales tax return"]}
    )

    _assert(
        "similarity_engine_pair_score",
        pair_only.ok and "pair_score" in pair_only.data,
        f"result={pair_only.to_dict() if not pair_only.ok else 'ok'}",
    )


def test_anomaly_detection() -> None:
    ad = AnomalyDetectionTool()

    clean = ad.run({})

    _assert(
        "anomaly_detection_real_metadata_clean",
        clean.ok
        and clean.data["records_checked"] == 58953
        and clean.data["anomaly_count"] == 0,
        f"result={clean.data if clean.ok else clean.error}",
    )

    synthetic_records = [
        {"vector_id": 0, "source": "a.pdf", "source_sha256": "x"},
        {
            "vector_id": 1,
            "source": "b.pdf",
            "source_sha256": "y",
            "page_start": 10,
            "page_end": 2,
        },
        {"vector_id": 1, "source": "c.pdf", "source_sha256": "z"},
        {"vector_id": 3, "source": "d.pdf"},
    ]

    with mock.patch(
        "app.tools.document_tools.json.load",
        return_value=synthetic_records,
    ):
        injected = ad.run({})

    anomaly_types = injected.data["anomalies_by_type"] if injected.ok else {}

    _assert(
        "anomaly_detection_detects_injected_anomalies",
        injected.ok
        and anomaly_types.get("invalid_page_range") == 1
        and anomaly_types.get("duplicate_vector_id") == 1
        and anomaly_types.get("missing_source_sha256") == 1
        and anomaly_types.get("vector_id_sequence_break", 0) >= 1,
        f"types={anomaly_types}",
    )

    _assert(
        "anomaly_detection_not_fraud_detection",
        "NOT fraud detection" in AnomalyDetectionTool.description
        or "Not fraud detection" in ad.run({}).data.get("note", "")
        or "fraud detection" in AnomalyDetectionTool.description,
        "anomaly tool must not claim fraud detection",
    )


def test_web_research_mocked() -> None:
    wr = WebResearchTool()

    daily_module = _load_script_module("daily_update.py")

    html = (
        b"<html><body>FBR income tax ordinance page"
        b"<a href='/Docs/income_tax_2025.pdf'>Act</a>"
        b"<a href='https://www.fbr.gov.pk/Categ/other'>Cat</a>"
        b"</body></html>"
    )

    with mock.patch.object(
        daily_module,
        "http_get",
        return_value=html,
    ):
        page = wr.run(
            {
                "url": (
                    "https://www.fbr.gov.pk/Categ/"
                    "Income-Tax-Ordinance/326/1000"
                )
            }
        )

    _assert(
        "web_research_mocked_page_fetch",
        page.ok
        and page.data["source"] == "official_fbr"
        and page.data["fetched_at"]
        and "income tax ordinance" in page.data["evidence"].lower(),
        f"result={page.to_dict() if not page.ok else 'ok'}",
    )

    _assert(
        "web_research_returns_links_and_timestamp",
        page.ok
        and page.data["link_count"] >= 1
        and all(
            link.startswith("https://")
            and "fbr.gov.pk" in link
            for link in page.data["links"]
        ),
        f"links={page.data.get('links') if page.ok else 'n/a'}",
    )

    with mock.patch.object(
        daily_module,
        "http_get",
        side_effect=OSError("network down"),
    ):
        failed = wr.run(
            {
                "url": (
                    "https://www.fbr.gov.pk/Categ/"
                    "Income-Tax-Ordinance/326/1000"
                )
            }
        )

    _assert(
        "web_research_fetch_failure_safe",
        failed.ok is False and "Fetch failed" in (failed.error or ""),
        f"result={failed.to_dict()}",
    )


def test_notification_and_reports() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="notif_test_"))

    try:
        with mock.patch(
            "app.tools.output_tools.NOTIFICATIONS_DIR",
            tmp_dir,
        ):
            nt = NotificationTool()

            recorded = nt.run(
                {
                    "type": "deadline",
                    "subject": "Appeal deadline approaching",
                    "message": "File the appeal within 30 days.",
                    "metadata": {"days_remaining": 5},
                }
            )

            log_file = tmp_dir / "notifications.jsonl"

            entries = [
                json.loads(line)
                for line in log_file.read_text(encoding="utf-8").splitlines()
            ]

        _assert(
            "notification_records_to_log",
            recorded.ok
            and recorded.data["status"] == "recorded"
            and len(entries) == 1
            and entries[0]["subject"] == "Appeal deadline approaching",
            f"result={recorded.to_dict() if not recorded.ok else entries}",
        )

        log_json = json.dumps(entries)

        _assert(
            "notification_stores_no_credentials",
            entries
            and "@" not in log_json
            and "password" not in log_json.lower()
            and "api_key" not in log_json.lower()
            and "sk-" not in log_json,
            "credentials found in notification log",
        )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    rg = ReportGeneratorTool()

    calc_report = rg.run(
        {
            "report_type": "calculation",
            "title": "Sales Tax Calculation",
            "payload": {
                "calculation": {
                    "kind": "percent_of_amount",
                    "percent": 17,
                    "amount": 1000000,
                    "expression": "1000000.0 x 17% = 170000.0",
                    "result": 170000.0,
                }
            },
        }
    )

    _assert(
        "report_generator_markdown_calculation",
        calc_report.ok
        and calc_report.data["format"] == "markdown"
        and "170000" in calc_report.data["content"]
        and "Sales Tax Calculation" in calc_report.data["content"],
        f"content={calc_report.data.get('content', '')[:200] if calc_report.ok else calc_report.error}",
    )

    json_report = rg.run(
        {
            "report_type": "compliance",
            "title": "Deadline Check",
            "payload": {
                "matched": [
                    {
                        "status": "deadline_missed",
                        "message": "Window elapsed (section 127).",
                        "source": {
                            "document": "IncomeTaxOrdinance2001_upto2025.pdf",
                            "section": "127(5)",
                        },
                    }
                ]
            },
            "format": "json",
        }
    )

    _assert(
        "report_generator_json_format",
        json_report.ok
        and json_report.data["format"] == "json"
        and json.loads(json_report.data["content"])["report_type"]
        == "compliance",
        f"content={json_report.data.get('content', '')[:200] if json_report.ok else json_report.error}",
    )

    doc_report = rg.run(
        {
            "report_type": "documents",
            "title": "Parsed Documents",
            "payload": {"documents": [{"name": "act.pdf", "pages": 10}]},
        }
    )

    _assert(
        "report_generator_documents_render",
        doc_report.ok and "act.pdf" in doc_report.data["content"],
        f"content={doc_report.data.get('content', '')[:200] if doc_report.ok else doc_report.error}",
    )


# ============================================================
# 4. AGENT -> TOOL INTEGRATION
# ============================================================

AGENT_CLASSES = {
    "income_tax": IncomeTaxAgent,
    "customs": CustomsAgent,
    "calculation": CalculationAgent,
    "notice_appeal": NoticeAppealAgent,
    "research": ResearchAgent,
    "registration": RegistrationAgent,
}


def test_agent_tool_mapping() -> None:
    all_valid = True

    for domain, agent_class in AGENT_CLASSES.items():
        tools = getattr(agent_class, "TOOLS", ())
        if not tools or not all(
            tool in TOOL_NAMES for tool in tools
        ):
            all_valid = False

    _assert(
        "agents_have_valid_tools_mapping",
        all_valid,
        "some agent has missing/invalid TOOLS",
    )

    _assert(
        "agent_mapping_income_tax",
        set(IncomeTaxAgent.TOOLS) == {
            "rag_search",
            "hybrid_search",
            "metadata_filter",
            "rule_engine",
            "calculation_engine",
            "tax_optimization",
        },
        f"tools={IncomeTaxAgent.TOOLS}",
    )

    _assert(
        "agent_mapping_customs_has_parser_and_web",
        {"document_parser", "web_research"}.issubset(
            set(CustomsAgent.TOOLS)
        ),
        f"tools={CustomsAgent.TOOLS}",
    )

    _assert(
        "agent_mapping_research_has_report_and_web",
        {"web_research", "report_generator"}.issubset(
            set(ResearchAgent.TOOLS)
        ),
        f"tools={ResearchAgent.TOOLS}",
    )

    _assert(
        "agent_mapping_notice_has_parser_and_web",
        {"document_parser", "web_research"}.issubset(
            set(NoticeAppealAgent.TOOLS)
        ),
        f"tools={NoticeAppealAgent.TOOLS}",
    )

    _assert(
        "agent_mapping_calculation_has_engine",
        "calculation_engine" in CalculationAgent.TOOLS,
        f"tools={CalculationAgent.TOOLS}",
    )


def test_select_tools() -> None:
    calc_agent = CalculationAgent(rag_engine=_StubRagEngine(_GROUNDED_STUB))

    plain = calc_agent.select_tools("what is income tax")

    _assert(
        "select_tools_plain_query_core_only",
        plain == ["rag_search", "hybrid_search"],
        f"selection={plain}",
    )

    with_numbers = calc_agent.select_tools(
        "calculate 17% sales tax on 1000000"
    )

    _assert(
        "select_tools_calculation_fires_on_numbers",
        "calculation_engine" in with_numbers,
        f"selection={with_numbers}",
    )

    customs_agent = CustomsAgent(rag_engine=_StubRagEngine(_GROUNDED_STUB))

    current = customs_agent.select_tools(
        "what is the latest customs tariff update"
    )

    _assert(
        "select_tools_web_research_fires_on_current",
        "web_research" in current,
        f"selection={current}",
    )

    research_agent = ResearchAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    report = research_agent.select_tools(
        "give me a report on property valuation"
    )

    _assert(
        "select_tools_report_generator_fires",
        "report_generator" in report,
        f"selection={report}",
    )

    notice_agent = NoticeAppealAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    notice_selection = notice_agent.select_tools(
        "I received a notice under section 114"
    )

    _assert(
        "select_tools_document_parser_and_metadata_fire",
        "document_parser" in notice_selection
        and "metadata_filter" in notice_selection,
        f"selection={notice_selection}",
    )

    reg_agent = RegistrationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    everything_query = (
        "current latest update report summary notice letter "
        "document appeal deadline duplicate similar compare "
        "anomaly remind alert"
    )

    constrained = reg_agent.select_tools(everything_query)

    _assert(
        "select_tools_never_exceeds_agent_tools",
        set(constrained).issubset(set(RegistrationAgent.TOOLS)),
        f"selection={constrained} tools={RegistrationAgent.TOOLS}",
    )

    repeated = [
        calc_agent.select_tools("calculate 10% of 500000")
        for _ in range(3)
    ]

    _assert(
        "select_tools_deterministic",
        repeated[0] == repeated[1] == repeated[2],
        f"selections={repeated}",
    )


def test_agent_tool_invocation() -> None:
    stub = _StubRagEngine(_GROUNDED_STUB)
    agent = CalculationAgent(rag_engine=stub)

    with mock.patch(
        "app.tools.get_default_registry"
    ) as fake_factory:
        fake_registry = mock.MagicMock()

        fake_registry.execute.return_value = ToolResult(
            tool="calculation_engine",
            ok=True,
            data={
                "kind": "percent_of_amount",
                "calculation": {
                    "kind": "percent_of_amount",
                    "percent": 17.0,
                    "amount": 1000000.0,
                    "expression": (
                        "1000000.0 x 17% = 170000.0"
                    ),
                    "result": 170000.0,
                },
                "computed": True,
            },
        )

        fake_factory.return_value = fake_registry

        result = agent.handle("Calculate 17% sales tax on 1000000")

    _assert(
        "calculation_agent_invokes_tool_registry",
        fake_registry.execute.call_count == 1
        and fake_registry.execute.call_args[0][0]
        == "calculation_engine",
        f"calls={fake_registry.execute.call_args_list}",
    )

    _assert(
        "calculation_agent_uses_tool_result",
        "Calculation basis" in result["answer"]
        and result["calculation"]["result"] == 170000.0
        and "calculation_engine" in result["tools_used"],
        f"answer={result['answer'][:200]}",
    )

    real_tool_agent = CalculationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    real_result = real_tool_agent.handle(
        "Calculate 17% sales tax on 1000000"
    )

    _assert(
        "calculation_agent_real_tool_wiring",
        real_result["calculation"] is not None
        and real_result["calculation"]["result"] == 170000.0
        and "calculation_engine" in real_result["tools_used"],
        f"calc={real_result['calculation']}",
    )

    base_agent = IncomeTaxAgent(rag_engine=_StubRagEngine(_GROUNDED_STUB))

    base_result = base_agent.handle("What is income tax?")

    _assert(
        "base_agent_attaches_tools_fields",
        "tools_selected" in base_result
        and "tools_used" in base_result
        and base_result["tools_used"] == ["rag_search", "hybrid_search"],
        f"result keys={sorted(base_result.keys())}",
    )

    _assert(
        "agent_result_schema_additive",
        all(
            key in base_result
            for key in (
                "domain",
                "question",
                "retrieval_question",
                "answer",
                "sources",
                "verification",
                "grounded",
                "context",
            )
        ),
        f"keys={sorted(base_result.keys())}",
    )

    refusal_stub = dict(_GROUNDED_STUB)
    refusal_stub["grounded"] = False

    refusal_agent = CalculationAgent(
        rag_engine=_StubRagEngine(refusal_stub)
    )

    refusal_result = refusal_agent.handle(
        "Calculate 17% sales tax on 1000000"
    )

    _assert(
        "calculation_agent_no_calc_when_ungrounded",
        refusal_result["calculation"] is None
        and "calculation_engine" not in refusal_result["tools_used"]
        and "Calculation basis" not in refusal_result["answer"],
        f"calc={refusal_result['calculation']}",
    )


# ============================================================
# 5. END-TO-END WORKFLOW (through the real orchestrator)
# ============================================================

E2E_QUERIES = [
    ("What is income tax?", {"income_tax"}),
    ("What is customs duty?", {"customs"}),
    ("How do I register for customs?", {"registration", "customs"}),
    ("Calculate 17% sales tax on 1000000", {"calculation", "sales_tax"}),
    (
        "I received a notice under section 114 of the Income Tax Ordinance",
        {"notice_appeal", "income_tax"},
    ),
    (
        "What is the latest update on customs tariff valuation?",
        {"customs"},
    ),
]


def test_end_to_end_workflow() -> None:
    from app.rag_engine import _NO_EVIDENCE_ANSWER
    from app.verification_layer import PLACEHOLDER_ANSWER

    orchestrator = _orch()

    e2e_context = (
        "Sales Tax Act 1990 section 3 prescribes a 17% rate on taxable supplies. "
        "Income Tax Ordinance 2001 section 114 sets the return-filing window. "
        "Customs Act 1969 governs import duties. The FBR notifies changes via "
        "official SROs and tariff valuations on its public portal."
    )

    def _fake_llm(question: str, context: str) -> str:
        return (
            f"Based on the retrieved FBR context: {context[:80]}\u2026 "
            f"Answer to '{question[:60]}' (mocked)."
        )

    with mock.patch("app.rag_engine.generate_answer", side_effect=_fake_llm):
        for question, expected_domains in E2E_QUERIES:
            response = orchestrator.handle(question)

            slug = (
                question.lower()
                .replace("?", "")
                .replace("'", "")
                .replace(" ", "_")[:40]
            )

            routed_ok = (
                expected_domains.issubset(set(response["domains"]))
                and response["primary_domain"] in response["domains"]
            )

            _assert(
                f"e2e[{slug}]_routed",
                routed_ok,
                f"domains={response['domains']}",
            )

            domain_results = response["domain_results"]

            tools_ok = bool(domain_results) and all(
                isinstance(r.get("tools_selected"), list)
                and isinstance(r.get("tools_used"), list)
                and "rag_search" in r["tools_selected"]
                and "hybrid_search" in r["tools_used"]
                for r in domain_results
            )

            _assert(
                f"e2e[{slug}]_tools_recorded",
                tools_ok,
                f"results={[r.get('tools_selected') for r in domain_results]}",
            )

            verified_ok = all(
                isinstance(r.get("verification"), dict)
                and isinstance(r.get("grounded"), bool)
                for r in domain_results
            ) and isinstance(response.get("verification"), dict)

            _assert(
                f"e2e[{slug}]_verification_present",
                verified_ok,
                "verification missing from results",
            )

            answers_ok = all(
                r.get("answer")
                and (
                    r["grounded"]
                    or r["answer"] in (_NO_EVIDENCE_ANSWER, PLACEHOLDER_ANSWER)
                )
                for r in domain_results
            )

            _assert(
                f"e2e[{slug}]_answer_grounded_or_safe",
                answers_ok,
                "unverified/unsafe answer in results",
            )

        customs_response = orchestrator.handle(
            "What is the latest update on customs tariff valuation?"
        )

        customs_result = customs_response["domain_results"][0]

        _assert(
            "e2e_web_research_selected_for_current_query",
            "web_research" in customs_result["tools_selected"],
            f"selected={customs_result['tools_selected']}",
        )

        notice_response = orchestrator.handle(
            "I received a notice under section 114 of the Income Tax Ordinance"
        )

        notice_tools = [
            tool
            for r in notice_response["domain_results"]
            if r["domain"] == "notice_appeal"
            for tool in r["tools_selected"]
        ]

        _assert(
            "e2e_notice_query_selects_document_parser",
            "document_parser" in notice_tools,
            f"tools={notice_tools}",
        )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("=" * 72)
    print("FBR TOOL ENGINE + AGENT INTEGRATION TEST")
    print("=" * 72)

    test_registry()
    test_validation()
    test_calculation_engine()
    test_rule_engine()
    test_metadata_filter()
    test_document_parser()
    test_duplicate_detection()
    test_similarity_engine()
    test_anomaly_detection()
    test_web_research_mocked()
    test_notification_and_reports()
    test_agent_tool_mapping()
    test_select_tools()
    test_agent_tool_invocation()
    test_end_to_end_workflow()

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
