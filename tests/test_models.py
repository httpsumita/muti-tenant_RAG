import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from models import AuditEvent, AuditOutcome, Chunk, Document, Principal


class CoreModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_principal_roles_are_immutable(self) -> None:
        roles = {"reader"}
        principal = Principal(user_id="user-1", tenant_id="tenant-1", roles=roles)
        roles.add("admin")

        self.assertEqual(principal.roles, frozenset({"reader"}))
        with self.assertRaises(FrozenInstanceError):
            principal.tenant_id = "tenant-2"  # type: ignore[misc]

    def test_document_requires_explicit_access_roles_and_aware_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed_roles must not be empty"):
            Document("doc-1", "tenant-1", "Title", "owner-1", frozenset(), self.now)

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Document(
                "doc-1",
                "tenant-1",
                "Title",
                "owner-1",
                frozenset({"reader"}),
                datetime(2026, 1, 1),
            )

    def test_chunk_requires_nonempty_text_and_nonnegative_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "chunk_index"):
            Chunk("chunk-1", "doc-1", "tenant-1", -1, "content", frozenset({"reader"}))

        with self.assertRaisesRegex(ValueError, "allowed_roles must not be empty"):
            Chunk("chunk-1", "doc-1", "tenant-1", 0, "content", frozenset())

    def test_denied_audit_event_cannot_claim_returned_resources(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not include returned resource IDs"):
            AuditEvent(
                event_id="event-1",
                request_id="request-1",
                occurred_at=self.now,
                principal_id="user-1",
                tenant_id="tenant-1",
                policy_version="rbac-v1",
                outcome=AuditOutcome.DENIED,
                document_ids=("doc-1",),
            )

    def test_allowed_audit_event_records_resource_ids_without_content(self) -> None:
        event = AuditEvent(
            event_id="event-1",
            request_id="request-1",
            occurred_at=self.now,
            principal_id="user-1",
            tenant_id="tenant-1",
            policy_version="rbac-v1",
            outcome=AuditOutcome.ALLOWED,
            document_ids=["doc-1"],
            chunk_ids=["chunk-1"],
        )

        self.assertEqual(event.document_ids, ("doc-1",))
        self.assertEqual(event.chunk_ids, ("chunk-1",))
        self.assertFalse(hasattr(event, "query"))
        self.assertFalse(hasattr(event, "content"))


if __name__ == "__main__":
    unittest.main()
