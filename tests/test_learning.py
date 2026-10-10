"""
Test Suite for the Self-Learning / Personalization Module
=========================================================

Covers the behavioural-personalization contract end to end:

- `extract_signals` domain/entity/year/language detection
- `build_profile` time decay and top_domains ordering
- per-user isolation, opt-out, retention + the 500-row cap
- `build_recommendations` kinds, dismissed ids, deadline cap
- feedback recording, privacy export and deletion
- the assistant hot-path integration (response field, SSE event,
  prompt injection, interaction recording) including the degrade
  paths where learning must never fail an answer

Behavioural personalization only — no model weights are involved.
"""

import gc
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from app.learning import (
    LearningStore,
    UserProfile,
    build_profile,
    build_recommendations,
    extract_signals,
)
from app.routers.assistant import (
    _final_answer,
    _final_answer_stream,
    _learning_context,
    _learning_snapshot,
    _personalization_block,
    _record_interaction,
)
from app.supabase_auth import require_user

EMPTY_PERSONALIZATION = {
    "enabled": False,
    "recommendations": [],
    "profile_summary": None,
}

# Every kind `build_recommendations` may emit.
RECOMMENDATION_KINDS = {
    "deadline",
    "calculator",
    "verification",
    "tax_health",
    "notice_followup",
    "document_followup",
    "learning_topic",
}


# =============================================================================
# extract_signals
# =============================================================================

def _remove_temp_tree(path: str) -> None:
    """Best-effort delete of a temp dir that held a live SQLite DB.

    On Windows an interpreter-level cache keeps the schema connection of a
    `LearningStore` alive for the whole process, so the DB file cannot be
    unlinked until that cache is flushed. Retry, then leave the OS temp
    file behind — a test must never fail because of a cleanup file lock.
    """
    for _ in range(3):
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.isdir(path):
            return

class TestExtractSignals(unittest.TestCase):
    """Deterministic signal extraction from one user's own query text."""

    def test_salary_query_with_amounts(self):
        signals = extract_signals(
            "What is the income tax on my salary of PKR 1,200,000 for tax year 2025?"
        )
        self.assertEqual(signals["money_amounts"], [1200000.0])
        self.assertEqual(signals["tax_year"], 2025)
        self.assertEqual(signals["entity_type"], "salaried")
        self.assertEqual(signals["language"], "en")

    def test_business_query(self):
        signals = extract_signals(
            "My company earned business income of Rs. 5,000,000 — how much tax is due?"
        )
        self.assertEqual(signals["money_amounts"], [5000000.0])
        self.assertEqual(signals["entity_type"], "company")
        self.assertEqual(signals["language"], "en")

    def test_notice_query_section_177(self):
        signals = extract_signals(
            "I have received a legal notice under section 177 of the Income Tax "
            "Ordinance, what should I do?"
        )
        self.assertEqual(signals["notice_type"], "notice_177_rectification")

    def test_roman_urdu_query(self):
        signals = extract_signals("mujhe meri salary ka kitna tax lagay ga 2025 mein?")
        self.assertEqual(signals["language"], "roman_ur")
        self.assertEqual(signals["entity_type"], "salaried")
        self.assertEqual(signals["tax_year"], 2025)

    def test_empty_text(self):
        # Language always resolves ("en" default); no other signal is found.
        signals = extract_signals("")
        self.assertEqual(signals, {"language": "en"})
        for absent in ("money_amounts", "tax_year", "ntn", "notice_type",
                       "doc_type", "entity_type", "filing_status"):
            self.assertNotIn(absent, signals)


# =============================================================================
# build_profile — time decay and ordering
# =============================================================================

