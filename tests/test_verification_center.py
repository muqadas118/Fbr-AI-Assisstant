"""
Test Suite for Verification Center
===================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.verification_center import (
    NTNVerifier, NTNStatus, FilerStatusChecker, FilerStatus, BusinessVerifier, RegistrationType, get_verification_api,
    VerificationRequest,
)


class TestNTNVerifier(unittest.TestCase):
    """Test NTN verifier."""

    def setUp(self):
        self.verifier = NTNVerifier()

    def test_valid_format(self):
        # Contract (app/common/unavailable.py): 7 or 9 digits.
        result = self.verifier.verify("123456-7")
        self.assertIn(result.status, [
            NTNStatus.ACTIVE, NTNStatus.SUSPENDED,
            NTNStatus.BLOCKED, NTNStatus.INACTIVE,
        ])

    def test_invalid_format(self):
        result = self.verifier.verify("invalid")
        self.assertEqual(result.status, NTNStatus.INVALID_FORMAT)
        self.assertFalse(result.is_valid)

    def test_short_ntn(self):
        result = self.verifier.verify("12345")
        self.assertEqual(result.status, NTNStatus.INVALID_FORMAT)

    def test_eight_digit_ntn_rejected(self):
        # 8-digit NTNs are not part of the documented contract.
        result = self.verifier.verify("1234567-8")
        self.assertEqual(result.status, NTNStatus.INVALID_FORMAT)
        self.assertFalse(result.is_valid)

    def test_active_ntn(self):
        # Use NTN ending in 1 (ACTIVE per simulation)
        result = self.verifier.verify("123456-1")
        self.assertEqual(result.status, NTNStatus.ACTIVE)
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.name)

    def test_suspended_ntn(self):
        result = self.verifier.verify("123456-3")
        self.assertEqual(result.status, NTNStatus.SUSPENDED)
        self.assertFalse(result.is_valid)

    def test_caching(self):
        result1 = self.verifier.verify("123456-8")
        result2 = self.verifier.verify("123456-8")
        # Should be same instance due to cache
        self.assertIs(result1, result2)

    def test_bulk_verify(self):
        results = self.verifier.bulk_verify(["123456-1", "123456-2", "123456-3"])
        self.assertEqual(len(results), 3)


class TestFilerStatusChecker(unittest.TestCase):
    """Test filer status checker."""

    def setUp(self):
        self.checker = FilerStatusChecker()

    def test_filer_status(self):
        info = self.checker.check_by_ntn("1234567-1")
        self.assertEqual(info.status, FilerStatus.FILER)
        self.assertTrue(info.is_active_filer)

    def test_non_filer_status(self):
        info = self.checker.check_by_ntn("1234567-5")
        self.assertEqual(info.status, FilerStatus.NON_FILER)
        self.assertFalse(info.is_active_filer)

    def test_late_filer(self):
        info = self.checker.check_by_ntn("1234567-3")
        self.assertEqual(info.status, FilerStatus.LATE_FILER)

    def test_atl_status(self):
        info = self.checker.check_by_ntn("1234567-1")
        self.assertTrue(info.is_atl)

    def test_check_by_cnic(self):
        # A CNIC is never resolved to a fabricated NTN/filing history.
        info = self.checker.check_by_cnic("12345-1234567-1")
        self.assertEqual(info.status, FilerStatus.UNKNOWN)
        self.assertEqual(info.ntn, "")

    def test_invalid_cnic(self):
        info = self.checker.check_by_cnic("12345")
        self.assertEqual(info.status, FilerStatus.UNKNOWN)


class TestBusinessVerifier(unittest.TestCase):
    """Test business verifier."""

    def setUp(self):
        self.verifier = BusinessVerifier()

    def test_verify_ntn(self):
        reg = self.verifier.verify_ntn("1234567-8")
        self.assertEqual(reg.registration_type, RegistrationType.NTN)
        self.assertTrue(reg.is_active)

    def test_verify_secp(self):
        reg = self.verifier.verify_secp("0123456")
        self.assertEqual(reg.registration_type, RegistrationType.SECP_COMPANY)
        self.assertTrue(reg.verified)

    def test_verify_vendor_active(self):
        vendor = self.verifier.verify_vendor("1234567-1")
        self.assertTrue(vendor.is_active)
        self.assertTrue(vendor.is_filer)
        self.assertEqual(vendor.risk_score, 0.0)

    def test_verify_vendor_blacklisted(self):
        # NTN ending in 9 = blacklisted
        vendor = self.verifier.verify_vendor("1234567-9")
        self.assertTrue(vendor.is_blacklisted)
        self.assertGreater(vendor.risk_score, 50)

    def test_verify_vendor_non_filer(self):
        # NTN ending in 5 = non-filer
        vendor = self.verifier.verify_vendor("1234567-5")
        self.assertFalse(vendor.is_registered)


class TestVerificationAPI(unittest.TestCase):
    """Test verification API truth contract.

    With no official verification source configured
    (FBR_VERIFICATION_MODE=off, the default), the API must return an
    explicit Unavailable result and NEVER a generated taxpayer name,
    status, or filing history.
    """

    def setUp(self):
        self.api = get_verification_api()

    def _assert_unavailable(self, resp, expected_type: str):
        self.assertEqual(resp.request_type.value, expected_type)
        self.assertFalse(resp.is_verified)
        self.assertEqual(resp.confidence, 0.0)
        self.assertEqual(resp.details.get("status"), "unavailable")
        self.assertEqual(resp.details.get("verification_source"), "unavailable")
        self.assertIsNone(resp.details.get("taxpayer_name"))

    def test_verify_ntn_unavailable(self):
        resp = self.api.verify_ntn("1234567-1")
        self._assert_unavailable(resp, "ntn")
        # Fabricated fields must not appear.
        self.assertNotIn("name", resp.details)
        self.assertNotIn("business_type", resp.details)
        self.assertNotIn("filer_status", resp.details)
        self.assertNotIn("last_return", resp.details)

    def test_verify_filer_status_unavailable(self):
        resp = self.api.verify_filer_status("1234567-1")
        self._assert_unavailable(resp, "filer")
        self.assertNotIn("is_active_filer", resp.details)
        self.assertNotIn("is_atl", resp.details)

    def test_verify_vendor_unavailable(self):
        resp = self.api.verify_vendor("1234567-1")
        self._assert_unavailable(resp, "vendor")
        self.assertNotIn("wht_rate_applicable", resp.details)
        self.assertNotIn("is_blacklisted", resp.details)

    def test_verify_cnic_unavailable(self):
        resp = self.api.verify_cnic("12345-1234567-1")
        self._assert_unavailable(resp, "cnic")

    def test_verify_business_unavailable(self):
        resp = self.api.verify_business("1234567-1", reg_type="ntn")
        self._assert_unavailable(resp, "business")
        self.assertNotIn("business_name", resp.details)
        self.assertNotIn("registration_date", resp.details)

    def test_batch_verify_all_unavailable(self):
        requests = [
            VerificationRequest(
                type="ntn",
                value="1234567-1",
            ),
            VerificationRequest(
                type="filer",
                value="1234567-1",
            ),
            VerificationRequest(
                type="vendor",
                value="1234567-5",
            ),
        ]
        responses = self.api.batch_verify(requests)
        self.assertEqual(len(responses), 3)
        for resp in responses:
            self.assertFalse(resp.is_verified)
            self.assertEqual(resp.details.get("status"), "unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
