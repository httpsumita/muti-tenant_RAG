from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from authorization import can_access_chunk_metadata
from models import Chunk, Principal


MAX_VECTOR_DIMENSIONS = 2048
MAX_ROLE_FILTERS = 30
MAX_RESULTS = 1000


def retrieve_authorized_chunks(
    db,
    principal: Principal,
    query_embedding: Sequence[float],
    *,
    limit: int = 5,
) -> tuple[Chunk, ...]:
    """Run tenant/role-filtered Firestore vector search and fail closed on bad records."""
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a verified Principal")
    if not principal.roles:
        return ()
    if len(principal.roles) > MAX_ROLE_FILTERS:
        raise ValueError(f"principal may have at most {MAX_ROLE_FILTERS} retrieval roles")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
    if isinstance(query_embedding, (str, bytes)):
        raise ValueError("query_embedding must be a numeric sequence")

    vector_values = tuple(query_embedding)
    if not vector_values or len(vector_values) > MAX_VECTOR_DIMENSIONS:
        raise ValueError("query_embedding has an unsupported dimension")
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        for value in vector_values
    ):
        raise ValueError("query_embedding must contain only finite numbers")

    query = (
        db.collection("chunks")
        .where(filter=FieldFilter("tenant_id", "==", principal.tenant_id))
        .where(
            filter=FieldFilter(
                "allowed_roles", "array_contains_any", sorted(principal.roles)
            )
        )
        .find_nearest(
            vector_field="embedding",
            query_vector=Vector(vector_values),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
        )
    )

    authorized_chunks: list[Chunk] = []
    for snapshot in query.stream():
        data = snapshot.to_dict()
        if not isinstance(data, dict):
            continue
        try:
            chunk = Chunk(
                chunk_id=snapshot.id,
                document_id=data["document_id"],
                tenant_id=data["tenant_id"],
                chunk_index=data["chunk_index"],
                text=data["text"],
                allowed_roles=data["allowed_roles"],
            )
        except (KeyError, TypeError, ValueError):
            continue
        if can_access_chunk_metadata(principal, chunk):
            authorized_chunks.append(chunk)

    return tuple(authorized_chunks)