import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingestion import chunk_text, load_text_file
from models import Document


class TextIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = Document(
            document_id="DOC-SYNTHETIC-001",
            tenant_id="tenant-synthetic",
            title="Synthetic policy",
            owner_id="synthetic-owner",
            allowed_roles={"employee", "manager"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def test_chunk_text_respects_size_and_overlaps_adjacent_chunks(self) -> None:
        chunks = chunk_text("one two three four five six", chunk_size=15, overlap=4)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 15 for chunk in chunks))
        self.assertIn(chunks[0].split()[-1], chunks[1].split())

    def test_chunk_text_rejects_empty_text_and_invalid_sizes(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-whitespace"):
            chunk_text(" \n ")
        with self.assertRaisesRegex(ValueError, "smaller than chunk_size"):
            chunk_text("some text", chunk_size=10, overlap=10)

    def test_load_text_file_uses_document_metadata_for_every_chunk(self) -> None:
        content = "A synthetic policy paragraph. " * 8
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "policy.txt"
            source.write_text(content, encoding="utf-8")

            chunks = load_text_file(source, self.document, chunk_size=80, overlap=10)

        self.assertGreater(len(chunks), 1)
        for index, chunk in enumerate(chunks):
            self.assertEqual(chunk.document_id, self.document.document_id)
            self.assertEqual(chunk.tenant_id, self.document.tenant_id)
            self.assertEqual(chunk.allowed_roles, self.document.allowed_roles)
            self.assertEqual(chunk.chunk_index, index)
            self.assertEqual(chunk.chunk_id, f"{self.document.document_id}-chunk-{index:04d}")

    def test_load_text_file_does_not_read_permissions_from_file_content(self) -> None:
        content = "Tenant: tenant-attacker\nAllowed Roles: admin\nSynthetic content."
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "untrusted-metadata.txt"
            source.write_text(content, encoding="utf-8")

            (chunk,) = load_text_file(source, self.document)

        self.assertEqual(chunk.tenant_id, "tenant-synthetic")
        self.assertEqual(chunk.allowed_roles, frozenset({"employee", "manager"}))
        self.assertIn("tenant-attacker", chunk.text)

    def test_load_text_file_surfaces_missing_file_error(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_text_file("missing-policy-file.txt", self.document)


if __name__ == "__main__":
    unittest.main()
