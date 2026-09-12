"""
Verification API - Production-Grade
===================================

Unified API for all verification operations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.verification_center.ntn_verifier import (
    NTNVerifier, NTNStatus, get_ntn_verifier,
)
from app.verification_center.filer_status import (
    FilerStatusChecker, FilerStatus, get_filer_status_checker,
)
from app.verification_center.business_verifier import (
    BusinessVerifier, RegistrationType, get_business_verifier,
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
    """Unified API for all verifications."""

    def __init__(self):
        self.ntn_verifier = get_ntn_verifier()
        self.filer_checker = get_filer_status_checker()
        self.business_verifier = get_business_verifier()

    def verify_ntn(self, ntn: str) -> VerificationResponse:
        """Verify NTN."""
        result = self.ntn_verifier.verify(ntn)
        return VerificationResponse(
            request_type=VerificationType.NTN,
            value=ntn,
            is_verified=result.is_valid,
            confidence=0.95,
            message=f"NTN {ntn}: {result.status.value}",
            details={
                "status": result.status.value,
                "name": result.name,
                "business_type": result.business_type,
                "tax_payer_type": result.tax_payer_type,
                "filer_status": result.filer_status,
                "last_return": result.last_return_filed,
            },
        )

    def verify_filer_status(self, ntn: str) -> VerificationResponse:
        """Verify filer status."""
        info = self.filer_checker.check_by_ntn(ntn)
        return VerificationResponse(
            request_type=VerificationType.FILER,
            value=ntn,
            is_verified=info.is_active_filer,
            confidence=0.95,
            message=f"Filer Status: {info.status.value}",
            details={
                "status": info.status.value,
                "is_active_filer": info.is_active_filer,
                "last_return": info.last_return_filed,
                "years_filing": info.years_of_filing,
                "is_atl": info.is_atl,
            },
        )

    def verify_vendor(self, vendor_ntn: str) -> VerificationResponse:
        """Verify vendor before onboarding or paying."""
        vendor = self.business_verifier.verify_vendor(vendor_ntn)
        warnings_text = "; ".join(vendor.warnings) if vendor.warnings else "None"

        return VerificationResponse(
            request_type=VerificationType.VENDOR,
            value=vendor_ntn,
            is_verified=vendor.is_registered and vendor.is_active and not vendor.is_blacklisted,
            confidence=0.90,
            message=f"Vendor: {vendor.vendor_name or vendor_ntn}",
            details={
                "is_registered": vendor.is_registered,
                "is_active": vendor.is_active,
                "is_filer": vendor.is_filer,
                "is_blacklisted": vendor.is_blacklisted,
                "risk_score": vendor.risk_score,
                "warnings": vendor.warnings,
                "warning_summary": warnings_text,
                "wht_rate_applicable": "15%" if vendor.is_filer else "30%",
            },
        )

    def verify_cnic(self, cnic: str) -> VerificationResponse:
        """Verify CNIC."""
        info = self.filer_checker.check_by_cnic(cnic)
        return VerificationResponse(
            request_type=VerificationType.CNIC,
            value=cnic,
            is_verified=info.status != FilerStatus.UNKNOWN,
            confidence=0.90,
            message=f"CNIC: {info.status.value}",
            details={
                "status": info.status.value,
                "is_active_filer": info.is_active_filer,
                "last_return": info.last_return_filed,
            },
        )

    def verify_business(self, registration_number: str, reg_type: str = "ntn") -> VerificationResponse:
        """Verify business registration."""
        try:
            rtype = RegistrationType(reg_type)
        except ValueError:
            rtype = RegistrationType.NTN

        if rtype == RegistrationType.NTN:
            result = self.business_verifier.verify_ntn(registration_number)
        elif rtype == RegistrationType.SECP_COMPANY:
            result = self.business_verifier.verify_secp(registration_number)
        elif rtype == RegistrationType.PRA_REGISTRATION:
            result = self.business_verifier.verify_pra(registration_number)
        else:
            return VerificationResponse(
                request_type=VerificationType.BUSINESS,
                value=registration_number,
                is_verified=False,
                message=f"Unsupported registration type: {reg_type}",
            )

        return VerificationResponse(
            request_type=VerificationType.BUSINESS,
            value=registration_number,
            is_verified=result.verified and result.is_active,
            confidence=0.95,
            message=f"Business Registration: {result.status}",
            details={
                "registration_number": result.registration_number,
                "registration_type": result.registration_type.value,
                "business_name": result.business_name,
                "registration_date": result.registration_date,
                "is_active": result.is_active,
                "status": result.status,
                "verification_source": result.verification_source,
            },
        )

    def batch_verify(
        self,
        requests: list[VerificationRequest],
    ) -> list[VerificationResponse]:
        """Verify multiple items at once."""
        responses = []
        for req in requests:
            if req.type == VerificationType.NTN:
                resp = self.verify_ntn(req.value)
            elif req.type == VerificationType.FILER:
                resp = self.verify_filer_status(req.value)
            elif req.type == VerificationType.VENDOR:
                resp = self.verify_vendor(req.value)
            elif req.type == VerificationType.CNIC:
                resp = self.verify_cnic(req.value)
            elif req.type == VerificationType.BUSINESS:
                resp = self.verify_business(req.value)
            else:
                resp = VerificationResponse(
                    request_type=req.type,
                    value=req.value,
                    is_verified=False,
                    message="Unknown verification type",
                )
            responses.append(resp)
        return responses


# Singleton
_api: Optional[VerificationAPI] = None


def get_verification_api() -> VerificationAPI:
    """Get singleton verification API."""
    global _api
    if _api is None:
        _api = VerificationAPI()
    return _api
