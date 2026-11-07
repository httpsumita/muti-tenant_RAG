from __future__ import annotations

from dataclasses import dataclass

import firebase_admin
import requests
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import DefaultCredentialsError

from models import Principal


class FirebaseAuthError(Exception):
    """A safe, user-presentable Firebase Authentication error."""


class InvalidFirebaseTokenError(FirebaseAuthError):
    """The ID token is invalid, expired, or revoked and requires a new sign-in."""


class FirebaseAccountExistsError(FirebaseAuthError):
    """The requested email already has a Firebase Authentication account."""


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    uid: str
    email: str | None


@dataclass(frozen=True, slots=True)
class FirebaseSession:
    id_token: str
    refresh_token: str


def sign_in_with_password_session(
    email: str, password: str, api_key: str
) -> FirebaseSession:
    """Exchange email/password for Firebase ID and refresh tokens."""
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
    refresh_token = payload.get("refreshToken") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or not id_token or not isinstance(refresh_token, str) or not refresh_token:
        raise FirebaseAuthError("Firebase Authentication returned an invalid response.")
    return FirebaseSession(id_token=id_token, refresh_token=refresh_token)


def sign_in_with_password(email: str, password: str, api_key: str) -> str:
    """Exchange email/password for a Firebase Authentication ID token."""
    return sign_in_with_password_session(email, password, api_key).id_token


