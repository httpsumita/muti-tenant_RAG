from __future__ import annotations

from dataclasses import dataclass

import firebase_admin
import requests
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from google.auth.exceptions import DefaultCredentialsError


class FirebaseAuthError(Exception):
    """A safe, user-presentable Firebase Authentication error."""


class InvalidFirebaseTokenError(FirebaseAuthError):
    """The ID token is invalid, expired, or revoked and requires a new sign-in."""


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    uid: str
    email: str | None


def sign_in_with_password(email: str, password: str, api_key: str) -> str:
    """Exchange email/password for a Firebase Authentication ID token."""
    if not email.strip() or not password:
        raise FirebaseAuthError("Enter both your email and password.")
    if not api_key.strip():
        raise FirebaseAuthError("Firebase Authentication is not configured.")

    try:
        response = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": api_key},
            json={"email": email.strip(), "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise FirebaseAuthError(
            "Could not reach Firebase Authentication. Check your connection and try again."
        ) from exc

    if response.status_code >= 400:
        raise FirebaseAuthError("Sign-in failed. Check your email and password.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FirebaseAuthError("Firebase Authentication returned an invalid response.") from exc

    id_token = payload.get("idToken") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise FirebaseAuthError("Firebase Authentication returned an invalid response.")
    return id_token


def _get_admin_app(project_id: str) -> firebase_admin.App:
    try:
        app = firebase_admin.get_app()
    except ValueError:
        try:
            app = firebase_admin.initialize_app(options={"projectId": project_id})
        except DefaultCredentialsError as exc:
            raise FirebaseAuthError(
                "Firebase Admin credentials are unavailable. Configure Application Default "
                "Credentials before signing in."
            ) from exc

    if app.project_id != project_id:
        raise FirebaseAuthError(
            "The configured Firebase project does not match the Admin credentials."
        )
    return app


def verify_identity_token(id_token: str, project_id: str) -> VerifiedIdentity:
    """Verify token signature, audience, expiry, and revocation with Firebase Admin."""
    if not id_token:
        raise InvalidFirebaseTokenError("Your sign-in has expired. Please sign in again.")
    if not project_id.strip():
        raise FirebaseAuthError("Firebase project ID is not configured.")

    app = _get_admin_app(project_id)
    try:
        claims = auth.verify_id_token(id_token, app=app, check_revoked=True)
    except auth.InvalidIdTokenError as exc:
        raise InvalidFirebaseTokenError(
            "Your sign-in is invalid or expired. Please sign in again."
        ) from exc
    except FirebaseError as exc:
        raise FirebaseAuthError(
            "Firebase could not verify your sign-in. Check connectivity and project configuration."
        ) from exc

    uid = claims.get("uid")
    email = claims.get("email")
    if not isinstance(uid, str) or not uid:
        raise InvalidFirebaseTokenError("Firebase returned an invalid identity. Please sign in again.")
    return VerifiedIdentity(uid=uid, email=email if isinstance(email, str) else None)
