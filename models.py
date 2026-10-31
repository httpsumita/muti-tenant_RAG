from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _immutable_roles(roles: frozenset[str], field_name: str) -> frozenset[str]:
    if isinstance(roles, str):
        raise ValueError(f"{field_name} must be a collection of role names")
    try:
        result = frozenset(roles)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a collection of role names") from exc
    for role in result:
        _require_non_blank(role, field_name)
    return result


def _immutable_ids(ids: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if isinstance(ids, str):
        raise ValueError(f"{field_name} must be a collection of IDs")
    try:
        result = tuple(ids)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a collection of IDs") from exc
    for value in result:
        _require_non_blank(value, field_name)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class Principal:
    """Verified application identity; construct only from trusted auth claims."""

    user_id: str
    tenant_id: str
    roles: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_blank(self.user_id, "user_id")
        _require_non_blank(self.tenant_id, "tenant_id")
        object.__setattr__(self, "roles", _immutable_roles(self.roles, "roles"))


@dataclass(frozen=True, slots=True)
class Document:
    """Tenant-scoped document metadata with explicit role-based access metadata."""

    document_id: str
    tenant_id: str
    title: str
    owner_id: str
    allowed_roles: frozenset[str]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.document_id, "document_id")
        _require_non_blank(self.tenant_id, "tenant_id")
        _require_non_blank(self.title, "title")
        _require_non_blank(self.owner_id, "owner_id")
        object.__setattr__(
            self, "allowed_roles", _immutable_roles(self.allowed_roles, "allowed_roles")
        )
        if not self.allowed_roles:
            raise ValueError("allowed_roles must not be empty")
        _require_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Chunk:
    """A document passage with tenant and access metadata stored alongside its text."""

    chunk_id: str
    document_id: str
    tenant_id: str
    chunk_index: int
    text: str
    allowed_roles: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_blank(self.chunk_id, "chunk_id")
        _require_non_blank(self.document_id, "document_id")
        _require_non_blank(self.tenant_id, "tenant_id")
        if isinstance(self.chunk_index, bool) or not isinstance(self.chunk_index, int):
            raise ValueError("chunk_index must be a non-negative integer")
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be a non-negative integer")
        _require_non_blank(self.text, "text")
        object.__setattr__(
            self, "allowed_roles", _immutable_roles(self.allowed_roles, "allowed_roles")
        )
        if not self.allowed_roles:
            raise ValueError("allowed_roles must not be empty")


class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Retrieval audit metadata; intentionally excludes query and document content."""

    event_id: str
    request_id: str
    occurred_at: datetime
    principal_id: str
    tenant_id: str
    policy_version: str
    outcome: AuditOutcome
    document_ids: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(self.event_id, "event_id")
        _require_non_blank(self.request_id, "request_id")
        _require_aware_datetime(self.occurred_at, "occurred_at")
        _require_non_blank(self.principal_id, "principal_id")
        _require_non_blank(self.tenant_id, "tenant_id")
        _require_non_blank(self.policy_version, "policy_version")
        if not isinstance(self.outcome, AuditOutcome):
            raise ValueError("outcome must be an AuditOutcome")
        object.__setattr__(
            self, "document_ids", _immutable_ids(self.document_ids, "document_ids")
        )
        object.__setattr__(self, "chunk_ids", _immutable_ids(self.chunk_ids, "chunk_ids"))
        if self.outcome is not AuditOutcome.ALLOWED and (self.document_ids or self.chunk_ids):
            raise ValueError("denied and error events must not include returned resource IDs")
