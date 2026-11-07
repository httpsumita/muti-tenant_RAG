import unittest
from unittest.mock import Mock, patch

import requests
from google.api_core.exceptions import PermissionDenied

import firebase_auth
from firebase_auth import (
    FirebaseAccountExistsError,
    FirebaseAuthError,
    FirebaseSession,
    InvalidFirebaseTokenError,
    VerifiedIdentity,
    authenticate_with_password,
    resolve_principal,
    resolve_principals,
    sign_in_with_password,
    sign_in_with_password_session,
    refresh_firebase_session,
    verify_identity_token,
)


class FirebaseSignInTests(unittest.TestCase):
    @patch("firebase_auth.requests.post")
    def test_sign_in_sends_credentials_over_https_and_returns_id_token(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "idToken": "synthetic-token",
            "refreshToken": "synthetic-refresh-token",
        }
        post.return_value = response

        token = sign_in_with_password("user@example.test", "synthetic-password", "web-api-key")

        self.assertEqual(token, "synthetic-token")
        self.assertTrue(post.call_args.args[0].startswith("https://"))
        self.assertEqual(post.call_args.kwargs["json"]["password"], "synthetic-password")
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    @patch("firebase_auth.requests.post")
    def test_sign_in_session_returns_refresh_token(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "idToken": "synthetic-token",
            "refreshToken": "synthetic-refresh-token",
        }
        post.return_value = response

        session = sign_in_with_password_session(
            "user@example.test", "synthetic-password", "web-api-key"
        )

        self.assertEqual(
            session,
            FirebaseSession("synthetic-token", "synthetic-refresh-token"),
        )

    @patch("firebase_auth.requests.post")
    def test_sign_in_rejects_bad_credentials_with_generic_error(self, post: Mock) -> None:
        post.return_value = Mock(status_code=400)

        with self.assertRaisesRegex(FirebaseAuthError, "Check your email and password"):
            sign_in_with_password("user@example.test", "wrong-password", "web-api-key")

    @patch("firebase_auth.requests.post", side_effect=requests.Timeout)
    def test_sign_in_reports_connectivity_errors(self, _post: Mock) -> None:
        with self.assertRaisesRegex(FirebaseAuthError, "Could not reach Firebase"):
            sign_in_with_password("user@example.test", "synthetic-password", "web-api-key")

    def test_sign_in_rejects_empty_credentials_without_request(self) -> None:
        with patch("firebase_auth.requests.post") as post:
            with self.assertRaisesRegex(FirebaseAuthError, "Enter both"):
                sign_in_with_password("", "synthetic-password", "web-api-key")
        post.assert_not_called()

    @patch("firebase_auth.requests.post")
    def test_sign_up_sends_credentials_and_returns_token_and_uid(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "idToken": "synthetic-token",
            "refreshToken": "synthetic-refresh-token",
            "localId": "synthetic-user",
        }
        post.return_value = response

        token, uid = firebase_auth.sign_up_with_password(
            "new-user@example.test", "synthetic-password", "web-api-key"
        )

        self.assertEqual((token, uid), ("synthetic-token", "synthetic-user"))
        self.assertTrue(post.call_args.args[0].endswith("accounts:signUp"))
        self.assertEqual(post.call_args.kwargs["json"]["email"], "new-user@example.test")
        self.assertEqual(post.call_args.kwargs["json"]["returnSecureToken"], True)

    @patch("firebase_auth.requests.post", side_effect=requests.Timeout)
    def test_sign_up_reports_connectivity_errors(self, _post: Mock) -> None:
        with self.assertRaisesRegex(FirebaseAuthError, "Could not reach Firebase"):
            firebase_auth.sign_up_with_password(
                "new-user@example.test", "synthetic-password", "web-api-key"
            )

    @patch("firebase_auth.requests.post")
    def test_refresh_rotates_session_tokens(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "id_token": "fresh-id-token",
            "refresh_token": "rotated-refresh-token",
        }
        post.return_value = response

        session = refresh_firebase_session("stored-refresh-token", "web-api-key")

        self.assertEqual(
            session,
            FirebaseSession("fresh-id-token", "rotated-refresh-token"),
        )
        self.assertTrue(post.call_args.args[0].startswith("https://securetoken.googleapis.com/"))
        self.assertEqual(
            post.call_args.kwargs["data"]["refresh_token"], "stored-refresh-token"
        )

    @patch("firebase_auth.requests.post")
    def test_refresh_rejects_revoked_token(self, post: Mock) -> None:
        response = Mock(status_code=400)
        response.json.return_value = {"error": {"message": "INVALID_REFRESH_TOKEN"}}
        post.return_value = response

        with self.assertRaises(InvalidFirebaseTokenError):
            refresh_firebase_session("revoked-refresh-token", "web-api-key")

    @patch("firebase_auth.requests.post")
    def test_sign_up_reports_existing_email_for_tenant_recovery(self, post: Mock) -> None:
        response = Mock(status_code=400)
        response.json.return_value = {"error": {"message": "EMAIL_EXISTS"}}
        post.return_value = response

        with self.assertRaisesRegex(FirebaseAccountExistsError, "already has an account"):
            firebase_auth.sign_up_with_password(
                "existing@example.test", "synthetic-password", "web-api-key"
            )

    @patch("firebase_auth.requests.post")
    def test_sign_up_maps_firebase_password_and_provider_errors(self, post: Mock) -> None:
        cases = (
            ("WEAK_PASSWORD : Password should be at least 8 characters", "password policy"),
            ("OPERATION_NOT_ALLOWED", "Email/password signup is disabled"),
        )
        for firebase_error, user_message in cases:
            with self.subTest(firebase_error=firebase_error):
                response = Mock(status_code=400)
                response.json.return_value = {"error": {"message": firebase_error}}
                post.return_value = response

                with self.assertRaisesRegex(FirebaseAuthError, user_message):
                    firebase_auth.sign_up_with_password(
                        "new@example.test", "synthetic-password", "web-api-key"
                    )

    @patch("firebase_auth.resolve_principals")
    @patch("firebase_auth.sign_in_with_password", return_value="synthetic-token")
    def test_authentication_verifies_and_loads_signed_in_users_memberships(
        self, sign_in: Mock, resolve: Mock
    ) -> None:
        principals = (Mock(), Mock())
        resolve.return_value = principals
        db = Mock()

        token, actual_principals = authenticate_with_password(
            "user@example.test", "synthetic-password", "web-api-key", "synthetic-project", db
        )

        self.assertEqual(token, "synthetic-token")
        self.assertIs(actual_principals, principals)
        sign_in.assert_called_once_with(
            "user@example.test", "synthetic-password", "web-api-key"
        )
        resolve.assert_called_once_with("synthetic-token", "synthetic-project", db)

    @patch("firebase_auth.resolve_principals")
    @patch("firebase_auth.sign_in_with_password", side_effect=FirebaseAuthError("Sign-in failed."))
    def test_failed_sign_in_never_resolves_membership(
        self, _sign_in: Mock, resolve: Mock
    ) -> None:
        with self.assertRaises(FirebaseAuthError):
            authenticate_with_password(
                "user@example.test", "wrong-password", "web-api-key", "synthetic-project", Mock()
            )

        resolve.assert_not_called()


