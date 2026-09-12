"""
NTN Verifier - Production-Grade
=================================

Verify NTN (National Tax Number) from FBR.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class NTNStatus(str, Enum):
    """NTN status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    INVALID_FORMAT = "invalid_format"


@dataclass
class NTNVerificationResult:
    """Result of NTN verification."""
    ntn: str
    status: NTNStatus
    is_valid: bool
    name: Optional[str] = None
    business_type: Optional[str] = None
    registration_date: Optional[str] = None
    last_return_filed: Optional[str] = None
    filing_status: Optional[str] = None
    tax_payer_type: Optional[str] = None  # Individual, Company, AOP, etc.
    filer_status: Optional[str] = None  # Filer / Non-Filer
    ntbr_status: Optional[str] = None  # NTN Taxpayer Blacklist Register
    verification_source: str = "simulated"
    error: Optional[str] = None


class NTNVerifier:
    """
    Verifies NTN from FBR records.

    In production, this would call FBR's IRIS API or web service.
    For now, it simulates verification.
    """

    # Common Pakistani business types
    BUSINESS_TYPES = [
        "Sole Proprietorship",
        "Partnership",
        "Private Limited Company",
        "Public Limited Company",
        "AOP (Association of Persons)",
        "Trust",
        "NGO",
        "Branch Office (Foreign)",
    ]

    def __init__(self):
        self._cache = {}  # In-memory cache for demo

    def verify(self, ntn: str) -> NTNVerificationResult:
        """
        Verify NTN against FBR records.
        """
        ntn_clean = ntn.replace("-", "").strip()

        # Validate format
        if not ntn_clean.isdigit() or len(ntn_clean) not in (7, 8):
            return NTNVerificationResult(
                ntn=ntn,
                status=NTNStatus.INVALID_FORMAT,
                is_valid=False,
                error="NTN must be 7-8 digits",
            )

        # Check cache
        if ntn_clean in self._cache:
            return self._cache[ntn_clean]

        # Simulate verification
        # In production: call FBR API
        result = self._simulate_verification(ntn_clean)
        self._cache[ntn_clean] = result
        return result

    def _simulate_verification(self, ntn_clean: str) -> NTNVerificationResult:
        """
        Simulate FBR verification for development.

        Real implementation would call:
        - FBR IRIS API
        - FBR web services
        - Third-party data providers
        """
        # Use last digit as deterministic "random"
        last_digit = int(ntn_clean[-1]) if ntn_clean[-1].isdigit() else 0

        # Deterministic simulation based on NTN
        if last_digit == 0:
            status = NTNStatus.ACTIVE
            is_valid = True
        elif last_digit in (1, 2):
            status = NTNStatus.ACTIVE
            is_valid = True
        elif last_digit == 3:
            status = NTNStatus.SUSPENDED
            is_valid = False
        elif last_digit == 4:
            status = NTNStatus.BLOCKED
            is_valid = False
        elif last_digit == 5:
            status = NTNStatus.INACTIVE
            is_valid = False
        else:
            status = NTNStatus.ACTIVE
            is_valid = True

        return NTNVerificationResult(
            ntn=ntn_clean,
            status=status,
            is_valid=is_valid,
            name=self._generate_name(ntn_clean),
            business_type=self.BUSINESS_TYPES[last_digit % len(self.BUSINESS_TYPES)],
            registration_date="2018-06-15",
            last_return_filed="2024-09-28",
            filing_status="Filed",
            tax_payer_type=self._get_taxpayer_type(ntn_clean),
            filer_status="Filer" if last_digit != 9 else "Non-Filer",
            ntbr_status="Clean",
            verification_source="simulated_fbr",
        )

    def _generate_name(self, ntn: str) -> str:
        """Generate deterministic name for demo."""
        names = [
            "ABC Corporation (Pvt) Ltd",
            "XYZ Industries Ltd",
            "Global Services Co",
            "Al-Meezan Enterprises",
            "Premier Trading Co",
            "Modern Tech Solutions",
            "Renaissance Group",
            "Atlas Holdings",
        ]
        idx = sum(int(d) for d in ntn if d.isdigit()) % len(names)
        return names[idx]

    def _get_taxpayer_type(self, ntn: str) -> str:
        """Determine taxpayer type from NTN format."""
        # First digit often indicates type in some systems
        first = int(ntn[0]) if ntn[0].isdigit() else 0
        types = ["Individual", "Sole Prop", "Company", "AOP", "Partnership"]
        return types[first % len(types)]

    def bulk_verify(self, ntns: list[str]) -> list[NTNVerificationResult]:
        """Verify multiple NTNs at once."""
        return [self.verify(ntn) for ntn in ntns]


# Singleton
_verifier: Optional[NTNVerifier] = None


def get_ntn_verifier() -> NTNVerifier:
    """Get singleton NTN verifier."""
    global _verifier
    if _verifier is None:
        _verifier = NTNVerifier()
    return _verifier
