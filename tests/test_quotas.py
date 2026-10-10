"""
Test Suite for the Daily Quota System
=====================================

Covers the per-user daily quota contract end to end:

- message limit hits exactly at N (N allowed, N+1 blocked, remaining never negative)
- uploads are independent from messages
- a limit of 0 blocks immediately; a negative limit is unlimited
- `snapshot` is read-only (never increments)
- the day rolls over at the timezone-local midnight (frozen clock)
- store failure degrades per FBR_QUOTA_FAIL_OPEN (open -> allowed, closed -> blocked)
- the last slot cannot be handed to two concurrent callers (threads)
- unparseable env limits fall back to the defaults
- `QuotaSnapshot.dict()` emits the exact frontend JSON shape
"""

import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.quotas import QuotaSnapshot, QuotaStore

# Baseline env every test starts from (limits are usually overridden).
_BASE_ENV = {
    "FBR_QUOTA_ENABLED": "1",
    "FBR_DAILY_MESSAGE_LIMIT": "10",
    "FBR_DAILY_UPLOAD_LIMIT": "5",
    "FBR_QUOTA_FAIL_OPEN": "1",
    "FBR_QUOTA_TIMEZONE": "Asia/Karachi",
    "FBR_RATE_LIMIT_DISABLED": "1",
}


def _make_store(testcase: unittest.TestCase, **env: str) -> QuotaStore:
    """QuotaStore on a throwaway SQLite file with `_BASE_ENV` + overrides."""
    tmp = tempfile.mkdtemp(prefix="fbr-quota-")
    testcase.addCleanup(_remove_temp_tree, tmp)
    patched = mock.patch.dict(os.environ, {**_BASE_ENV, **env}, clear=False)
    patched.start()
    testcase.addCleanup(patched.stop)
    return QuotaStore(db_path=os.path.join(tmp, "usage.db"))


def _remove_temp_tree(path: str) -> None:
    """Best-effort delete of a temp dir that held a live SQLite DB (Windows)."""
    import gc
    import shutil

    for _ in range(3):
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.isdir(path):
            return


class _FrozenClock:
    """Stand-in for `app.quotas._now_in_tz` that freezes (or advances) time."""

    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self, tz):
        return self.moment.astimezone(tz)


def _freeze(testcase: unittest.TestCase, moment: datetime) -> _FrozenClock:
    clock = _FrozenClock(moment)
    patched = mock.patch("app.quotas._now_in_tz", clock)
    patched.start()
    testcase.addCleanup(patched.stop)
    return clock


# 2026-10-10 12:00 in UTC; 17:00 the same day in Asia/Karachi (UTC+5).
_DAY_ONE = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
_DAY_TWO = _DAY_ONE + timedelta(days=1)


class TestMessageLimit(unittest.TestCase):
    """The message budget blocks exactly at N."""

    def test_limit_hits_exactly_at_n(self):
        store = _make_store(self, FBR_DAILY_MESSAGE_LIMIT="3")
        first = store.consume_message("u1")
        second = store.consume_message("u1")
        third = store.consume_message("u1")
        fourth = store.consume_message("u1")
        self.assertTrue(first.allowed_message)
        self.assertTrue(second.allowed_message)
        self.assertTrue(third.allowed_message)
        self.assertFalse(fourth.allowed_message)
        snap = store.snapshot("u1")
        self.assertEqual(snap.messages_used, 3)
        self.assertEqual(snap.messages_remaining, 0)
        self.assertGreaterEqual(snap.messages_remaining, 0)

    def test_remaining_never_negative_at_boundary(self):
        store = _make_store(self, FBR_DAILY_MESSAGE_LIMIT="1")
        store.consume_message("u1")
        for _ in range(3):
            snap = store.consume_message("u1")
            self.assertGreaterEqual(snap.messages_remaining, 0)
            self.assertFalse(snap.allowed_message)

    def test_zero_limit_blocks_immediately(self):
        store = _make_store(
            self, FBR_DAILY_MESSAGE_LIMIT="0", FBR_DAILY_UPLOAD_LIMIT="0"
        )
        snap = store.consume_message("u1")
        self.assertFalse(snap.allowed_message)
        self.assertEqual(snap.messages_used, 0)
        self.assertEqual(snap.messages_remaining, 0)
        self.assertFalse(store.consume_upload("u1").allowed_upload)

    def test_negative_limit_is_unlimited(self):
        store = _make_store(self, FBR_DAILY_MESSAGE_LIMIT="-1")
        for _ in range(7):
            snap = store.consume_message("u1")
            self.assertTrue(snap.allowed_message)
        self.assertEqual(store.snapshot("u1").messages_used, 7)


class TestUploadIndependence(unittest.TestCase):
    """Uploads and messages are separate budgets."""

    def test_uploads_do_not_consume_messages(self):
        store = _make_store(
            self, FBR_DAILY_MESSAGE_LIMIT="10", FBR_DAILY_UPLOAD_LIMIT="2"
        )
        self.assertTrue(store.consume_upload("u1").allowed_upload)
        self.assertTrue(store.consume_upload("u1").allowed_upload)
        self.assertFalse(store.consume_upload("u1").allowed_upload)
        snap = store.snapshot("u1")
        self.assertEqual(snap.uploads_used, 2)
        self.assertEqual(snap.messages_used, 0)
        # Messages still fully available.
        self.assertTrue(store.consume_message("u1").allowed_message)
        self.assertEqual(store.snapshot("u1").messages_used, 1)


