from __future__ import annotations

from pathlib import Path

from models import Chunk, Document


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 150) -> tuple[str, ...]:
    """Split text into bounded character windows, retaining a small overlap."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must contain non-whitespace content")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or overlap < 0:
        raise ValueError("overlap must be a non-negative integer")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            whitespace = next(
                (index for index in range(end, start, -1) if text[index - 1].isspace()),
                None,
            )
            if whitespace is not None:
                end = whitespace

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        next_start = max(start + 1, end - overlap) #takes next start ack by overlap
        while next_start > start + 1 and not text[next_start - 1].isspace():
            next_start -= 1
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = next_start

    return tuple(chunks)


def load_text_file(
    source_path: str | Path,
    document: Document,
    *,
    chunk_size: int = 1200,
    overlap: int = 150,
) -> tuple[Chunk, ...]:
    """Read a UTF-8 text file and attach explicitly supplied document permissions."""
    text = Path(source_path).read_text(encoding="utf-8")
    text_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    return tuple(
        Chunk(
            chunk_id=f"{document.document_id}-chunk-{index:04d}",
            document_id=document.document_id,
            tenant_id=document.tenant_id,
            chunk_index=index,
            text=chunk_text_value,
            allowed_roles=document.allowed_roles,
        )
        for index, chunk_text_value in enumerate(text_chunks)
    )