class FirebaseTokenVerificationTests(unittest.TestCase):
    @patch("firebase_auth.auth.verify_id_token")
    @patch("firebase_auth._get_admin_app", return_value=object())
    def test_verifies_token_and_returns_identity(self, _get_app: Mock, verify: Mock) -> None:
        verify.return_value = {"uid": "synthetic-user", "email": "user@example.test"}

        identity = verify_identity_token("synthetic-token", "synthetic-project")

        self.assertEqual(
            identity,
            VerifiedIdentity(uid="synthetic-user", email="user@example.test"),
        )
        self.assertTrue(verify.call_args.kwargs["check_revoked"])

    @patch("firebase_auth.auth.verify_id_token", side_effect=firebase_auth.auth.InvalidIdTokenError("bad"))
    @patch("firebase_auth._get_admin_app", return_value=object())
    def test_rejects_invalid_token(self, _get_app: Mock, _verify: Mock) -> None:
        with self.assertRaises(InvalidFirebaseTokenError):
            verify_identity_token("invalid-token", "synthetic-project")

    @patch("firebase_auth.auth.verify_id_token", return_value={"email": "user@example.test"})
    @patch("firebase_auth._get_admin_app", return_value=object())
    def test_rejects_verified_token_without_user_id(self, _get_app: Mock, _verify: Mock) -> None:
        with self.assertRaises(InvalidFirebaseTokenError):
            verify_identity_token("synthetic-token", "synthetic-project")


class TrustedMembershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = VerifiedIdentity(uid="synthetic-user", email="user@example.test")
        self.db = Mock()
        self.membership_collection = (
            self.db.collection.return_value.document.return_value.collection.return_value
        )

    def set_memberships(self, *memberships: tuple[str, dict]) -> None:
        self.membership_collection.stream.return_value = [
            FakeMembershipSnapshot(tenant_id, data) for tenant_id, data in memberships
        ]

    def resolve(self):
        with patch("firebase_auth.verify_identity_token", return_value=self.identity) as verify:
            principal = resolve_principal("synthetic-token", "synthetic-project", self.db)
        verify.assert_called_once_with("synthetic-token", "synthetic-project")
        return principal

    def test_builds_principal_from_membership_document_for_verified_uid(self) -> None:
        self.set_memberships(
            (
                "tenant-synthetic",
                {"tenant_id": "tenant-synthetic", "roles": ["reader", "editor"], "active": True},
            )
        )

        principal = self.resolve()

        self.assertEqual(principal.user_id, "synthetic-user")
        self.assertEqual(principal.tenant_id, "tenant-synthetic")
        self.assertEqual(principal.roles, frozenset({"reader", "editor"}))
        self.db.collection.assert_called_once_with("memberships")
        self.db.collection.return_value.document.assert_called_once_with("synthetic-user")
        self.db.collection.return_value.document.return_value.collection.assert_called_once_with(
            "tenants"
        )

    def test_lists_only_active_valid_tenant_memberships(self) -> None:
        self.set_memberships(
            ("tenant-b", {"tenant_id": "tenant-b", "roles": ["reader"], "active": True}),
            ("tenant-a", {"tenant_id": "tenant-a", "roles": ["admin"], "active": True}),
            ("tenant-inactive", {"tenant_id": "tenant-inactive", "roles": ["reader"], "active": False}),
            ("tenant-mismatch", {"tenant_id": "another-tenant", "roles": ["reader"], "active": True}),
        )

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            principals = resolve_principals("synthetic-token", "synthetic-project", self.db)

        self.assertEqual([principal.tenant_id for principal in principals], ["tenant-a", "tenant-b"])

    def test_selects_requested_tenant_from_verified_memberships(self) -> None:
        self.set_memberships(
            ("tenant-a", {"tenant_id": "tenant-a", "roles": ["reader"], "active": True}),
            ("tenant-b", {"tenant_id": "tenant-b", "roles": ["admin"], "active": True}),
        )

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            principal = resolve_principal(
                "synthetic-token", "synthetic-project", self.db, tenant_id="tenant-b"
            )

        self.assertEqual(principal.tenant_id, "tenant-b")
        self.assertEqual(principal.roles, frozenset({"admin"}))

    def test_requires_selection_when_user_has_multiple_tenants(self) -> None:
        self.set_memberships(
            ("tenant-a", {"tenant_id": "tenant-a", "roles": ["reader"], "active": True}),
            ("tenant-b", {"tenant_id": "tenant-b", "roles": ["admin"], "active": True}),
        )

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            with self.assertRaisesRegex(FirebaseAuthError, "Select one"):
                resolve_principal("synthetic-token", "synthetic-project", self.db)

    def test_denies_missing_membership(self) -> None:
        self.set_memberships()

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            with self.assertRaisesRegex(FirebaseAuthError, "not assigned"):
                resolve_principal("synthetic-token", "synthetic-project", self.db)

    def test_denies_inactive_membership(self) -> None:
        self.set_memberships(
            ("tenant-synthetic", {"tenant_id": "tenant-synthetic", "roles": ["reader"], "active": False})
        )

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            with self.assertRaisesRegex(FirebaseAuthError, "not assigned to an active tenant"):
                resolve_principal("synthetic-token", "synthetic-project", self.db)

    def test_denies_missing_or_empty_roles(self) -> None:
        for roles in (None, []):
            with self.subTest(roles=roles):
                self.set_memberships(
                    ("tenant-synthetic", {"tenant_id": "tenant-synthetic", "roles": roles, "active": True})
                )

                with patch("firebase_auth.verify_identity_token", return_value=self.identity):
                    with self.assertRaises(FirebaseAuthError):
                        resolve_principal("synthetic-token", "synthetic-project", self.db)

    def test_invalid_token_never_reads_membership(self) -> None:
        with patch(
            "firebase_auth.verify_identity_token",
            side_effect=InvalidFirebaseTokenError("invalid token"),
        ):
            with self.assertRaises(InvalidFirebaseTokenError):
                resolve_principal("invalid-token", "synthetic-project", self.db)

        self.db.collection.assert_not_called()

    def test_reports_firestore_membership_permission_failure(self) -> None:
        self.membership_collection.stream.side_effect = PermissionDenied(
            "synthetic permission denial"
        )

        with patch("firebase_auth.verify_identity_token", return_value=self.identity):
            with self.assertRaisesRegex(FirebaseAuthError, "ADC account has permission"):
                resolve_principal("synthetic-token", "synthetic-project", self.db)


class FakeMembershipSnapshot:
    def __init__(self, tenant_id: str, data: dict) -> None:
        self.id = tenant_id
        self._data = data

    def to_dict(self) -> dict:
        return self._data


if __name__ == "__main__":
    unittest.main()
