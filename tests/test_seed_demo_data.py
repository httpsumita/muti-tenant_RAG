import unittest
from unittest.mock import patch

from seed_demo_data import (
    EDUCATION_DOCUMENT_ID,
    LEGACY_POLICY_DOCUMENT_ID,
    PROFILE_DOCUMENT_ID,
    TENANT_A_ID,
    TENANT_B_ID,
    seed_demo_data,
)


class FakeSnapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.id = reference.path[-1]
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class FakeDocumentReference:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def get(self):
        return FakeSnapshot(self, self.database.documents.get(self.path))

    def set(self, data, merge=False):
        current = self.database.documents.get(self.path, {}) if merge else {}
        self.database.documents[self.path] = {**current, **data}


class FakeBatch:
    def __init__(self, database):
        self.database = database
        self.operations = []

    def set(self, reference, data, merge=False):
        self.operations.append(("set", reference, data, merge))

    def delete(self, reference):
        self.operations.append(("delete", reference, None, False))

    def commit(self):
        for operation, reference, data, merge in self.operations:
            if operation == "delete":
                self.database.documents.pop(reference.path, None)
            else:
                current = self.database.documents.get(reference.path, {}) if merge else {}
                self.database.documents[reference.path] = {**current, **data}


class FakeQuery:
    def __init__(self, database, collection_name):
        self.database = database
        self.collection_name = collection_name
        self.filters = []

    def where(self, field, operator, value):
        self.filters.append((field, operator, value))
        return self

    def stream(self):
        results = []
        for path, data in self.database.documents.items():
            if len(path) != 2 or path[0] != self.collection_name:
                continue
            if all(
                (operator == "==" and data.get(field) == value)
                for field, operator, value in self.filters
            ):
                results.append(FakeSnapshot(FakeDocumentReference(self.database, path), data))
        return iter(results)


class FakeCollection:
    def __init__(self, database, name):
        self.database = database
        self.name = name

    def document(self, document_id):
        return FakeDocumentReference(self.database, (self.name, document_id))

    def where(self, field, operator, value):
        return FakeQuery(self.database, self.name).where(field, operator, value)


class FakeFirestore:
    def __init__(self, documents=None):
        self.documents = documents or {}
        self.batches = []

    def collection(self, name):
        return FakeCollection(self, name)

    def batch(self):
        batch = FakeBatch(self)
        self.batches.append(batch)
        return batch


class ResumeSeedTests(unittest.TestCase):
    @patch("seed_demo_data.provision_tenant_membership")
    def test_resume_chunks_are_written_only_to_tenant_a(self, provision_membership) -> None:
        db = FakeFirestore()

        profile_chunk_count, education_chunk_count = seed_demo_data(
            db,
            firebase_uid="synthetic-user",
            embed_documents=lambda texts: tuple((0.1,) * 768 for _ in texts),
        )

        profile_chunks = [
            data for path, data in db.documents.items()
            if path[0] == "chunks" and data.get("document_id") == PROFILE_DOCUMENT_ID
        ]
        education_chunks = [
            data for path, data in db.documents.items()
            if path[0] == "chunks" and data.get("document_id") == EDUCATION_DOCUMENT_ID
        ]
        self.assertGreater(profile_chunk_count, 0)
        self.assertGreater(education_chunk_count, 0)
        self.assertEqual(len(profile_chunks), profile_chunk_count)
        self.assertEqual(len(education_chunks), education_chunk_count)
        self.assertTrue(all(chunk["tenant_id"] == TENANT_A_ID for chunk in profile_chunks))
        self.assertTrue(
            all(chunk["allowed_roles"] == ["employee"] for chunk in profile_chunks)
        )
        self.assertTrue(all(chunk["tenant_id"] == TENANT_B_ID for chunk in education_chunks))
        self.assertTrue(
            all(chunk["allowed_roles"] == ["employee"] for chunk in education_chunks)
        )
        self.assertNotIn(
            "maulana abul kalam azad",
            " ".join(chunk["text"].lower() for chunk in profile_chunks),
        )
        self.assertIn(
            "maulana abul kalam azad",
            " ".join(chunk["text"].lower() for chunk in education_chunks),
        )
        self.assertEqual(provision_membership.call_count, 2)

    @patch("seed_demo_data.provision_tenant_membership")
    def test_legacy_policy_cleanup_never_deletes_another_tenants_data(
        self, _provision_membership
    ) -> None:
        documents = {
            ("documents", LEGACY_POLICY_DOCUMENT_ID): {"tenant_id": TENANT_A_ID},
            ("chunks", "old-tenant-a"): {
                "tenant_id": TENANT_A_ID,
                "document_id": LEGACY_POLICY_DOCUMENT_ID,
            },
            ("chunks", "same-id-tenant-b"): {
                "tenant_id": TENANT_B_ID,
                "document_id": LEGACY_POLICY_DOCUMENT_ID,
            },
        }
        db = FakeFirestore(documents)

        seed_demo_data(
            db,
            firebase_uid="synthetic-user",
            embed_documents=lambda texts: tuple((0.1,) * 768 for _ in texts),
            replace_legacy_policy=True,
        )

        self.assertNotIn(("documents", LEGACY_POLICY_DOCUMENT_ID), db.documents)
        self.assertNotIn(("chunks", "old-tenant-a"), db.documents)
        self.assertIn(("chunks", "same-id-tenant-b"), db.documents)


if __name__ == "__main__":
    unittest.main()