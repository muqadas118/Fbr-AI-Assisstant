"""
Verification Center - Production-Grade
======================================

Verify all things FBR-related:
- NTN verification (check if NTN is valid/active)
- CNIC verification
- STRN (Sales Tax Registration Number) verification
- Filer status verification (filer vs non-filer)
- Taxpayer status (active, blocked, suspended)
- Business registration verification
- Property verification
- Vehicle verification
- Vendor verification
- Blacklist checks
- Active taxpayers list (ATL) check
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
