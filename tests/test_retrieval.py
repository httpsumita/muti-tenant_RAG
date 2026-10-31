import unittest
from unittest.mock import patch

from models import Principal
from rag_service import answer_question


class FakeSnapshot:
    def __init__(self, chunk_id: str, data: dict) -> None:
        self.id = chunk_id
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class FakeQuery:
    def __init__(self, snapshots: list[FakeSnapshot]) -> None:
        self.snapshots = snapshots
        self.filters: list[tuple[str, str, object]] = []
        self.vector_query_started = False

    def where(self, *, filter: tuple[str, str, object]):
        if self.vector_query_started:
            raise AssertionError("ACL filters must be applied before vector retrieval")
        self.filters.append(filter)
        return self

    def find_nearest(self, **kwargs):
        self.vector_query_started = True
        self.vector_options = kwargs
        return self

    def stream(self):
        return iter(self.snapshots)


class FakeCollection:
    def __init__(self, query: FakeQuery) -> None:
        self.query = query

    def where(self, *, filter: tuple[str, str, object]):
        return self.query.where(filter=filter)


class FakeFirestore:
    def __init__(self, snapshots: list[FakeSnapshot]) -> None:
        self.query = FakeQuery(snapshots)

    def collection(self, name: str) -> FakeCollection:
        if name != "chunks":
            raise AssertionError(f"Unexpected collection: {name}")
        return FakeCollection(self.query)


class FakeGemini:
    def __init__(self) -> None:
        self.generated_chunks = None
        self.embedding_calls = 0
        self.generation_calls = 0

    def embed_query(self, query: str) -> tuple[float, ...]:
        self.embedding_calls += 1
        return (0.1, 0.2, 0.3)

    def generate_answer(self, query: str, chunks: tuple) -> str:
        self.generation_calls += 1
        self.generated_chunks = chunks
        return "synthetic answer"


def snapshot_data(
    document_id: str,
    tenant_id: str,
    text: str,
    allowed_roles: list[str],
) -> dict:
    return {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "chunk_index": 0,
        "text": text,
        "allowed_roles": allowed_roles,
    }


class PermissionFilteredRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.principal = Principal(
            user_id="synthetic-user",
            tenant_id="tenant-a",
            roles={"reader"},
        )

    @patch("retrieval.FieldFilter", side_effect=lambda field, op, value: (field, op, value))
    def test_tenant_and_role_filters_are_applied_before_vector_search(
        self, _field_filter
    ) -> None:
        db = FakeFirestore(
            [
                FakeSnapshot(
                    "chunk-allowed",
                    snapshot_data("doc-a", "tenant-a", "authorized context", ["reader"]),
                )
            ]
        )
        gemini = FakeGemini()

        answer = answer_question(db, self.principal, "question", gemini)

        self.assertEqual(answer, "synthetic answer")
        self.assertEqual(
            db.query.filters,
            [
                ("tenant_id", "==", "tenant-a"),
                ("allowed_roles", "array_contains_any", ["reader"]),
            ],
        )
        self.assertTrue(db.query.vector_query_started)
        self.assertEqual(db.query.vector_options["vector_field"], "embedding")
        self.assertEqual(gemini.generated_chunks[0].text, "authorized context")

    @patch("retrieval.FieldFilter", side_effect=lambda field, op, value: (field, op, value))
    def test_denied_and_malformed_chunks_never_reach_gemini(
        self, _field_filter
    ) -> None:
        db = FakeFirestore(
            [
                FakeSnapshot(
                    "chunk-allowed",
                    snapshot_data("doc-a", "tenant-a", "authorized context", ["reader"]),
                ),
                FakeSnapshot(
                    "chunk-wrong-role",
                    snapshot_data("doc-b", "tenant-a", "DENIED wrong role", ["admin"]),
                ),
                FakeSnapshot(
                    "chunk-wrong-tenant",
                    snapshot_data("doc-c", "tenant-b", "DENIED other tenant", ["reader"]),
                ),
                FakeSnapshot(
                    "chunk-missing-acl",
                    {
                        "document_id": "doc-d",
                        "tenant_id": "tenant-a",
                        "chunk_index": 0,
                        "text": "DENIED missing ACL",
                    },
                ),
            ]
        )
        gemini = FakeGemini()

        answer_question(db, self.principal, "question", gemini)

        self.assertEqual(gemini.generation_calls, 1)
        self.assertEqual(
            [chunk.text for chunk in gemini.generated_chunks], ["authorized context"]
        )
        self.assertNotIn("DENIED", " ".join(chunk.text for chunk in gemini.generated_chunks))

    @patch("retrieval.FieldFilter", side_effect=lambda field, op, value: (field, op, value))
    def test_retrieval_failure_never_calls_gemini_generation(self, _field_filter) -> None:
        db = FakeFirestore([])

        def fail_stream():
            raise RuntimeError("synthetic Firestore failure")

        db.query.stream = fail_stream
        gemini = FakeGemini()

        with self.assertRaisesRegex(RuntimeError, "synthetic Firestore failure"):
            answer_question(db, self.principal, "question", gemini)

        self.assertEqual(gemini.generation_calls, 0)

    def test_empty_roles_return_no_chunks_without_query_or_generation(self) -> None:
        principal = Principal("synthetic-user", "tenant-a", frozenset())
        db = FakeFirestore([])
        gemini = FakeGemini()

        answer = answer_question(db, principal, "question", gemini)

        self.assertIn("couldn't find", answer)
        self.assertFalse(db.query.vector_query_started)
        self.assertEqual(gemini.embedding_calls, 0)
        self.assertEqual(gemini.generation_calls, 0)

    def test_unverified_principal_is_rejected_before_gemini(self) -> None:
        gemini = FakeGemini()

        with self.assertRaisesRegex(TypeError, "verified Principal"):
            answer_question(FakeFirestore([]), object(), "question", gemini)

        self.assertEqual(gemini.embedding_calls, 0)
        self.assertEqual(gemini.generation_calls, 0)


if __name__ == "__main__":
    unittest.main()