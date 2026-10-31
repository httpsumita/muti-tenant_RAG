import unittest
from datetime import datetime, timezone

from authorization import can_access_chunk, can_access_document
from models import Chunk, Document, Principal


class TenantRoleAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = Principal(
            user_id="user-reader",
            tenant_id="tenant-a",
            roles={"reader"},
        )
        self.other_tenant_reader = Principal(
            user_id="user-other",
            tenant_id="tenant-b",
            roles={"reader"},
        )
        self.editor = Principal(
            user_id="user-editor",
            tenant_id="tenant-a",
            roles={"editor"},
        )
        self.document = Document(
            document_id="doc-a",
            tenant_id="tenant-a",
            title="Synthetic handbook",
            owner_id="user-owner",
            allowed_roles={"reader", "editor"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.chunk = Chunk(
            chunk_id="chunk-a-0",
            document_id="doc-a",
            tenant_id="tenant-a",
            chunk_index=0,
            text="Synthetic, non-sensitive example content.",
            allowed_roles={"reader"},
        )

    def test_document_allows_matching_tenant_and_role(self) -> None:
        self.assertTrue(can_access_document(self.reader, self.document))

    def test_document_denies_principal_from_another_tenant(self) -> None:
        self.assertFalse(can_access_document(self.other_tenant_reader, self.document))

    def test_document_denies_principal_without_an_allowed_role(self) -> None:
        restricted_document = Document(
            document_id="doc-restricted",
            tenant_id="tenant-a",
            title="Synthetic restricted document",
            owner_id="user-owner",
            allowed_roles={"admin"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertFalse(can_access_document(self.reader, restricted_document))

    def test_chunk_allows_only_when_document_and_chunk_allow_role(self) -> None:
        self.assertTrue(can_access_chunk(self.reader, self.chunk, self.document))
        self.assertFalse(can_access_chunk(self.editor, self.chunk, self.document))

    def test_chunk_denies_mismatched_parent_document(self) -> None:
        different_document = Document(
            document_id="doc-other",
            tenant_id="tenant-a",
            title="Synthetic other document",
            owner_id="user-owner",
            allowed_roles={"reader"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertFalse(can_access_chunk(self.reader, self.chunk, different_document))

    def test_chunk_denies_inconsistent_tenant_metadata(self) -> None:
        inconsistent_chunk = Chunk(
            chunk_id="chunk-b-0",
            document_id="doc-a",
            tenant_id="tenant-b",
            chunk_index=0,
            text="Synthetic, non-sensitive example content.",
            allowed_roles={"reader"},
        )

        self.assertFalse(can_access_chunk(self.reader, inconsistent_chunk, self.document))


if __name__ == "__main__":
    unittest.main()
