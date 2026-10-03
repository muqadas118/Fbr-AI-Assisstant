"""
Verification Center Router
==========================

FastAPI router for FBR entity verification operations.
Exposes VerificationAPI as HTTP endpoints.
"""

import logging
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.verification_center import VerificationAPI, get_verification_api

logger = logging.getLogger("fbr_api.verify")

router = APIRouter(prefix="/verify", tags=["Verification Center"])


# =============================================================================
# Enums
# =============================================================================

class VerificationTypeEnum(str, Enum):
    NTN = "ntn"
    FILER = "filer"
    VENDOR = "vendor"
    CNIC = "cnic"
    BUSINESS = "business"


class BusinessRegType(str, Enum):
    NTN = "ntn"
    SECP_COMPANY = "secp_company"
    PRA_REGISTRATION = "pra_registration"


# =============================================================================
# Request Models
# =============================================================================

class VerifyNTNRequest(BaseModel):
    """Verify NTN request."""
    ntn: str = Field(..., min_length=1, description="NTN number")


class VerifyFilerRequest(BaseModel):
    """Verify filer status request."""
    ntn: str = Field(..., min_length=1, description="NTN number")


class VerifyVendorRequest(BaseModel):
    """Verify vendor request."""
    vendor_ntn: str = Field(..., min_length=1, description="Vendor NTN")


class VerifyCNICRequest(BaseModel):
    """Verify CNIC request."""
    cnic: str = Field(..., min_length=1, description="CNIC number (without dashes)")


class VerifyBusinessRequest(BaseModel):
    """Verify business registration request."""
    registration_number: str = Field(..., min_length=1)
    reg_type: BusinessRegType = Field(default=BusinessRegType.NTN)


class BatchVerifyRequest(BaseModel):
    """Batch verification request."""
    requests: list[dict] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of verification requests"
    )


# =============================================================================
# Response Models
# =============================================================================

class VerificationResponse(BaseModel):
    """Verification result."""
    request_type: str
    value: str
    is_verified: bool
    confidence: float
    message: str
    details: dict


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/ntn", response_model=VerificationResponse, dependencies=[Depends(require_user)])
async def verify_ntn(request: VerifyNTNRequest) -> VerificationResponse:
    """
    Verify a National Tax Number (NTN).

    Checks if the NTN is valid and returns taxpayer information
    including name, business type, filer status, and last return filed.
    """
    try:
        api = get_verification_api()
        result = api.verify_ntn(request.ntn)
        return VerificationResponse(
            request_type=result.request_type.value,
            value=result.value,
            is_verified=result.is_verified,
            confidence=result.confidence,
            message=result.message,
            details=result.details,
        )
    except Exception as e:
        logger.exception("Error verifying NTN")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify NTN"
        )


@router.post("/filer", response_model=VerificationResponse, dependencies=[Depends(require_user)])
async def verify_filer_status(request: VerifyFilerRequest) -> VerificationResponse:
    """
    Check filer status of a taxpayer.

    Returns whether the NTN holder is an active filer on ATL,
    last return filed year, and filing history.
    """
    try:
        api = get_verification_api()
        result = api.verify_filer_status(request.ntn)
        return VerificationResponse(
            request_type=result.request_type.value,
            value=result.value,
            is_verified=result.is_verified,
            confidence=result.confidence,
            message=result.message,
            details=result.details,
        )
    except Exception as e:
        logger.exception("Error checking filer status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check filer status"
        )


@router.post("/vendor", response_model=VerificationResponse, dependencies=[Depends(require_user)])
async def verify_vendor(request: VerifyVendorRequest) -> VerificationResponse:
    """
    Verify a vendor before onboarding or payment.

    Checks vendor registration, filer status, blacklisting,
    and provides WHT rate recommendation (15% for filers, 30% for non-filers).
    """
    try:
        api = get_verification_api()
        result = api.verify_vendor(request.vendor_ntn)
        return VerificationResponse(
            request_type=result.request_type.value,
            value=result.value,
            is_verified=result.is_verified,
            confidence=result.confidence,
            message=result.message,
            details=result.details,
        )
    except Exception as e:
        logger.exception("Error verifying vendor")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify vendor"
        )


@router.post("/cnic", response_model=VerificationResponse, dependencies=[Depends(require_user)])
async def verify_cnic(request: VerifyCNICRequest) -> VerificationResponse:
    """
    Verify a CNIC for tax purposes.

    Checks filer status and return filing history by CNIC.
    """
    try:
        api = get_verification_api()
        result = api.verify_cnic(request.cnic)
        return VerificationResponse(
            request_type=result.request_type.value,
            value=result.value,
            is_verified=result.is_verified,
            confidence=result.confidence,
            message=result.message,
            details=result.details,
        )
    except Exception as e:
        logger.exception("Error verifying CNIC")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify CNIC"
        )


@router.post("/business", response_model=VerificationResponse, dependencies=[Depends(require_user)])
async def verify_business(request: VerifyBusinessRequest) -> VerificationResponse:
    """
    Verify business registration.

    Supports NTN, SECP company registration, and PRA registration verification.
    """
    try:
        api = get_verification_api()
        result = api.verify_business(
            request.registration_number,
            request.reg_type.value,
        )
        return VerificationResponse(
            request_type=result.request_type.value,
            value=result.value,
            is_verified=result.is_verified,
            confidence=result.confidence,
            message=result.message,
            details=result.details,
        )
    except Exception as e:
        logger.exception("Error verifying business")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify business registration"
        )


@router.post("/batch", response_model=list[VerificationResponse], dependencies=[Depends(require_user)])
async def batch_verify(request: BatchVerifyRequest) -> list[VerificationResponse]:
    """
    Batch verification of multiple entities.

    Verifies up to 50 items in a single request.
    Each item should have 'type' and 'value' fields.
    """
    try:
        api = get_verification_api()

        from app.verification_center.api import VerificationRequest, VerificationType
        reqs: list[VerificationRequest] = []
        for r in request.requests:
            try:
                req_type = VerificationType(r["type"])
            except (KeyError, ValueError) as exc:
                # Unknown request type is a client error, not a server fault.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported verification type: {r.get('type')!r}. "
                           f"Expected one of: {[t.value for t in VerificationType]}",
                ) from exc
            if not isinstance(r.get("value"), str) or not r["value"].strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Each batch request needs a non-empty 'value' string.",
                )
            reqs.append(
                VerificationRequest(
                    type=req_type,
                    value=r["value"],
                    purpose=r.get("purpose", "general"),
                )
            )

        results = api.batch_verify(reqs)
        return [
            VerificationResponse(
                request_type=r.request_type.value,
                value=r.value,
                is_verified=r.is_verified,
                confidence=r.confidence,
                message=r.message,
                details=r.details,
            )
            for r in results
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in batch verification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform batch verification"
        )


@router.get("/atl/{ntn}", dependencies=[Depends(require_user)])
async def check_atl(ntn: str) -> dict:
    """
    Check if NTN is on Active Taxpayers List (ATL).

    Returns ATL status which determines WHT rates.
    """
    try:
        api = get_verification_api()
        result = api.verify_filer_status(ntn)
        return {
            "ntn": ntn,
            "on_atl": result.details.get("is_atl", False),
            "filer_status": result.details.get("status", "unknown"),
            "last_return": result.details.get("last_return", "N/A"),
        }
    except Exception as e:
        logger.exception("Error checking ATL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check ATL"
        )
