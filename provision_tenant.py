from __future__ import annotations

import argparse
import os
import re
import sys
from uuid import uuid4

import firebase_admin.firestore as firestore
from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError

from firebase_client import get_firestore_client
from models import Principal


class TenantProvisioningError(ValueError):
    """The tenant or membership already exists or has invalid provisioning data."""


DEFAULT_SIGNUP_TENANT_ID = "tenant-a"
DEFAULT_SIGNUP_ROLE = "employee"


def generate_tenant_id(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise TenantProvisioningError("name must be non-empty")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "tenant"
    return f"{slug}-{uuid4().hex[:8]}"


def _validate_document_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or "/" in value:
        raise TenantProvisioningError(f"{field_name} must be a non-empty Firestore document ID")
    if len(value.encode("utf-8")) > 1500 or value in {".", ".."}:
        raise TenantProvisioningError(f"{field_name} is not a valid Firestore document ID")


def provision_tenant(
    db,
    *,
    tenant_id: str,
    name: str,
    firebase_uid: str,
    roles: list[str],
) -> None:
    """Atomically create one tenant and its initial active membership."""
    _validate_document_id(tenant_id, "tenant_id")
    _validate_document_id(firebase_uid, "firebase_uid")
    if not isinstance(name, str) or not name.strip():
        raise TenantProvisioningError("name must be non-empty")

    try:
        principal = Principal(user_id=firebase_uid, tenant_id=tenant_id, roles=roles)
    except (TypeError, ValueError) as exc:
        raise TenantProvisioningError("roles must be a non-empty collection of role names") from exc
    if not principal.roles:
        raise TenantProvisioningError("at least one role is required")
    if len(principal.roles) > 30:
        raise TenantProvisioningError("at most 30 roles can be assigned")

    tenant_ref = db.collection("tenants").document(tenant_id)
    membership_ref = (
        db.collection("memberships")
        .document(firebase_uid)
        .collection("tenants")
        .document(tenant_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def create_records(transaction):
        tenant_snapshot = tenant_ref.get(transaction=transaction)
        membership_snapshot = membership_ref.get(transaction=transaction)
        if tenant_snapshot.exists:
            raise TenantProvisioningError("tenant_id already exists")
        if membership_snapshot.exists:
            raise TenantProvisioningError("user already has a membership for this tenant")

        transaction.create(
            tenant_ref,
            {
                "tenant_id": tenant_id,
                "name": name.strip(),
                "active": True,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        )
        transaction.create(
            membership_ref,
            {
                "tenant_id": tenant_id,
                "roles": sorted(principal.roles),
                "active": True,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        )

    create_records(transaction)


def provision_tenant_membership(
    db,
    *,
    firebase_uid: str,
    tenant_id: str = DEFAULT_SIGNUP_TENANT_ID,
    roles: list[str] | None = None,
    tenant_name: str | None = None,
) -> None:
    """Join a user to an existing policy tenant, creating its record if absent."""
    _validate_document_id(tenant_id, "tenant_id")
    _validate_document_id(firebase_uid, "firebase_uid")
    assigned_roles = roles if roles is not None else [DEFAULT_SIGNUP_ROLE]
    try:
        principal = Principal(user_id=firebase_uid, tenant_id=tenant_id, roles=assigned_roles)
    except (TypeError, ValueError) as exc:
        raise TenantProvisioningError("roles must be a non-empty collection of role names") from exc
    if not principal.roles:
        raise TenantProvisioningError("at least one role is required")
    if len(principal.roles) > 30:
        raise TenantProvisioningError("at most 30 roles can be assigned")

    tenant_ref = db.collection("tenants").document(tenant_id)
    membership_ref = (
        db.collection("memberships")
        .document(firebase_uid)
        .collection("tenants")
        .document(tenant_id)
    )
    transaction = db.transaction()

    @firestore.transactional
    def create_membership(transaction):
        tenant_snapshot = tenant_ref.get(transaction=transaction)
        membership_snapshot = membership_ref.get(transaction=transaction)

        if tenant_snapshot.exists:
            tenant_data = tenant_snapshot.to_dict()
            if not isinstance(tenant_data, dict) or tenant_data.get("active") is not True:
                raise TenantProvisioningError("tenant is inactive or invalid")

        if membership_snapshot.exists:
            membership = membership_snapshot.to_dict()
            if (
                isinstance(membership, dict)
                and membership.get("active") is True
                and membership.get("tenant_id") == tenant_id
            ):
                try:
                    existing = Principal(
                        user_id=firebase_uid,
                        tenant_id=tenant_id,
                        roles=membership.get("roles", []),
                    )
                except (TypeError, ValueError) as exc:
                    raise TenantProvisioningError("existing membership is invalid") from exc
                if existing.roles:
                    return
            raise TenantProvisioningError("user already has an invalid or inactive membership")

        if not tenant_snapshot.exists:
            transaction.create(
                tenant_ref,
                {
                    "tenant_id": tenant_id,
                    "name": tenant_name or ("Tenant A" if tenant_id == "tenant-a" else tenant_id),
                    "active": True,
                    "created_at": firestore.SERVER_TIMESTAMP,
                },
            )

        transaction.create(
            membership_ref,
            {
                "tenant_id": tenant_id,
                "roles": sorted(principal.roles),
                "active": True,
                "created_at": firestore.SERVER_TIMESTAMP,
            },
        )

    create_membership(transaction)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(
        description="Provision a tenant and its first Firebase Auth user's membership."
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--firebase-uid", required=True)
    parser.add_argument("--role", action="append", required=True, dest="roles")
    args = parser.parse_args(argv)

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        parser.error("FIREBASE_PROJECT_ID must be set in .env or the process environment")

    try:
        db = get_firestore_client(project_id)
        provision_tenant(
            db,
            tenant_id=args.tenant_id,
            name=args.name,
            firebase_uid=args.firebase_uid,
            roles=args.roles,
        )
    except TenantProvisioningError as exc:
        parser.error(str(exc))
    except GoogleAPICallError:
        print(
            "Firestore provisioning failed. Confirm a Firestore database exists and the "
            "ADC account has write access.",
            file=sys.stderr,
        )
        return 1

    print("Tenant and initial membership created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())