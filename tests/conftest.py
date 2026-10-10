"""Pytest configuration.

test_production_suite.py used to execute at import time and call sys.exit(),
which crashed collection with INTERNALERROR (SystemExit during import). It now
registers one pytest item per production check (and stays runnable standalone
via `python tests/test_production_suite.py`), so it is collected normally.

Quota hermeticity
-----------------
The daily-quota feature (``app/quotas.py``) meters every assistant message and
chat upload against a SQLite store. Without isolation the test suite reads and
writes the developer's real ``data/usage.db`` and inherits whatever
``FBR_DAILY_*_LIMIT`` the environment happens to set, so a suite that uploads
more than the daily limit in one process-day fails non-deterministically
(e.g. tests/test_uploads.py uploads 9+ files as one account against the
default limit of 5).

The autouse fixture below makes every test hermetic:

* ``FBR_QUOTA_DB`` points at a per-test temporary file (``tmp_path``), so the
  real ``data/usage.db`` is never created or modified.
* ``FBR_DAILY_MESSAGE_LIMIT`` / ``FBR_DAILY_UPLOAD_LIMIT`` are raised high so
  unrelated suites are never throttled. We deliberately do NOT set
  ``FBR_QUOTA_ENABLED=0``: quotas stay enabled, so the router enforcement code
  path (``consume_message`` / ``consume_upload`` -> 429) is still exercised.
* ``app.quotas._store`` (the process-wide cached singleton) is reset, because
  ``QuotaStore.__init__`` snapshots ``FBR_QUOTA_DB`` at construction time; limits
  are read from env at call time, but the DB path is not. Clearing the cache
  before and after each test guarantees this test's temporary DB is the one
  used, and that no store bound to a to-be-deleted temp file survives.

``tests/test_quotas.py`` is unaffected: it builds its own ``QuotaStore`` with an
explicit ``db_path`` and overrides limits via its own ``mock.patch.dict``, which
takes precedence over these env values for the duration of each test.
"""

import pytest

import app.quotas as _quotas

# A limit no realistic test run can reach in a single process-day.
_HIGH_QUOTA_LIMIT = "1000000"


@pytest.fixture(autouse=True)
def _isolate_quota_store(tmp_path, monkeypatch):
    """Redirect the quota store to a temp DB with non-throttling limits.

    ``monkeypatch`` restores the environment automatically; ``_store`` is reset
    manually (before the test so the temp DB wins, after the test so no store
    survives pointing at the deleted temp file).
    """
    monkeypatch.setenv("FBR_QUOTA_DB", str(tmp_path / "usage.db"))
    monkeypatch.setenv("FBR_DAILY_MESSAGE_LIMIT", _HIGH_QUOTA_LIMIT)
    monkeypatch.setenv("FBR_DAILY_UPLOAD_LIMIT", _HIGH_QUOTA_LIMIT)

    # QuotaStore snapshots FBR_QUOTA_DB at construction; drop the cached
    # singleton so get_quota_store() rebuilds it against the temp path.
    _quotas._store = None
    try:
        yield
    finally:
        _quotas._store = None
