# Security Model (Initial)

## Assets and trust boundaries

- Protected assets: source documents, chunk text, embeddings, metadata, prompts, and retrieval/audit records.
- Trust boundaries: caller to API; API to database; ingestion pipeline to database; API to embedding/LLM providers; operators to logs and backups.
- Assume requests, document text, and model output can be malicious or malformed. Never treat prompt instructions as authorization.

## Non-negotiable invariants

1. Every request has a verified principal and tenant context derived from trusted authentication—not caller-supplied tenant headers or request-body fields.
2. Every chunk is bound to exactly one tenant and has explicit access metadata. Missing or invalid access metadata means deny.
3. Tenant and role/policy predicates are applied in the database retrieval operation before chunk text is returned to the application or sent to an LLM. A post-retrieval filter is not sufficient.
4. Firestore Security Rules should restrict direct client access as defense in depth. Server code using Firebase Admin bypasses those rules, so it must perform explicit authorization and use narrowly scoped query functions.
5. The LLM receives only authorized chunks. Retrieval failure or policy uncertainty fails closed.
6. Audit records identify the principal, tenant, authorization/policy version, request/correlation ID, and the chunk/document IDs actually returned; keep sensitive query and content out of ordinary logs.
7. Revocation and document deletion have defined semantics for stored chunks, caches, and subsequent retrievals.

## Retrieval implementation contract

The `chunks` collection stores `tenant_id`, `allowed_roles`, `embedding`, and chunk metadata. Retrieval applies `tenant_id == principal.tenant_id` and `allowed_roles array_contains_any principal.roles` in the same Firestore vector query. Returned records are parsed into validated chunk models and checked again before generation. Empty roles, malformed ACL metadata, query errors, and no authorized results must never fall back to an unfiltered query or invoke Gemini generation.

## Initial authorization shape

Use tenant isolation plus role-based access as the first policy. A document/chunk is visible only when its tenant matches the authenticated tenant and its allowed-role set intersects the principal's effective roles (with an explicitly modeled owner/admin rule). Do not rely on role names or tenant IDs provided by the caller without server-side verification.

## Threats to test as the project grows

- Cross-tenant IDOR and vector-search leakage.
- Missing ACL metadata, stale permissions, and permission changes after ingestion.
- Prompt injection in authorized documents (content is still untrusted, even when access is allowed).
- Cache-key collisions across tenants or principals.
- Audit records that omit denied/returned-resource context or leak document contents.
- Database connection-pool reuse that carries the wrong tenant context.

## Scope and caveats

This is a learning design, not a compliance certification. Production use requires an organization-specific threat model, identity-provider integration, legal/privacy review, key and secret management, tested backup/restore, and independent security review.
