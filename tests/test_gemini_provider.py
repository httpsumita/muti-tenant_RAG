import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gemini_provider import EMBEDDING_DIMENSIONS, GENERATION_MODEL, GeminiProvider
from models import Chunk


class GeminiDocumentEmbeddingTests(unittest.TestCase):
    @patch("gemini_provider.genai.Client")
    def test_embeds_documents_for_retrieval_and_preserves_input_order(self, client_factory) -> None:
        client = Mock()
        client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1, 0.2]),
                SimpleNamespace(values=[0.3, 0.4]),
            ]
        )
        client_factory.return_value = client
        provider = GeminiProvider("synthetic-api-key")

        vectors = provider.embed_documents(["resume chunk one", "resume chunk two"])

        self.assertEqual(vectors, ((0.1, 0.2), (0.3, 0.4)))
        config = client.models.embed_content.call_args.kwargs["config"]
        self.assertEqual(config.task_type, "RETRIEVAL_DOCUMENT")
        self.assertEqual(config.output_dimensionality, EMBEDDING_DIMENSIONS)

    @patch("gemini_provider.genai.Client")
    def test_rejects_incomplete_embedding_response(self, client_factory) -> None:
        client = Mock()
        client.models.embed_content.return_value = SimpleNamespace(embeddings=[])
        client_factory.return_value = client
        provider = GeminiProvider("synthetic-api-key")

        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            provider.embed_documents(["resume chunk"])


class GeminiAnswerGenerationTests(unittest.TestCase):
    @patch("gemini_provider.genai.Client")
    def test_generates_answer_with_supported_model_and_authorized_context(self, client_factory) -> None:
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text="An answer.")
        client_factory.return_value = client
        provider = GeminiProvider("synthetic-api-key")
        chunk = Chunk(
            chunk_id="doc-1-chunk-0000",
            document_id="doc-1",
            tenant_id="tenant-a",
            chunk_index=0,
            text="Relevant resume context.",
            allowed_roles={"employee"},
        )

        answer = provider.generate_answer("What experience?", [chunk])

        self.assertEqual(answer, "An answer.")
        request = client.models.generate_content.call_args.kwargs
        self.assertEqual(request["model"], GENERATION_MODEL)
        self.assertIn("Relevant resume context.", request["contents"])


if __name__ == "__main__":
    unittest.main()