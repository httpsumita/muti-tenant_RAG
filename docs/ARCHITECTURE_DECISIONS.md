# Architecture Decisions

## Initial choices

- **UI/runtime:** Python + Streamlit — fast way to build the learning interface.
- **Public demo access:** No visitor authentication. The server creates a fixed `tenant-a` / `employee` principal; all matching Tenant A content is public. Do not place private data in that tenant.
- **Primary store:** Cloud Firestore — store tenant-scoped documents, chunks, ACL metadata, and audit events. The server must enforce access explicitly; Firebase Admin SDK bypasses Firestore Security Rules, so rules alone are not authorization for server code.
- **LLM:** Gemini via the Google Gen AI SDK — invoke only after authorized retrieval returns permitted chunks.
- **Development data:** synthetic documents only.

## Deferred decisions

Exact policy expression (initially RBAC), chunking/embedding strategy and vector search implementation, deployment target, and audit retention period. Resolve these before integrating real identities or data.

## Retrieval constraint

The retrieval implementation must constrain tenant and roles in the database query before returning text. Verify Firestore query/index semantics and any vector-search filter behavior with integration tests. If the selected Firebase vector-search path cannot enforce the required filters before returning chunk content, choose a design that can; never fetch broad results and treat later filtering as the security boundary.

## Current milestone

The backend retrieval service uses Firestore vector search with tenant and role prefilters, then validates returned chunk metadata before passing context to Gemini. A composite index is defined in `firestore.indexes.json`. The public Streamlit UI uses a fixed synthetic principal for `tenant-a` / `employee`; Firebase Auth is not used for visitor access. Never put private data in Tenant A.
