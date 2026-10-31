import unittest
from unittest.mock import Mock, patch

import requests

import firebase_auth
from firebase_auth import (
    FirebaseAuthError,
    InvalidFirebaseTokenError,
    VerifiedIdentity,
    sign_in_with_password,
    verify_identity_token,
)


class FirebaseSignInTests(unittest.TestCase):
    @patch("firebase_auth.requests.post")
    def test_sign_in_sends_credentials_over_https_and_returns_id_token(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"idToken": "synthetic-token"}
        post.return_value = response

        token = sign_in_with_password("user@example.test", "synthetic-password", "web-api-key")

        self.assertEqual(token, "synthetic-token")
        self.assertTrue(post.call_args.args[0].startswith("https://"))
        self.assertEqual(post.call_args.kwargs["json"]["password"], "synthetic-password")
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

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


if __name__ == "__main__":
    unittest.main()
