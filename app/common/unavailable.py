"""
Honest "unavailable" results for the Verification Center.

Contract (documented in .env.example and PROGRESS.md):

  The verification endpoints must NEVER return a generated taxpayer
  name, registration date, filing history, or filer status. When no
  official verification source is configured (FBR_VERIFICATION_MODE
  is "off", the default), every endpoint returns an explicit
  unavailable result with is_verified=False and confidence=0.0.

Backed modes (opt-in via .env):
  off   - no lookup, always Unavailable          (default, always safe)
  atl   - FBR public Active Taxpayer List        (filer status only,
          no taxpayer name)                      [not yet implemented]
  iris  - FBR IRIS/PRAL API, requires FBR_API_KEY [not yet implemented]
"""

from __future__ import annotations

import os
import re
from typing import Optional


def verification_mode() -> str:
    """Return the configured FBR verification source mode (lowercased)."""
    return (os.getenv("FBR_VERIFICATION_MODE") or "off").strip().lower()


# Format-level checks (no external data — deterministic, always honest).
_FORMAT_CHECKS: dict[str, tuple[str, re.Pattern[str]]] = {
    "ntn": ("NTN (7 or 9 digits)", re.compile(r"^\d{7}$|^\d{9}$")),
    "cnic": ("CNIC (13 digits, e.g. 35202-1234567-1)", re.compile(r"^\d{5}-?\d{7}-?\d$")),
    "filer": ("NTN (7 or 9 digits)", re.compile(r"^\d{7}$|^\d{9}$")),
    "vendor": ("NTN (7 or 9 digits)", re.compile(r"^\d{7}$|^\d{9}$")),
    "business": ("registration number (7-13 chars)", re.compile(r"^[A-Za-z0-9-]{5,20}$")),
}


def _format_check(request_type: str, value: str) -> dict:
    """Return a deterministic format-validity assessment for the value."""
    entry = _FORMAT_CHECKS.get(request_type)
    if entry is None:
        return {"format_valid": None, "format_expected": "unknown type"}
    label, pattern = entry
    valid = bool(pattern.match((value or "").strip()))
    return {
        "format_valid": valid,
        "format_expected": label,
        "format_note": (
            "Format is structurally valid — official status still requires "
            "an FBR lookup (not wired in this build)."
            if valid
            else "Format is INVALID — check the value before retrying; no "
            "lookup was attempted."
        ),
    }


def verification_unavailable(request_type: str, value: str) -> dict:
    """Build the deterministic unavailable response for any request type.

    Returned shape matches app.routers.verify.VerificationResponse so
    routers can wrap it directly.
    """
    mode = verification_mode()
    if mode in ("atl", "iris"):
        reason = (
            f"FBR_VERIFICATION_MODE={mode} is configured but no official "
            "lookup backend is wired in this build."
        )
    else:
        reason = (
            "No official verification source configured "
            "(FBR_VERIFICATION_MODE=off)."
        )
    fmt = _format_check(request_type, value)
    clean = "yes" if fmt.get("format_valid") else "no"
    return {
        "request_type": request_type,
        "value": value,
        "is_verified": False,
        "confidence": 0.0,
        "message": (
            f"Verification unavailable for '{value}': {reason} "
            f"Format check: {clean}. "
            "No taxpayer data is shown because none was verified."
        ),
        "details": {
            "status": "unavailable",
            "verification_source": "unavailable",
            "configured_mode": mode,
            "reason": reason,
            "taxpayer_name": None,
            **fmt,
        },
    }
