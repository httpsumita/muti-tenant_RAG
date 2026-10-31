"""Tenant and role authorization for in-memory application records."""

from models import Chunk, Document, Principal


def can_access_document(principal: Principal, document: Document) -> bool:
    """Return whether a principal matches the document tenant and an allowed role."""
    return (
        principal.tenant_id == document.tenant_id
        and not principal.roles.isdisjoint(document.allowed_roles)
    )


def can_access_chunk(
    principal: Principal,
    chunk: Chunk,
    document: Document,
) -> bool:
    """Authorize a chunk only when both it and its parent document allow access."""
    return (
        chunk.document_id == document.document_id
        and chunk.tenant_id == document.tenant_id
        and can_access_document(principal, document)
        and can_access_chunk_metadata(principal, chunk)
    )


def can_access_chunk_metadata(principal: Principal, chunk: Chunk) -> bool:
    """Authorize tenant and role metadata stored directly on a chunk."""
    return (
        principal.tenant_id == chunk.tenant_id
        and not principal.roles.isdisjoint(chunk.allowed_roles)
    )
