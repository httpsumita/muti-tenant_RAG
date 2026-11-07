import unittest
from unittest.mock import patch

from provision_tenant import (
    DEFAULT_SIGNUP_ROLE,
    DEFAULT_SIGNUP_TENANT_ID,
    TenantProvisioningError,
    generate_tenant_id,
    provision_tenant,
    provision_tenant_membership,
)


class FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None = None) -> None:
        self.exists = exists
        self.data = data or {}

    def to_dict(self) -> dict:
        return self.data


class FakeDocumentReference:
    def __init__(self, path: tuple[str, ...], existing: set[tuple[str, ...]]) -> None:
        self.path = path
        self.existing = existing

    def get(self, *, transaction):
        exists = self.path in self.existing
        data = {}
        if exists and self.path[0] == "tenants":
            data = {"tenant_id": self.path[-1], "active": True}
        elif exists and self.path[0] == "memberships":
            data = {"tenant_id": self.path[-1], "roles": [DEFAULT_SIGNUP_ROLE], "active": True}
        return FakeSnapshot(exists, data)

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self.path + (name,), self.existing)


class FakeCollection:
    def __init__(self, path: tuple[str, ...], existing: set[tuple[str, ...]]) -> None:
        self.path = path
        self.existing = existing

    def document(self, document_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(self.path + (document_id,), self.existing)


class FakeTransaction:
    def __init__(self) -> None:
        self.created: list[tuple[FakeDocumentReference, dict]] = []

    def create(self, reference: FakeDocumentReference, data: dict) -> None:
        self.created.append((reference, data))


class FakeFirestore:
    def __init__(self, existing: set[tuple[str, ...]] | None = None) -> None:
        self.existing = existing or set()
        self.fake_transaction = FakeTransaction()

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection((name,), self.existing)

    def transaction(self) -> FakeTransaction:
        return self.fake_transaction


class TenantProvisioningTests(unittest.TestCase):
    def call_provision(self, db: FakeFirestore, **overrides) -> None:
        values = {
            "tenant_id": "tenant-acme",
            "name": "Acme",
            "firebase_uid": "firebase-user-1",
            "roles": ["reader", "admin"],
        }
        values.update(overrides)
        provision_tenant(db, **values)

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_atomically_creates_tenant_and_initial_membership(self, _transactional) -> None:
        db = FakeFirestore()

        self.call_provision(db)

        self.assertEqual(len(db.fake_transaction.created), 2)
        tenant_ref, tenant = db.fake_transaction.created[0]
        membership_ref, membership = db.fake_transaction.created[1]
        self.assertEqual(tenant_ref.path, ("tenants", "tenant-acme"))
        self.assertEqual(tenant["name"], "Acme")
        self.assertTrue(tenant["active"])
        self.assertEqual(
            membership_ref.path,
            ("memberships", "firebase-user-1", "tenants", "tenant-acme"),
        )
        self.assertEqual(membership["tenant_id"], "tenant-acme")
        self.assertEqual(membership["roles"], ["admin", "reader"])
        self.assertTrue(membership["active"])

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_refuses_to_overwrite_existing_tenant(self, _transactional) -> None:
        db = FakeFirestore({("tenants", "tenant-acme")})

        with self.assertRaisesRegex(TenantProvisioningError, "tenant_id already exists"):
            self.call_provision(db)

        self.assertEqual(db.fake_transaction.created, [])

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_refuses_to_overwrite_existing_membership(self, _transactional) -> None:
        db = FakeFirestore(
            {("memberships", "firebase-user-1", "tenants", "tenant-acme")}
        )

        with self.assertRaisesRegex(TenantProvisioningError, "already has a membership"):
            self.call_provision(db)

        self.assertEqual(db.fake_transaction.created, [])

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_allows_same_user_to_join_another_tenant(self, _transactional) -> None:
        db = FakeFirestore(
            {
                ("memberships", "firebase-user-1", "tenants", "tenant-existing"),
                ("tenants", "tenant-existing"),
            }
        )

        self.call_provision(db)

        self.assertEqual(len(db.fake_transaction.created), 2)

    def test_rejects_path_injection_or_empty_roles_before_database_access(self) -> None:
        db = FakeFirestore()

        with self.assertRaisesRegex(TenantProvisioningError, "document ID"):
            self.call_provision(db, tenant_id="bad/tenant")
        with self.assertRaises(TenantProvisioningError):
            self.call_provision(db, roles=[])

        self.assertEqual(db.fake_transaction.created, [])

    def test_generates_a_firestore_safe_tenant_id_from_the_name(self) -> None:
        tenant_id = generate_tenant_id("Acme & Sons, Inc.")

        self.assertRegex(tenant_id, r"^acme-sons-inc-[a-f0-9]{8}$")
        self.assertNotIn("/", tenant_id)

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_self_signup_joins_policy_tenant_with_employee_role(self, _transactional) -> None:
        db = FakeFirestore({("tenants", DEFAULT_SIGNUP_TENANT_ID)})

        provision_tenant_membership(db, firebase_uid="firebase-user-1")

        self.assertEqual(len(db.fake_transaction.created), 1)
        membership_ref, membership = db.fake_transaction.created[0]
        self.assertEqual(
            membership_ref.path,
            ("memberships", "firebase-user-1", "tenants", "tenant-a"),
        )
        self.assertEqual(membership["tenant_id"], DEFAULT_SIGNUP_TENANT_ID)
        self.assertEqual(membership["roles"], ["employee"])

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_self_signup_creates_missing_policy_tenant_and_membership(self, _transactional) -> None:
        db = FakeFirestore()

        provision_tenant_membership(db, firebase_uid="firebase-user-1")

        self.assertEqual(len(db.fake_transaction.created), 2)
        tenant_ref, tenant = db.fake_transaction.created[0]
        self.assertEqual(tenant_ref.path, ("tenants", "tenant-a"))
        self.assertEqual(tenant["tenant_id"], "tenant-a")
        self.assertTrue(tenant["active"])

    @patch("provision_tenant.firestore.transactional", side_effect=lambda function: function)
    def test_self_signup_is_idempotent_for_existing_active_membership(self, _transactional) -> None:
        db = FakeFirestore(
            {
                ("tenants", "tenant-a"),
                ("memberships", "firebase-user-1", "tenants", "tenant-a"),
            }
        )

        provision_tenant_membership(db, firebase_uid="firebase-user-1")

        self.assertEqual(db.fake_transaction.created, [])


if __name__ == "__main__":
    unittest.main()