def sign_up_with_password_session(
    email: str, password: str, api_key: str
) -> tuple[FirebaseSession, str]:
    """Create an account and return its Firebase session and UID."""
    if not email.strip() or not password:
        raise FirebaseAuthError("Enter both your email and password.")
    if not api_key.strip():
        raise FirebaseAuthError("Firebase Authentication is not configured.")

    try:
        response = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signUp",
            params={"key": api_key},
            json={"email": email.strip(), "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise FirebaseAuthError(
            "Could not reach Firebase Authentication. Check your connection and try again."
        ) from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message", "") if isinstance(error, dict) else ""
        code = message.split(":", 1)[0].strip()
        if code == "EMAIL_EXISTS":
            raise FirebaseAccountExistsError(
                "This email already has an account. Enter its current password to add this tenant."
            )
        if code == "WEAK_PASSWORD":
            raise FirebaseAuthError("Password does not meet the Firebase password policy.")
        if code == "INVALID_EMAIL":
            raise FirebaseAuthError("Enter a valid email address.")
        if code == "OPERATION_NOT_ALLOWED":
            raise FirebaseAuthError(
                "Email/password signup is disabled. Enable it in Firebase Authentication settings."
            )
        if code == "API_KEY_INVALID":
            raise FirebaseAuthError("The Firebase Web API key is invalid for this project.")
        raise FirebaseAuthError("Firebase could not create the account. Check Auth settings and try again.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FirebaseAuthError("Firebase Authentication returned an invalid response.") from exc

    id_token = payload.get("idToken") if isinstance(payload, dict) else None
    refresh_token = payload.get("refreshToken") if isinstance(payload, dict) else None
    uid = payload.get("localId") if isinstance(payload, dict) else None
    if (
        not isinstance(id_token, str)
        or not id_token
        or not isinstance(refresh_token, str)
        or not refresh_token
        or not isinstance(uid, str)
        or not uid
    ):
        raise FirebaseAuthError("Firebase Authentication returned an invalid response.")
    return FirebaseSession(id_token=id_token, refresh_token=refresh_token), uid


def sign_up_with_password(email: str, password: str, api_key: str) -> tuple[str, str]:
    """Create a Firebase Authentication account and return its ID token and UID."""
    session, uid = sign_up_with_password_session(email, password, api_key)
    return session.id_token, uid


def refresh_firebase_session(refresh_token: str, api_key: str) -> FirebaseSession:
    """Exchange a persisted Firebase refresh token for a fresh, rotated session."""
    if not refresh_token or not api_key:
        raise InvalidFirebaseTokenError("Your saved sign-in has expired. Please sign in again.")

    try:
        response = requests.post(
            "https://securetoken.googleapis.com/v1/token",
            params={"key": api_key},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise FirebaseAuthError(
            "Could not restore your saved sign-in. Check your connection and try again."
        ) from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message", "") if isinstance(error, dict) else ""
        code = message.split(":", 1)[0].strip()
        if code in {"TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_DISABLED", "USER_NOT_FOUND"}:
            raise InvalidFirebaseTokenError(
                "Your saved sign-in has expired. Please sign in again."
            )
        raise FirebaseAuthError("Could not restore your saved Firebase sign-in.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FirebaseAuthError("Firebase returned an invalid session response.") from exc

    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    rotated_refresh_token = payload.get("refresh_token") if isinstance(payload, dict) else None
    if (
        not isinstance(id_token, str)
        or not id_token
        or not isinstance(rotated_refresh_token, str)
        or not rotated_refresh_token
    ):
        raise FirebaseAuthError("Firebase returned an invalid session response.")
    return FirebaseSession(id_token=id_token, refresh_token=rotated_refresh_token)


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


def _load_principals(identity: VerifiedIdentity, db) -> tuple[Principal, ...]:
    """Load every active tenant membership under a verified Firebase UID."""
    if not isinstance(identity, VerifiedIdentity) or not identity.uid.strip():
        raise FirebaseAuthError("A verified Firebase identity is required.")

    try:
        snapshots = (
            db.collection("memberships")
            .document(identity.uid)
            .collection("tenants")
            .stream()
        )
    except GoogleAPICallError as exc:
        raise FirebaseAuthError(
            "Could not read your tenant memberships from Firestore. Confirm Firestore is enabled "
            "and the ADC account has permission to read memberships."
        ) from exc

    principals: list[Principal] = []
    for snapshot in snapshots:
        membership = snapshot.to_dict()
        if not isinstance(membership, dict) or membership.get("active") is not True:
            continue

        try:
            tenant_id = membership["tenant_id"]
            roles = membership["roles"]
            principal = Principal(user_id=identity.uid, tenant_id=tenant_id, roles=roles)
        except (KeyError, TypeError, ValueError):
            continue

        if principal.tenant_id == snapshot.id and principal.roles:
            principals.append(principal)

    if not principals:
        raise FirebaseAuthError("Your account is not assigned to an active tenant.")
    return tuple(sorted(principals, key=lambda principal: principal.tenant_id))


def resolve_principals(id_token: str, project_id: str, db) -> tuple[Principal, ...]:
    """Verify the ID token and return all active principals for its Firebase user."""
    identity = verify_identity_token(id_token, project_id)
    return _load_principals(identity, db)


def resolve_principal(
    id_token: str,
    project_id: str,
    db,
    *,
    tenant_id: str | None = None,
) -> Principal:
    """Resolve one authorized tenant principal, requiring selection when ambiguous."""
    principals = resolve_principals(id_token, project_id, db)
    if tenant_id is None:
        if len(principals) == 1:
            return principals[0]
        raise FirebaseAuthError("Select one of your available tenants to continue.")

    for principal in principals:
        if principal.tenant_id == tenant_id:
            return principal
    raise FirebaseAuthError("You do not have access to the selected tenant.")


def authenticate_with_password(
    email: str,
    password: str,
    api_key: str,
    project_id: str,
    db,
) -> tuple[str, tuple[Principal, ...]]:
    """Sign in, verify the returned token, and load trusted tenant memberships."""
    id_token = sign_in_with_password(email, password, api_key)
    principals = resolve_principals(id_token, project_id, db)
    return id_token, principals


def authenticate_with_password_session(
    email: str,
    password: str,
    api_key: str,
    project_id: str,
    db,
) -> tuple[FirebaseSession, tuple[Principal, ...]]:
    """Sign in, verify the ID token, and return the session plus active memberships."""
    session = sign_in_with_password_session(email, password, api_key)
    principals = resolve_principals(session.id_token, project_id, db)
    return session, principals
