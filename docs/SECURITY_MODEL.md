# Security Model (Initial)

## Assets and trust boundaries

- Protected assets: source documents, chunk text, embeddings, metadata, prompts, and retrieval/audit records.
- Trust boundaries: caller to API; API to database; ingestion pipeline to database; API to embedding/LLM providers; operators to logs and backups.
- Assume requests, document text, and model output can be malicious or malformed. Never treat prompt instructions as authorization.

## Public demo access policy

This Streamlit deployment intentionally has no visitor authentication. The server assigns every visitor the same fixed principal: `public-demo-visitor`, tenant `tenant-a`, role `employee`. Therefore all Tenant A chunks allowed for `employee` are public to anyone who can reach the app. Tenant A must contain only content approved for public disclosure. Never put private or sensitive data in Tenant A. Tenant B and other tenants remain excluded by the retrieval filters.

## Required invariants

1. The visitor cannot choose or change the server-defined tenant or role.
2. Every chunk is bound to exactly one tenant and has explicit access metadata. Missing or invalid access metadata means deny.
3. Tenant and role predicates are applied in the database retrieval operation before chunk text is returned to the application or sent to an LLM. A post-retrieval filter is not sufficient.
4. Firestore Security Rules do not authorize the server's Firebase Admin requests; server code must enforce access explicitly and use narrowly scoped query functions.
5. Gemini receives only relevant chunks authorized for the fixed public demo principal. Retrieval failure or policy uncertainty fails closed.
6. Public visitors can consume the operator's Gemini quota. Keep provider keys server-side and monitor usage.
7. Audit records should identify the public demo principal, tenant, policy version, request/correlation ID, and returned chunk/document IDs without logging sensitive query or document content.

## Retrieval implementation contract

The `chunks` collection stores `tenant_id`, `allowed_roles`, `embedding`, and chunk metadata. Retrieval applies `tenant_id == principal.tenant_id` and `allowed_roles array_contains_any principal.roles` in the same Firestore vector query. Returned records are parsed into validated chunk models and checked again before generation. Empty roles, malformed ACL metadata, query errors, and no authorized results must never fall back to an unfiltered query or invoke Gemini generation.

## Initial authorization shape

Use tenant isolation plus role-based access. In this public demo, a document/chunk is visible only when its tenant is `tenant-a` and its allowed-role set includes `employee`. The server fixes these values; visitors cannot provide or change them.

## Identity and membership tools

Firebase Authentication and membership provisioning code remains available for operator scripts and tests, but it is not used to authenticate visitors to the public Streamlit demo.

## Threats to test as the project grows

- Cross-tenant IDOR and vector-search leakage.
- Missing ACL metadata, stale permissions, and permission changes after ingestion.
- Prompt injection in authorized documents (content is still untrusted, even when access is allowed).
- Cache-key collisions across tenants or principals.
- Audit records that omit denied/returned-resource context or leak document contents.
- Database connection-pool reuse that carries the wrong tenant context.

## Scope and caveats

This is a public learning demo, not a private multi-tenant production deployment or compliance certification. Production use requires visitor authentication, an organization-specific threat model, legal/privacy review, key and secret management, tested backup/restore, rate limiting, and independent security review.
