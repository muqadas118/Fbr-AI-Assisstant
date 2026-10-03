"""
Verification API - Production-Grade
===================================

Unified API for all verification operations.

TRUTH CONTRACT (see app/common/unavailable.py and .env.example):

  This API never fabricates taxpayer data. When no official
  verification source is configured (FBR_VERIFICATION_MODE=off, the
  default), every verify_* method returns an explicit Unavailable
  result: is_verified=False, confidence=0.0, no taxpayer name,
  no registration dates, no filing history. Simulated lookup
  classes remain importable for future backed modes but are NOT
  consulted in the default configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.common.unavailable import verification_unavailable
from app.verification_center.ntn_verifier import get_ntn_verifier
from app.verification_center.filer_status import get_filer_status_checker
from app.verification_center.business_verifier import (
    RegistrationType, get_business_verifier,
)


class VerificationType(str, Enum):
    """Types of verification."""
    NTN = "ntn"
    FILER = "filer"
    VENDOR = "vendor"
    CNIC = "cnic"
    BUSINESS = "business"


@dataclass
class VerificationRequest:
    """Verification request."""
    type: VerificationType
    value: str  # NTN, CNIC, etc.
    purpose: str = "general"  # general, vendor_onboarding, invoice_wht


@dataclass
class VerificationResponse:
    """Verification response."""
    request_type: VerificationType
    value: str
    is_verified: bool
    confidence: float = 0.0
    message: str = ""
    details: dict = field(default_factory=dict)


class VerificationAPI:
    """Unified API for all verifications (honest-unavailable by default)."""

    def __init__(self):
        # Kept for backed modes (atl/iris); never consulted when mode=off.
        self.ntn_verifier = get_ntn_verifier()
        self.filer_checker = get_filer_status_checker()
        self.business_verifier = get_business_verifier()

    # ------------------------------------------------------------
    # Honest unavailable result
    # ------------------------------------------------------------

    def _unavailable(
        self, rtype: VerificationType, value: str
    ) -> VerificationResponse:
        payload = verification_unavailable(rtype.value, value)
        return VerificationResponse(
            request_type=rtype,
            value=value,
            is_verified=payload["is_verified"],
            confidence=payload["confidence"],
            message=payload["message"],
            details=payload["details"],
        )

    def verify_ntn(self, ntn: str) -> VerificationResponse:
        """Verify NTN against the configured official source."""
        return self._unavailable(VerificationType.NTN, ntn)

    def verify_filer_status(self, ntn: str) -> VerificationResponse:
        """Check filer status against the configured official source."""
        return self._unavailable(VerificationType.FILER, ntn)

    def verify_vendor(self, vendor_ntn: str) -> VerificationResponse:
        """Verify a vendor against the configured official source."""
        return self._unavailable(VerificationType.VENDOR, vendor_ntn)

    def verify_cnic(self, cnic: str) -> VerificationResponse:
        """Verify a CNIC against the configured official source."""
        return self._unavailable(VerificationType.CNIC, cnic)

    def verify_business(
        self, registration_number: str, reg_type: str = "ntn"
    ) -> VerificationResponse:
        """Verify business registration against the configured source."""
        try:
            rtype = RegistrationType(reg_type)
        except ValueError:
            rtype = RegistrationType.NTN

        if rtype not in (
            RegistrationType.NTN,
            RegistrationType.SECP_COMPANY,
            RegistrationType.PRA_REGISTRATION,
        ):
            return VerificationResponse(
                request_type=VerificationType.BUSINESS,
                value=registration_number,
                is_verified=False,
                message=f"Unsupported registration type: {reg_type}",
            )

        return self._unavailable(VerificationType.BUSINESS, registration_number)

    def batch_verify(
        self,
        requests: list[VerificationRequest],
    ) -> list[VerificationResponse]:
        """Verify multiple items at once."""
        handlers = {
            VerificationType.NTN: self.verify_ntn,
            VerificationType.FILER: self.verify_filer_status,
            VerificationType.VENDOR: self.verify_vendor,
            VerificationType.CNIC: self.verify_cnic,
        }
        responses = []
        for req in requests:
            handler = handlers.get(req.type)
            if handler is not None:
                responses.append(handler(req.value))
            elif req.type == VerificationType.BUSINESS:
                responses.append(self.verify_business(req.value))
            else:
                responses.append(
                    VerificationResponse(
                        request_type=req.type,
                        value=req.value,
                        is_verified=False,
                        message="Unknown verification type",
                    )
                )
        return responses


# Singleton
_api: Optional[VerificationAPI] = None


def get_verification_api() -> VerificationAPI:
    """Get singleton verification API."""
    global _api
    if _api is None:
        _api = VerificationAPI()
    return _api