def _iso(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class TestBuildProfileTimeDecay(unittest.TestCase):
    """Exponential decay: old low-count interest loses to recent interest."""

    def _profile(self) -> UserProfile:
        rows = [
            # Old, single, low-weight interaction (weight ~0.5 ** 4).
            {
                "domain": "income_tax",
                "tools": ["calculate"],
                "signals": {"tax_year": 2023, "entity_type": "salaried"},
                "rating": None,
                "created_at": _iso(days_ago=120),
            },
        ]
        # Recent, repeated interactions (weight ~1 each, all positive).
        for _ in range(4):
            rows.append(
                {
                    "domain": "sales_tax",
                    "tools": ["calculate", "calendar"],
                    "signals": {"tax_year": 2025, "entity_type": "business"},
                    "rating": 1,
                    "created_at": _iso(days_ago=0.25),
                }
            )
        return build_profile(rows, decay_days=30)

    def test_recent_beats_old(self):
        profile = self._profile()
        self.assertEqual(profile.top_domains[0][0], "sales_tax")
        self.assertEqual([d for d, _ in profile.top_domains], ["sales_tax", "income_tax"])
        self.assertGreater(profile.top_domains[0][1], profile.top_domains[1][1])

    def test_recency_weighted_modes(self):
        profile = self._profile()
        self.assertEqual(profile.tax_year, 2025)
        self.assertEqual(profile.entity_type, "business")
        self.assertEqual(profile.total_interactions, 5)
        self.assertEqual(sorted(profile.frequent_tools), ["calculate", "calendar"])

    def test_dict_shape(self):
        data = self._profile().dict()
        self.assertEqual(
            set(data), {"signals", "top_domains", "total_interactions", "last_active"}
        )
        self.assertIsInstance(data["top_domains"][0], list)
        self.assertEqual(data["total_interactions"], 5)
        self.assertEqual(data["signals"]["language"], None)  # none was recorded


# =============================================================================
# Store: isolation, opt-out, retention, caps
# =============================================================================

class LearningStoreTestCase(unittest.TestCase):
    """Base case with an isolated temp learning DB (never the real one)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(_remove_temp_tree, self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "learning.db")
        self.store = LearningStore(db_path=self.db_path)
        self.addCleanup(self._reset_store_singleton)
        self.assertTrue(self.store.available, "temp learning store must be available")
        self.user_a = "user-a"
        self.user_b = "user-b"

    @staticmethod
    def _reset_store_singleton():
        import app.learning.store as store_module

        store_module._store = None

    def _insert_old_row(self, user_id: str, days_ago: float, domain: str = "income_tax"):
        """Insert a row with a backdated created_at (retention test fixture)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO interactions"
                " (id, user_id, query, domain, tools, signals, rating, channel, created_at)"
                " VALUES (?, ?, '', ?, '[]', '{}', NULL, 'assistant', ?)",
                (
                    "int-" + uuid.uuid4().hex[:16],
                    user_id,
                    domain,
                    _iso(days_ago=days_ago),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _count_rows(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM interactions WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        finally:
            conn.close()


class TestPerUserIsolation(LearningStoreTestCase):
    """One user's interactions never leak into another user's profile."""

    def setUp(self):
        super().setUp()
        for _ in range(3):
            self.store.record_interaction(
                self.user_a,
                query="calculate salary tax on 1200000",
                domain="income_tax",
                tools=["calculate"],
                signals={"tax_year": 2025, "entity_type": "salaried"},
            )

    def test_user_b_has_no_profile_or_recs(self):
        self.assertIsNone(self.store.get_profile(self.user_b))

        # Behavioural suggestions are per-user: user B (no history) may only
        # ever get the generic tax-health nudge plus static calendar
        # deadlines — never a suggestion derived from user A's history.
        recs_b = self.store.get_recommendations(self.user_b, limit=10)
        behavioural_b = [r.id for r in recs_b if r.kind != "deadline"]
        self.assertEqual(behavioural_b, ["tax_health:check"])

        # ...while user A's own history drives A's feed.
        recs_a = self.store.get_recommendations(self.user_a, limit=10)
        ids_a = [r.id for r in recs_a]
        self.assertIn("learning_topic:income_tax", ids_a)
        self.assertIn("calculator:salary_tax", ids_a)
        self.assertIn("verification:filer", ids_a)

        export = self.store.export_user_data(self.user_b)
        self.assertEqual(export["interactions"], [])
        self.assertEqual(export["feedback"], [])
        self.assertEqual(self._count_rows(self.user_b), 0)

    def test_user_a_profile_present(self):
        profile = self.store.get_profile(self.user_a)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.total_interactions, 3)
        self.assertEqual(profile.top_domains[0][0], "income_tax")
        self.assertTrue(self.store.get_recommendations(self.user_a))


class TestOptOut(LearningStoreTestCase):
    """Opting out disables recording and reads for that user only."""

    def test_opt_out_is_a_noop(self):
        self.assertTrue(self.store.is_personalized(self.user_a))
        self.store.set_personalized(self.user_a, False)
        self.assertFalse(self.store.is_personalized(self.user_a))

        self.store.record_interaction(
            self.user_a, query="calculate salary tax on 1200000", domain="income_tax"
        )
        self.assertIsNone(self.store.get_profile(self.user_a))
        self.assertEqual(self.store.get_recommendations(self.user_a), [])
        self.assertEqual(self._count_rows(self.user_a), 0)

        # Another user is unaffected by user A's opt-out.
        self.assertTrue(self.store.is_personalized(self.user_b))
        self.store.record_interaction(self.user_b, query="sales tax", domain="sales_tax")
        self.assertIsNotNone(self.store.get_profile(self.user_b))

    def test_opt_back_in(self):
        self.store.set_personalized(self.user_a, False)
        self.store.set_personalized(self.user_a, True)
        self.assertTrue(self.store.is_personalized(self.user_a))
        self.store.record_interaction(self.user_a, query="salary tax", domain="income_tax")
        self.assertIsNotNone(self.store.get_profile(self.user_a))


class TestRetentionAndCaps(LearningStoreTestCase):
    """Retention window, prune_expired and the hard 500-row cap."""

    def test_prune_expired_drops_old_rows(self):
        self._insert_old_row(self.user_a, days_ago=200)
        self._insert_old_row(self.user_a, days_ago=120)
        self._insert_old_row(self.user_a, days_ago=1)

        deleted = self.store.prune_expired()
        self.assertGreaterEqual(deleted, 2)

        profile = self.store.get_profile(self.user_a)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.total_interactions, 1)
        self.assertEqual(self._count_rows(self.user_a), 1)

    def test_record_interaction_prunes_expired(self):
        self._insert_old_row(self.user_a, days_ago=400)
        self.store.record_interaction(self.user_a, query="salary tax", domain="income_tax")
        self.assertEqual(self._count_rows(self.user_a), 1)

    def test_500_row_cap_holds(self):
        # Seed just above the cap in one connection (520 record_interaction
        # calls would be O(n^2) SQLite writes), then let ONE
        # record_interaction enforce the hard per-user cap.
        rows = [
            (
                "int-" + uuid.uuid4().hex[:16],
                self.user_a,
                _iso(days_ago=0.01 * i),
            )
            for i in range(505)
        ]
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                "INSERT INTO interactions"
                " (id, user_id, query, domain, tools, signals, rating, channel, created_at)"
                " VALUES (?, ?, '', 'income_tax', '[\"calculate\"]', '{\"tax_year\": 2025}',"
                " NULL, 'assistant', ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self._count_rows(self.user_a), 505)

        self.store.record_interaction(
            self.user_a, query="salary tax", domain="income_tax", tools=["calculate"]
        )
        exported = self.store.export_user_data(self.user_a)["interactions"]
        self.assertEqual(len(exported), 500)
        self.assertEqual(self._count_rows(self.user_a), 500)

        # The cap is per user: user B is unaffected.
        self.store.record_interaction(self.user_b, query="notice 177", domain="notices")
        self.assertEqual(self._count_rows(self.user_b), 1)


# =============================================================================
# Recommender
# =============================================================================

class _FakeEvent:
    """Minimal stand-in for a compliance-calendar event."""

    def __init__(self, ev_id: str, title: str, due_date: str, days: int):
        self.id = ev_id
        self.title = title
        self.due_date = due_date
        self._days = days

    def days_until_due(self) -> int:
        return self._days


def _personalized_profile() -> UserProfile:
    return UserProfile(
        top_domains=[("income_tax", 9.0), ("sales_tax", 2.5)],
        tax_year=2025,
        entity_type="salaried",
        language="en",
        filing_status="filer",
        frequent_tools=["notice_analyzer", "calculate"],
        document_types_seen=["Salary Certificate"],
        total_interactions=12,
    )


class TestRecommender(unittest.TestCase):
    """build_recommendations kinds, dismissed ids and deadline cap."""

    def test_only_expected_kinds(self):
        recs = build_recommendations(_personalized_profile(), [], [], limit=7)
        self.assertTrue(recs)
        kinds = {r.kind for r in recs}
        self.assertTrue(kinds <= RECOMMENDATION_KINDS, f"unexpected kinds: {kinds}")
        self.assertLessEqual(len(recs), 7)
        # behavioural kinds derived from the profile are present
        for expected in ("calculator", "verification", "tax_health",
                         "notice_followup", "document_followup", "learning_topic"):
            self.assertIn(expected, kinds)
        for rec in recs:
            self.assertTrue(rec.dict())

    def test_limit_is_respected(self):
        recs = build_recommendations(_personalized_profile(), [], [], limit=3)
        self.assertEqual(len(recs), 3)
        # highest priority first
        priorities = [r.priority for r in recs]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_dismissed_ids_are_filtered(self):
        recs = build_recommendations(
            _personalized_profile(), [], ["verification:filer", "tax_health:check"], limit=5
        )
        ids = [r.id for r in recs]
        self.assertNotIn("verification:filer", ids)
        self.assertNotIn("tax_health:check", ids)
        self.assertTrue(ids)

    def test_deadline_cap_keeps_behavioural_recs_visible(self):
        events = [
            _FakeEvent(f"ev-{i}", f"Deadline {i}", "2026-01-31", -3) for i in range(12)
        ]
        recs = build_recommendations(_personalized_profile(), events, [], limit=5)
        kinds = [r.kind for r in recs]
        self.assertEqual(len(recs), 5)
        self.assertLessEqual(kinds.count("deadline"), 3)
        self.assertTrue(any(kind != "deadline" for kind in kinds), kinds)

    def test_zero_limit(self):
        self.assertEqual(build_recommendations(_personalized_profile(), [], [], limit=0), [])


# =============================================================================
# Feedback, privacy export and deletion
# =============================================================================

class TestFeedbackAndPrivacy(LearningStoreTestCase):
    """Feedback is stored, exported, and wiped on delete."""

    def test_feedback_export_and_delete(self):
        self.store.record_interaction(
            self.user_a,
            query="calculate salary tax on 1200000 for tax year 2025",
            domain="income_tax",
            tools=["calculate"],
            signals=extract_signals("calculate salary tax on 1200000 for tax year 2025"),
        )
        self.store.record_feedback(
            self.user_a, message_id="msg-1", rating=1, comment="Very helpful"
        )
        self.store.record_feedback(
            self.user_a, message_id="msg-2", rating=-1, comment="wrong number"
        )

        data = self.store.export_user_data(self.user_a)
        self.assertEqual(len(data["feedback"]), 2)
        by_message = {fb["message_id"]: fb for fb in data["feedback"]}
        self.assertEqual(by_message["msg-1"]["rating"], 1)
        self.assertEqual(by_message["msg-1"]["comment"], "Very helpful")
        self.assertEqual(by_message["msg-2"]["rating"], -1)
        self.assertEqual(len(data["interactions"]), 1)

        deleted = self.store.delete_user_data(self.user_a)
        self.assertGreater(deleted, 0)
        self.assertIsNone(self.store.get_profile(self.user_a))
        self.assertEqual(self.store.export_user_data(self.user_a)["feedback"], [])
        self.assertEqual(self.store.export_user_data(self.user_a)["interactions"], [])


# =============================================================================
# Assistant hot-path helpers
# =============================================================================

def _prompt_context() -> dict:
    return {
        "top_domains": [["income_tax", 3.0], ["sales_tax", 1.0]],
        "entity_type": "salaried",
        "tax_year": 2025,
        "language": "en",
        "total_interactions": 7,
        "recommendations": [
            {
                "id": "calculator:salary_tax",
                "kind": "calculator",
                "title": "Estimate your salary income tax",
                "body": "Run the salary tax calculator for a quick estimate.",
                "action_label": "Open salary tax calculator",
                "action_path": "/calculator/salary-tax",
                "priority": 58,
                "source": "profile",
            }
        ],
    }


class TestLearningContextHelper(unittest.TestCase):
    """`_learning_context` / `_learning_snapshot` response contract."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(_remove_temp_tree, self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        import app.learning.store as store_module

        self._store_module = store_module
        self._saved_store = store_module._store
        self.addCleanup(self._restore_store)
        store_module._store = None

    def _restore_store(self):
        self._store_module._store = self._saved_store

    def _seeded_store(self, uid: str = "ctx-user") -> LearningStore:
        store = LearningStore(db_path=os.path.join(self._tmp.name, "learning.db"))
        store.record_interaction(
            uid,
            query="calculate salary tax on 1200000 for tax year 2025",
            domain="income_tax",
            tools=["calculate"],
            signals=extract_signals("calculate salary tax on 1200000 for tax year 2025"),
        )
        return store

    def test_no_user_means_empty(self):
        self.assertEqual(_learning_context(None), EMPTY_PERSONALIZATION)
        self.assertEqual(_learning_context(""), EMPTY_PERSONALIZATION)

    def test_seeded_profile_contract(self):
        store = self._seeded_store()
        with mock.patch("app.routers.assistant.get_learning_store", return_value=store):
            context = _learning_context("ctx-user")

        self.assertEqual(set(context), {"enabled", "recommendations", "profile_summary"})
        self.assertTrue(context["enabled"])
        self.assertIsInstance(context["recommendations"], list)
        summary = context["profile_summary"]
        self.assertEqual(set(summary), {"top_domains", "total_interactions"})
        self.assertEqual(summary["total_interactions"], 1)
        self.assertEqual(summary["top_domains"][0][0], "income_tax")

    def test_snapshot_raises_never_fails(self):
        broken = mock.Mock()
        broken.get_profile.side_effect = RuntimeError("db exploded")
        broken.get_recommendations.side_effect = RuntimeError("db exploded")
        with mock.patch("app.routers.assistant.get_learning_store", return_value=broken):
            self.assertEqual(_learning_context("ctx-user"), EMPTY_PERSONALIZATION)
            payload, prompt_context = _learning_snapshot("ctx-user")
        self.assertEqual(payload, EMPTY_PERSONALIZATION)
        self.assertIsNone(prompt_context)

    def test_snapshot_reads_store_at_most_twice(self):
        store = self._seeded_store()
        with mock.patch.object(store, "get_profile", wraps=store.get_profile) as spy_profile, \
                mock.patch.object(store, "get_recommendations", wraps=store.get_recommendations) as spy_recs, \
                mock.patch("app.routers.assistant.get_learning_store", return_value=store):
            _learning_snapshot("ctx-user")
        self.assertEqual(spy_profile.call_count, 1)
        self.assertEqual(spy_recs.call_count, 1)

    def test_personalization_block_contents(self):
        block = _personalization_block(_prompt_context())
        self.assertIn("USER CONTEXT (learned from this account's own past questions", block)
        self.assertIn("Frequently asks about: income_tax (3.0)", block)
        self.assertIn("Taxpayer type: salaried", block)
        self.assertIn("Tax year: 2025", block)
        self.assertIn("Language preference: en", block)
        self.assertIn("Interactions so far: 7", block)
        self.assertIn("PERSONALIZED SUGGESTIONS TO MENTION BRIEFLY", block)
        self.assertIn("Estimate your salary income tax", block)
        self.assertIn("HARD RULE", block)

    def test_personalization_block_is_empty_without_context(self):
        self.assertEqual(_personalization_block(None), "")
        self.assertEqual(_personalization_block({}), "")

    def test_personalization_block_tolerates_garbage(self):
        # Malformed values must degrade, never raise out of the request path.
        for junk in (
            {"top_domains": "not-a-list", "recommendations": ["not-a-dict"]},
            {"top_domains": [("only-one-item",)], "recommendations": [None]},
            {"entity_type": object(), "tax_year": [], "language": {}},
        ):
            self.assertIsInstance(_personalization_block(junk), str)

        # A well-formed context still renders with partially empty values.
        block = _personalization_block({"total_interactions": 3})
        self.assertIn("USER CONTEXT", block)
        self.assertIn("Taxpayer type: unknown", block)
        self.assertIn("Interactions so far: 3", block)

    def test_final_answer_injects_block(self):
        captured = {}

        def fake_generate(question, prompt, language=None):
            captured["prompt"] = prompt
            return "STUBBED ANSWER"

        with mock.patch("app.llm.generate_answer", side_effect=fake_generate):
            answer = _final_answer(
                "calculate my salary tax", [], "FBR CONTEXT", user_context=_prompt_context()
            )
        self.assertEqual(answer, "STUBBED ANSWER")
        self.assertIn("USER CONTEXT", captured["prompt"])
        self.assertIn("Estimate your salary income tax", captured["prompt"])

    def test_final_answer_without_context_has_no_block(self):
        captured = {}

        def fake_generate(question, prompt, language=None):
            captured["prompt"] = prompt
            return "STUBBED ANSWER"

        with mock.patch("app.llm.generate_answer", side_effect=fake_generate):
            _final_answer("calculate my salary tax", [], "FBR CONTEXT")
        self.assertNotIn("USER CONTEXT", captured["prompt"])

    def test_final_answer_stream_injects_block(self):
        captured = {}

        def fake_stream(question, prompt, language=None):
            captured["prompt"] = prompt
            yield "chunk-1"
            yield "chunk-2"

        with mock.patch("app.llm.generate_answer_stream", side_effect=fake_stream):
            chunks = list(
                _final_answer_stream(
                    "calculate my salary tax", [], "FBR CONTEXT",
                    user_context=_prompt_context(),
                )
            )
        self.assertEqual(chunks, ["chunk-1", "chunk-2"])
        self.assertIn("USER CONTEXT", captured["prompt"])


class TestRecordInteractionHelper(LearningStoreTestCase):
    """Interaction recording after the answer: domain and tools."""

    def test_records_primary_domain_tools_and_signals(self):
        self._patch_store()
        _record_interaction(
            self.user_a,
            "calculate salary tax on 1200000 for tax year 2025",
            ["calculate", "verification"],
            {"primary_domain": "income_tax_salary"},
        )
        profile = self.store.get_profile(self.user_a)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.top_domains[0][0], "income_tax_salary")
        self.assertEqual(sorted(profile.frequent_tools), ["calculate", "verification"])
        self.assertEqual(profile.tax_year, 2025)
        self.assertEqual(profile.entity_type, "salaried")

    def test_falls_back_to_first_planned_tool_as_domain(self):
        self._patch_store()
        _record_interaction(self.user_a, "sales tax on 500000", ["calculate"], {})
        profile = self.store.get_profile(self.user_a)
        self.assertEqual(profile.top_domains[0][0], "calculate")

    def test_no_user_is_a_noop_and_failures_are_swallowed(self):
        with mock.patch("app.routers.assistant.get_learning_store") as spy:
            _record_interaction(None, "q", ["calculate"], {})
        spy.assert_not_called()

        with mock.patch(
            "app.routers.assistant.get_learning_store",
            side_effect=RuntimeError("store exploded"),
        ):
            # Must not raise into the request path.
            _record_interaction(self.user_a, "q", ["calculate"], {})
        self.assertEqual(self._count_rows(self.user_a), 0)

    def _patch_store(self):
        patcher = mock.patch(
            "app.routers.assistant.get_learning_store", return_value=self.store
        )
        patcher.start()
        self.addCleanup(patcher.stop)


# =============================================================================
# API: POST /assistant/ask personalization contract
# =============================================================================

RAG_STUB = {
    "answer": "",
    "sources": [{"title": "Income Tax Ordinance 2001", "section": "12"}],
    "verification": {"passed": True, "checks": {}, "failed_checks": []},
    "grounded": True,
    "primary_domain": "income_tax_salary",
}

DETERMINISTIC_QUERY = {"query": "calculate salary tax on 1200000"}


class TestAssistantAskPersonalizationApi(unittest.TestCase):
    """POST /assistant/ask under FBR_AUTH_REQUIRED=false.

    The RAG/LLM path is stubbed (offline determinism); what is asserted is
    the learning contract: the `personalization` object shape and the
    no-crash behaviour when the learning store is unavailable.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(_remove_temp_tree, cls._tmp.name)
        cls.addClassCleanup(cls._tmp.cleanup)

        import app.learning.store as store_module

        cls._store_module = store_module
        cls._saved_store = store_module._store
        cls._saved_env = {k: os.environ.get(k) for k in ("FBR_LEARNING_DB", "FBR_AUTH_REQUIRED")}

        # Isolated learning DB + dev auth, set BEFORE importing app.api.
        os.environ["FBR_LEARNING_DB"] = os.path.join(cls._tmp.name, "learning.db")
        os.environ["FBR_AUTH_REQUIRED"] = "false"
        store_module._store = None

        import app.api

        cls.api_module = app.api
        cls.client = TestClient(app.api.app)

    @classmethod
    def tearDownClass(cls):
        cls.api_module.app.dependency_overrides.pop(require_user, None)
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._store_module._store = cls._saved_store

    def _post(self, payload: dict):
        with mock.patch(
            "app.routers.assistant._rag_ground", return_value=(RAG_STUB, "FBR CONTEXT")
        ), mock.patch("app.llm.generate_answer", return_value="STUBBED ANSWER"):
            return self.client.post("/assistant/ask", json=payload)

    def test_ask_returns_personalization_contract(self):
        resp = self._post(DETERMINISTIC_QUERY)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        personalization = body["personalization"]
        self.assertEqual(
            set(personalization), {"enabled", "recommendations", "profile_summary"}
        )
        # FBR_AUTH_REQUIRED=false -> no caller id -> learning is skipped.
        self.assertFalse(personalization["enabled"])
        self.assertEqual(personalization["recommendations"], [])
        self.assertIsNone(personalization["profile_summary"])
        self.assertIn("calculate", [t["tool"] for t in body["tools_used"]])

    def test_ask_with_caller_records_interaction(self):
        self.api_module.app.dependency_overrides[require_user] = lambda: {
            "id": "api-user-1"
        }
        try:
            first = self._post(DETERMINISTIC_QUERY)
            self.assertEqual(first.status_code, 200)
            first_personalization = first.json()["personalization"]
            self.assertEqual(
                set(first_personalization),
                {"enabled", "recommendations", "profile_summary"},
            )
            self.assertTrue(first_personalization["enabled"])
            # First ask: nothing learned yet, so no profile summary.
            self.assertIsNone(first_personalization["profile_summary"])

            # The first answer records one interaction; each later ask sees
            # the interactions answered before it (the snapshot is taken
            # before the answer is generated).
            second = self._post(DETERMINISTIC_QUERY)
            self.assertEqual(second.status_code, 200)
            personalization = second.json()["personalization"]
            self.assertTrue(personalization["enabled"])
            self.assertEqual(personalization["profile_summary"]["total_interactions"], 1)
            self.assertEqual(
                personalization["profile_summary"]["top_domains"][0][0],
                "income_tax_salary",
            )
            self.assertTrue(personalization["recommendations"])

            third = self._post(DETERMINISTIC_QUERY)
            self.assertEqual(
                third.json()["personalization"]["profile_summary"]["total_interactions"], 2
            )
        finally:
            self.api_module.app.dependency_overrides.pop(require_user, None)

    def test_ask_survives_unavailable_learning_store(self):
        # An existing FILE in place of the DB directory makes the store
        # unopenable: personalization must degrade, never fail the answer.
        blocker = os.path.join(self._tmp.name, "not-a-directory")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")

        self.api_module.app.dependency_overrides[require_user] = lambda: {
            "id": "api-user-broken-store"
        }
        saved_db = os.environ.get("FBR_LEARNING_DB")
        os.environ["FBR_LEARNING_DB"] = os.path.join(blocker, "learning.db")
        self._store_module._store = None
        try:
            resp = self._post(DETERMINISTIC_QUERY)
            self.assertEqual(resp.status_code, 200)
            personalization = resp.json()["personalization"]
            self.assertEqual(personalization, EMPTY_PERSONALIZATION)
        finally:
            if saved_db is None:
                os.environ.pop("FBR_LEARNING_DB", None)
            else:
                os.environ["FBR_LEARNING_DB"] = saved_db
            self._store_module._store = None
            self.api_module.app.dependency_overrides.pop(require_user, None)


if __name__ == "__main__":
    unittest.main()
