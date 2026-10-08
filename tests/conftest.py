"""Pytest configuration.

test_production_suite.py is a standalone verification script (it boots live
servers and calls sys.exit() at import-time scope), not a pytest module.
Collecting it crashes pytest with INTERNALERROR (SystemExit during import).
Keep it runnable directly via `python tests/test_production_suite.py`.
"""

collect_ignore = ["test_production_suite.py"]