class TestSnapshotReadOnly(unittest.TestCase):
    """snapshot() must never increment counters."""

    def test_snapshot_does_not_increment(self):
        store = _make_store(self)
        self.assertEqual(store.snapshot("u1").messages_used, 0)
        self.assertEqual(store.snapshot("u1").messages_used, 0)
        store.consume_message("u1")
        self.assertEqual(store.snapshot("u1").messages_used, 1)
        self.assertEqual(store.snapshot("u1").messages_used, 1)
        self.assertEqual(store.snapshot("u1").uploads_used, 0)


class TestDayRollover(unittest.TestCase):
    """The counter resets at timezone-local midnight (frozen clock)."""

    def test_day_rolls_over(self):
        store = _make_store(self, FBR_DAILY_MESSAGE_LIMIT="2")
        clock = _freeze(self, _DAY_ONE)
        first = store.consume_message("u1")
        self.assertTrue(first.allowed_message)
        self.assertEqual(first.date, "2026-10-10")
        store.consume_message("u1")
        self.assertFalse(store.consume_message("u1").allowed_message)
        # Cross local midnight: budget starts fresh under a new day key.
        clock.moment = _DAY_TWO
        snap = store.snapshot("u1")
        self.assertEqual(snap.date, "2026-10-11")
        self.assertEqual(snap.messages_used, 0)
        self.assertTrue(store.consume_message("u1").allowed_message)


class TestStoreFailure(unittest.TestCase):
    """A broken store degrades per FBR_QUOTA_FAIL_OPEN, never raises."""

    def _broken_store(self, **env):
        store = _make_store(self, **env)
        # Kill every connection attempt after init.
        patched = mock.patch.object(
            QuotaStore, "_connect", side_effect=RuntimeError("db gone")
        )
        patched.start()
        self.addCleanup(patched.stop)
        return store

    def test_fail_open_allows(self):
        store = self._broken_store(FBR_QUOTA_FAIL_OPEN="1")
        snap = store.consume_message("u1")
        self.assertTrue(snap.allowed_message)
        self.assertTrue(store.snapshot("u1").allowed_message)

    def test_fail_closed_blocks(self):
        store = self._broken_store(FBR_QUOTA_FAIL_OPEN="0")
        snap = store.consume_message("u1")
        self.assertFalse(snap.allowed_message)
        self.assertFalse(snap.allowed_upload)
        self.assertFalse(store.snapshot("u1").allowed_message)


class TestConcurrencyAtBoundary(unittest.TestCase):
    """Two rapid calls at the boundary cannot both take the last slot."""

    def test_last_slot_taken_once(self):
        store = _make_store(self, FBR_DAILY_MESSAGE_LIMIT="3")
        store.consume_message("u1")
        store.consume_message("u1")

        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(store.consume_message("u1"))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 2)
        allowed_count = sum(1 for s in results if s.allowed_message)
        self.assertEqual(allowed_count, 1)
        self.assertEqual(store.snapshot("u1").messages_used, 3)


class TestEnvParsing(unittest.TestCase):
    """Bad env values fall back to defaults (and log once)."""

    def test_unknown_limit_values_fall_back(self):
        store = _make_store(
            self,
            FBR_DAILY_MESSAGE_LIMIT="banana",
            FBR_DAILY_UPLOAD_LIMIT="1e9",
        )
        snap = store.snapshot("u1")
        self.assertEqual(snap.messages_limit, 10)
        self.assertEqual(snap.uploads_limit, 5)


class TestSnapshotShape(unittest.TestCase):
    """QuotaSnapshot.dict() emits the exact frontend JSON shape."""

    def test_dict_shape(self):
        store = _make_store(self)
        _freeze(self, _DAY_ONE)
        data = store.consume_message("u1").dict()
        self.assertEqual(
            set(data.keys()),
            {"enabled", "user_id", "date", "timezone", "reset_at", "messages", "uploads"},
        )
        self.assertEqual(set(data["messages"].keys()), {"used", "limit", "remaining"})
        self.assertEqual(set(data["uploads"].keys()), {"used", "limit", "remaining"})
        self.assertEqual(data["user_id"], "u1")
        self.assertEqual(data["date"], "2026-10-10")
        self.assertEqual(data["timezone"], "Asia/Karachi")
        self.assertEqual(data["reset_at"], "2026-10-11T00:00:00+05:00")
        self.assertEqual(data["messages"], {"used": 1, "limit": 10, "remaining": 9})
        self.assertEqual(data["uploads"], {"used": 0, "limit": 5, "remaining": 5})

    def test_snapshot_dataclass_fields(self):
        store = _make_store(self)
        snap = store.snapshot("u1")
        self.assertIsInstance(snap, QuotaSnapshot)
        for field in (
            "enabled", "user_id", "date", "timezone", "reset_at",
            "messages_used", "messages_limit", "messages_remaining", "allowed_message",
            "uploads_used", "uploads_limit", "uploads_remaining", "allowed_upload",
        ):
            self.assertTrue(hasattr(snap, field), field)


if __name__ == "__main__":
    unittest.main()
