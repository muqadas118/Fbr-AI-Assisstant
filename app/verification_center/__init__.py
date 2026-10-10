"""
Verification Center - Production-Grade
======================================

Honest FBR verification surface. The public entry point is VerificationAPI
(app/verification_center/api.py): every verify_* call returns either a
format-level assessment or an explicit "unavailable" result, never a
generated taxpayer name, filing history, or filer status.

What actually exists here:
- ntn_verifier: NTN format validation (7 or 9 digits) plus a simulated
  lookup used only for local development (never wired into the API).
- filer_status: simulated filer-status rules (last-digit deterministic),
  also never wired into the API.
- business_verifier: simulated SECP/NTN/PRA and vendor checks, likewise
  never wired into the API.
- api: VerificationAPI — the only component the routers use.

NOT implemented: STRN, property, vehicle, blacklist/ATL lookups, and any
real IRIS/PRAL integration. Those need an official source configured via
FBR_VERIFICATION_MODE (see app/common/unavailable.py); until then the API
reports "unavailable" instead of inventing data.
"""

from app.verification_center.ntn_verifier import (
    NTNVerifier, NTNVerificationResult, NTNStatus,
    get_ntn_verifier,
)
from app.verification_center.filer_status import (
    FilerStatusChecker, FilerStatus, FilerInfo,
    get_filer_status_checker,
)
from app.verification_center.business_verifier import (
    BusinessVerifier, BusinessRegistration, RegistrationType,
    get_business_verifier,
)
from app.verification_center.api import (
    VerificationAPI, get_verification_api,
    VerificationRequest, VerificationResponse,
)

__all__ = [
    "NTNVerifier",
    "NTNVerificationResult",
    "NTNStatus",
    "get_ntn_verifier",
    "FilerStatusChecker",
    "FilerStatus",
    "FilerInfo",
    "get_filer_status_checker",
    "BusinessVerifier",
    "BusinessRegistration",
    "RegistrationType",
    "get_business_verifier",
    "VerificationAPI",
    "get_verification_api",
    "VerificationRequest",
    "VerificationResponse",
]
