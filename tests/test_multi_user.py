"""
Test Suite for Multi-User Foundation
====================================
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.multi_user import (
    UserRole, AuthManager, hash_password, verify_password,
    TeamManager,
)


class TestUserModels(unittest.TestCase):
    """Test user models."""

    def setUp(self):
        from app.multi_user.models import UserManager
        # Isolated temp store — the default store now persists to disk
        # (data/auth_users.json) and must not be touched by tests.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.um = UserManager(store_path=Path(self._tmp.name) / "auth_users.json")
        self.addCleanup(self.um.users.clear)

    def test_create_user(self):
        user = self.um.create_user(
            email="test@example.com",
            name="Test User",
            password_hash="hash123",
            ntn="1234567-8",
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.role, UserRole.ACCOUNTANT)

    def test_get_user_by_email(self):
        self.um.create_user(
            email="user@example.com",
            name="Test",
            password_hash="hash",
        )
        user = self.um.get_user_by_email("user@example.com")
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "Test")

    def test_update_user(self):
        user = self.um.create_user(
            email="u@example.com",
            name="Old Name",
            password_hash="hash",
        )
        updated = self.um.update_user(user.id, name="New Name")
        self.assertEqual(updated.name, "New Name")

    def test_delete_user(self):
        user = self.um.create_user(
            email="del@example.com",
            name="Delete Me",
            password_hash="hash",
        )
        success = self.um.delete_user(user.id)
        self.assertTrue(success)
        self.assertFalse(self.um.get_user(user.id).is_active)

    def test_record_login(self):
        user = self.um.create_user(
            email="login@example.com",
            name="Login Test",
            password_hash="hash",
        )
        self.um.record_login(user.id)
        self.assertIsNotNone(user.last_login_at)

    def test_profile_and_settings(self):
        user = self.um.create_user(
            email="profile@example.com",
            name="Profile Test",
            password_hash="hash",
        )
        self.um.update_profile(user.id, bio="Test bio", city="Karachi")
        profile = self.um.get_profile(user.id)
        self.assertEqual(profile.bio, "Test bio")
        self.assertEqual(profile.city, "Karachi")

        self.um.update_settings(user.id, theme="dark", timezone="UTC")
        settings = self.um.get_settings(user.id)
        self.assertEqual(settings.theme, "dark")

    def test_list_users(self):
        self.um.create_user("a@e.com", "A", "h", role=UserRole.ADMIN)
        self.um.create_user("b@e.com", "B", "h", role=UserRole.ACCOUNTANT)
        self.um.create_user("c@e.com", "C", "h", role=UserRole.VIEWER)

        all_users = self.um.list_users()
        self.assertEqual(len(all_users), 3)

        admins = self.um.list_users(role=UserRole.ADMIN)
        self.assertEqual(len(admins), 1)

    def test_statistics(self):
        self.um.create_user("s1@e.com", "S1", "h")
        self.um.create_user("s2@e.com", "S2", "h")
        stats = self.um.get_statistics()
        self.assertEqual(stats["total_users"], 2)
        self.assertEqual(stats["active_users"], 2)


class TestAuthManager(unittest.TestCase):
    """Test authentication manager."""

    def setUp(self):
        self.auth = AuthManager()

    def test_hash_and_verify_password(self):
        pwd = "SecurePass123!"
        hashed = hash_password(pwd)
        self.assertNotEqual(pwd, hashed)
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_create_session(self):
        session = self.auth.create_session(
            user_id="user1",
            ip_address="192.168.1.1",
        )
        self.assertIsNotNone(session.token)
        self.assertEqual(session.user_id, "user1")

    def test_validate_token(self):
        session = self.auth.create_session(user_id="user1")
        validated = self.auth.validate_token(session.token)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.user_id, "user1")

    def test_invalid_token(self):
        result = self.auth.validate_token("invalid_token")
        self.assertIsNone(result)

    def test_revoke_session(self):
        session = self.auth.create_session(user_id="user1")
        success = self.auth.revoke_session(session.id)
        self.assertTrue(success)
        # Revoked session should not validate
        self.assertIsNone(self.auth.validate_token(session.token))

    def test_revoke_all_sessions(self):
        self.auth.create_session(user_id="u1")
        self.auth.create_session(user_id="u1")
        count = self.auth.revoke_all_sessions("u1")
        self.assertEqual(count, 2)

    def test_api_key(self):
        api_key, plain = self.auth.create_api_key(
            user_id="user1",
            name="Test Key",
            scopes=["read", "write"],
        )
        self.assertIsNotNone(plain)
        validated = self.auth.validate_api_key(plain)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.name, "Test Key")

    def test_api_key_revoke(self):
        api_key, plain = self.auth.create_api_key(user_id="u1", name="K1")
        success = self.auth.revoke_api_key(api_key.id)
        self.assertTrue(success)
        self.assertIsNone(self.auth.validate_api_key(plain))


class TestTeamManager(unittest.TestCase):
    """Test team manager."""

    def setUp(self):
        # Isolated temp store — TeamManager now persists to disk
        # (data/auth_teams.json) and must not be touched by tests.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tm = TeamManager(store_path=Path(self._tmp.name) / "auth_teams.json")

    def test_create_team(self):
        team = self.tm.create_team(
            owner_id="owner1",
            name="Acme Corp",
            organization_type="Private Ltd",
            ntn="1234567-8",
        )
        self.assertIsNotNone(team.id)
        self.assertEqual(team.name, "Acme Corp")
        self.assertEqual(team.member_count, 1)

    def test_add_member(self):
        team = self.tm.create_team(owner_id="o1", name="Team A")
        member = self.tm.add_member(team.id, "user2", UserRole.ACCOUNTANT, "o1")
        self.assertEqual(member.role, UserRole.ACCOUNTANT)
        self.assertEqual(team.member_count, 2)

    def test_remove_member(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        self.tm.add_member(team.id, "u1", UserRole.ACCOUNTANT, "o1")
        success = self.tm.remove_member(team.id, "u1")
        self.assertTrue(success)
        self.assertEqual(team.member_count, 1)

    def test_cannot_remove_owner(self):
        team = self.tm.create_team(owner_id="owner1", name="T1")
        with self.assertRaises(ValueError):
            self.tm.remove_member(team.id, "owner1")

    def test_update_member_role(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        self.tm.add_member(team.id, "u1", UserRole.VIEWER, "o1")
        member = self.tm.update_member_role(team.id, "u1", UserRole.MANAGER)
        self.assertEqual(member.role, UserRole.MANAGER)

    def test_invitation_flow(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        inv = self.tm.invite_to_team(
            team_id=team.id,
            email="new@example.com",
            role=UserRole.ACCOUNTANT,
            invited_by="o1",
        )
        self.assertEqual(inv.status.value, "pending")
        # The accepting identity must be the invited address.
        success = self.tm.accept_invitation(
            inv.id, "new_user_id", "New@Example.com"
        )
        self.assertTrue(success)

    def test_accept_invitation_wrong_email(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        inv = self.tm.invite_to_team(
            team_id=team.id,
            email="invited@example.com",
            role=UserRole.ACCOUNTANT,
            invited_by="o1",
        )
        with self.assertRaises(ValueError):
            self.tm.accept_invitation(inv.id, "attacker_id", "attacker@example.com")
        # A failed email check must not have joined the team.
        self.assertIsNone(self.tm.get_member(team.id, "attacker_id"))

    def test_invite_requires_manage_permission(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        self.tm.add_member(team.id, "viewer1", UserRole.VIEWER, "o1")
        with self.assertRaises(PermissionError):
            self.tm.invite_to_team(
                team.id, "x@example.com", UserRole.VIEWER, "viewer1"
            )
        with self.assertRaises(ValueError):
            self.tm.invite_to_team(
                "no-such-team", "x@example.com", UserRole.VIEWER, "o1"
            )

    def test_decline_invitation(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        inv = self.tm.invite_to_team(team.id, "dec@example.com", UserRole.VIEWER, "o1")
        success = self.tm.decline_invitation(inv.id)
        self.assertTrue(success)
        self.assertEqual(self.tm.invitations[inv.id].status.value, "declined")

    def test_check_permission(self):
        team = self.tm.create_team(owner_id="o1", name="T1")
        self.tm.add_member(team.id, "u1", UserRole.VIEWER, "o1")

        self.assertTrue(self.tm.check_permission("o1", team.id, "manage_team"))
        self.assertTrue(self.tm.check_permission("o1", team.id, "file_returns"))
        self.assertFalse(self.tm.check_permission("u1", team.id, "manage_team"))
        self.assertTrue(self.tm.check_permission("u1", team.id, "view_reports"))

    def test_user_teams(self):
        self.tm.create_team(owner_id="u1", name="T1")
        self.tm.create_team(owner_id="u1", name="T2")
        teams = self.tm.get_user_teams("u1")
        self.assertEqual(len(teams), 2)


class TestMultiUserAPI(unittest.TestCase):
    """Test multi-user API."""

    def setUp(self):
        # Fresh instances
        from app.multi_user.models import UserManager
        from app.multi_user.auth import AuthManager
        from app.multi_user.team import TeamManager
        from app.multi_user.api import MultiUserAPI
        self.api = MultiUserAPI()
        # Reset singletons with isolated temp stores (JSON persistence must
        # never hit the real data/auth_users.json from tests).
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.api.users = UserManager(store_path=Path(self._tmp.name) / "auth_users.json")
        self.api.auth = AuthManager()
        self.api.teams = TeamManager(store_path=Path(self._tmp.name) / "auth_teams.json")

    def test_register_user(self):
        user = self.api.register_user(
            email="new@example.com",
            password="Password123!",
            name="New User",
        )
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.role, UserRole.ACCOUNTANT)

    def test_login_success(self):
        self.api.register_user("login@example.com", "Pass123!", "Login Test")
        result = self.api.login("login@example.com", "Pass123!")
        self.assertIsNotNone(result)
        self.assertIn("session", result)

    def test_login_wrong_password(self):
        self.api.register_user("lp@example.com", "Pass123!", "LP")
        result = self.api.login("lp@example.com", "wrongpassword")
        self.assertIsNone(result)

    def test_change_password(self):
        user = self.api.register_user("cp@example.com", "OldPass1!", "CP")
        success = self.api.change_password(user.id, "OldPass1!", "NewPass2!")
        self.assertTrue(success)
        # Old password should no longer work
        result = self.api.login("cp@example.com", "OldPass1!")
        self.assertIsNone(result)
        # New password should work
        result = self.api.login("cp@example.com", "NewPass2!")
        self.assertIsNotNone(result)

    def test_profile_and_settings_update(self):
        user = self.api.register_user("ps@example.com", "Pass1!", "PS")
        self.api.update_profile(user.id, bio="Tax consultant", city="Lahore")
        self.api.update_settings(user.id, theme="dark", language="ur")
        result = self.api.get_user_profile(user.id)
        self.assertEqual(result["profile"]["bio"], "Tax consultant")
        self.assertEqual(result["settings"]["theme"], "dark")

    def test_team_creation_and_invitation(self):
        user = self.api.register_user("team@example.com", "Pass1!", "Team Lead")
        team = self.api.create_team(
            owner_id=user.id,
            name="My Accounting Firm",
            organization_type="Partnership",
            ntn="9876543-2",
        )
        self.assertEqual(team.name, "My Accounting Firm")
        inv = self.api.invite_user_to_team(
            team_id=team.id,
            email="colleague@example.com",
            role=UserRole.ACCOUNTANT,
            invited_by=user.id,
        )
        self.assertEqual(inv.email, "colleague@example.com")

    def test_team_dashboard(self):
        user = self.api.register_user("td@example.com", "Pass1!", "TD")
        team = self.api.create_team(owner_id=user.id, name="Dashboard Team")
        dashboard = self.api.get_team_dashboard(team.id)
        self.assertEqual(dashboard["team"]["name"], "Dashboard Team")
        self.assertEqual(dashboard["member_count"], 1)

    def test_user_dashboard(self):
        user = self.api.register_user("ud@example.com", "Pass1!", "UD")
        self.api.create_team(owner_id=user.id, name="Team 1")
        self.api.create_team(owner_id=user.id, name="Team 2")
        dashboard = self.api.get_user_dashboard(user.id)
        self.assertEqual(dashboard["team_count"], 2)
        self.assertEqual(len(dashboard["teams"]), 2)

    def test_statistics(self):
        self.api.register_user("s1@example.com", "Pass1!", "S1")
        self.api.register_user("s2@example.com", "Pass1!", "S2")
        stats = self.api.get_statistics()
        self.assertEqual(stats["users"]["total_users"], 2)


class TestHasPermission(unittest.TestCase):
    """Test permission checking."""

    def test_role_permissions(self):
        from app.multi_user.team import has_permission
        self.assertTrue(has_permission(UserRole.ADMIN, "manage_team"))
        self.assertTrue(has_permission(UserRole.ADMIN, "file_returns"))
        self.assertTrue(has_permission(UserRole.ACCOUNTANT, "file_returns"))
        self.assertFalse(has_permission(UserRole.ACCOUNTANT, "manage_team"))
        self.assertTrue(has_permission(UserRole.VIEWER, "view_reports"))
        self.assertFalse(has_permission(UserRole.VIEWER, "file_returns"))
        self.assertFalse(has_permission(UserRole.GUEST, "view_reports"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
