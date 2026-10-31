from __future__ import annotations

from typing import Protocol

from models import Chunk, Principal
from retrieval import retrieve_authorized_chunks


class GeminiGateway(Protocol):
    def embed_query(self, query: str) -> tuple[float, ...]: ...

    def generate_answer(self, query: str, chunks: tuple[Chunk, ...]) -> str: ...


def answer_question(
    db,
    principal: Principal,
    query: str,
    gemini: GeminiGateway,
    *,
    limit: int = 5,
) -> str:
    """Retrieve authorized context before invoking Gemini generation."""
    if not query.strip():
        raise ValueError("query must contain non-whitespace text")
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a verified Principal")
    if not principal.roles:
        return "I couldn't find information you are authorized to access for that question."

    query_embedding = gemini.embed_query(query)
    chunks = retrieve_authorized_chunks(db, principal, query_embedding, limit=limit)
    if not chunks:
        return "I couldn't find information you are authorized to access for that question."

    return gemini.generate_answer(query, chunks)