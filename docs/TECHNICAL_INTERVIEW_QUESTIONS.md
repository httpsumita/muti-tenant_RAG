# Technical Interview Question Bank

Short, keyword-style answers for quick interview preparation. Treat live-service
status as something to verify before describing it as tested.


## Project Overview

- What problem does this application solve?
  - **Answer:** Tenant-scoped document search; answers grounded in authorized content.
- What does “permission-aware multi-tenant RAG” mean in this project?
  - **Answer:** Tenant and role filters before retrieval; authorized context only reaches generation.
- Can you describe the complete flow from sign-in to a generated answer?
  - **Answer:** Firebase Auth → verified identity → Firestore membership → query embedding → filtered vector search → ACL check → Gemini answer.
  Firebase Auth: The user signs in and receives an identity token.
Verified identity: The app verifies the token so it knows who signed in.
Firestore membership: The app looks up which tenant and roles that user is allowed to access.
Query embedding: The question is converted into numbers that represent its meaning, so it can be matched against document chunks.
Filtered vector search: Firestore finds relevant chunks only within the selected tenant and the user’s allowed roles.
ACL check: The app checks the returned chunks’ access metadata again before using them.
Gemini answer: Only the question and authorized chunks are sent to Gemini, which generates the response. If no authorized chunks are found, Gemini is not called.

- Which parts of the system are implemented, and which are still planned or unverified?
  - **Answer:** Implemented: auth flow, seeder, filtered retrieval, unit tests. Verify live Firestore/Gemini; uploads and persistent audit writes are not implemented.
- Why is this more than a standard chatbot connected to a vector database?
  - **Answer:** Server-verified identity; tenant/role-filtered vector query; fail-closed authorization checks.
- What are the main trust boundaries in the system?
  - **Answer:** Browser to app; app to Firebase/Firestore; app to Gemini; trusted metadata versus document text.
- What security properties should hold even if Gemini returns an unexpected answer?
  - **Answer:** Gemini only receives authorized chunks; model output does not grant access or change ACLs.
- What converted the data intp vecptors before gemini
Gemini’s embedding model converts the text into vectors—specifically gemini-embedding-001.

During seeding, seed_demo_data.py calls GeminiProvider.embed_documents() to embed document chunks.
## Architecture and Components

- Why did you choose Streamlit for the current interface?
  - **Answer:** Fast Python prototype; simple chat and authentication UI.
- What responsibilities belong to Firebase Authentication, Firebase Admin, Firestore, and Gemini?
  - **Answer:** Auth: identity; Admin: server-side verification/access; Firestore: membership and chunks; Gemini: embeddings and answer generation.
- What is the difference between the Firebase Web API key and Application Default Credentials?
  - **Answer:** Web key: client Auth API identification; ADC: server identity for privileged Firebase/Firestore access.
- Why does the server use Firebase Admin rather than giving the browser direct Firestore access?
  - **Answer:** Keep database access server-side; centralize identity and authorization checks.
- How does `answer_question` coordinate embedding, retrieval, and generation?
  - **Answer:** Validate query/principal → embed query → retrieve authorized chunks → generate only when chunks exist.
- Why are the Gemini provider and retrieval service separate abstractions?
  - **Answer:** Separate model API calls from access-controlled data retrieval; easier testing and replacement.
- Which components would you replace first if the system grew beyond a prototype?
  - **Answer:** Streamlit UI; ingestion pipeline; possibly Firestore vector search, based on scale and requirements.
  Ingestion pipeline: The current seeder is an operator-run script, not a complete upload workflow with background processing, retries, and monitoring.
Firestore vector search: Convenient while the dataset is small; a dedicated vector database may offer more flexibility or scale if requirements grow.
In this project, the seeder (seed_demo_data.py) puts the sample data into Firestore so chat has documents to search:

Reads the sample profile and education files.
Splits each file into smaller text chunks.
Creates Gemini embeddings for those chunks.
Stores the chunks, embeddings, tenant IDs, and role permissions in Firestore.
Sets up the demo user’s tenant memberships.
It’s a setup script—not something that runs for each chat question. Without seeded chunks, retrieval has nothing to find.

## Tenants and Identity

- How is a Firebase user mapped to a tenant and a set of roles?
  - **Answer:** Verified Firebase UID → active Firestore membership → `Principal(tenant_id, roles)`.
- Why does the application derive tenant membership from Firestore rather than a form field?
  - **Answer:** Membership is trusted server-side data; form values are user-controlled.
- What is stored under `memberships/{uid}/tenants/{tenant_id}`?
  - **Answer:** Tenant membership data, including tenant ID, roles, and active status.
- How does the tenant dropdown avoid listing tenants the user cannot access?
  - **Answer:** Options come only from the user's resolved memberships.
- What happens when a user belongs to multiple tenants?
  - **Answer:** One verified principal per membership; user selects among their authorized tenants.
- How does new recruiter signup choose the tenant and role?
  - **Answer:** Fixed policy: `tenant-a` and `employee`; user cannot choose either.
- Why does signup assign the `employee` role instead of letting users choose `hr` or `admin`?
  - **Answer:** Least privilege; prevent self-assignment of elevated access.
- How would an administrator grant or revoke an HR role?
  - **Answer:** Trusted admin workflow updates membership roles; audit and revalidate the change.
- What happens if a membership is missing, inactive, malformed, or has no roles?
  - **Answer:** Reject access; fail closed.
- How would you prevent a user from attaching themselves to another tenant?
  - **Answer:** Never accept tenant/role claims from forms; provision memberships only through trusted server operations.
- How would you handle an employee leaving the organization while their Firebase session is still active?
  - **Answer:** Deactivate/remove membership; re-resolve membership on requests; revoke the Auth session as defense in depth.

## Authorization and Tenant Isolation

- What tenant and role checks are applied to each chunk?
  - **Answer:** `tenant_id` must match; `allowed_roles` must intersect the principal's roles.
- Why must authorization filters be part of the Firestore query before vector search?
  - **Answer:** Unauthorized records must never be returned to application code.
- Why is filtering results only after an unrestricted vector search unsafe?
  - **Answer:** Unauthorized content has already crossed the database boundary into the app.
- How does the application perform a second authorization check after Firestore returns chunks?
  - **Answer:** Validate chunk fields and call `can_access_chunk_metadata` before returning results.
- What happens when a chunk has no `tenant_id` or `allowed_roles` field?
  - **Answer:** Chunk is rejected; malformed records fail closed.
- Why must document/chunk ACL metadata come from trusted ingestion or administration rather than document text?
  - **Answer:** Text is untrusted; otherwise a document could assign itself permissions.
- How would you protect against a chunk whose tenant metadata conflicts with its parent document?
  - **Answer:** Validate chunk-to-document ownership during ingestion/retrieval; reject mismatches. Parent consistency checks are future work.
- What is the difference between tenant isolation and role-based access control in this design?
  - **Answer:** Tenant: organization boundary; role: permissions within that tenant.
- Why does Firebase Admin bypass Firestore Security Rules, and what defense remains necessary?
  - **Answer:** Admin SDK uses server IAM; application must enforce authorization in its own queries and checks.
- How would you add attribute-based access control without weakening the current role checks?
  - **Answer:** Add trusted attributes and explicit server-side predicates; retain tenant and role filters.

## Ingestion and Data Model

- What metadata must be stored on every document and every chunk?
  - **Answer:** IDs, tenant, allowed roles, ownership/source metadata; chunks also need index, text, and embedding.
- How does the current seeder turn the redacted resume into chunks?
  - **Answer:** Read UTF-8 text → split into overlapping windows → embed → write chunk records.
- How are chunk IDs made stable and associated with the source document?
  - **Answer:** `{document_id}-chunk-{index:04d}`.
- Why must each chunk inherit the source document's tenant and allowed roles?
  - **Answer:** Preserve document-level access controls during retrieval.
- What happens if embedding generation fails partway through seeding?
  - **Answer:** No Firestore batch is committed; error is surfaced.
- How would you make ingestion idempotent when the same document is uploaded twice?
  - **Answer:** Stable document/chunk IDs; merge writes; delete stale chunks.
- How would you handle document updates, stale chunks, and embedding model changes?
  - **Answer:** Re-chunk and re-embed; replace stale chunks; version embeddings and indexes.
- How should deletion or permission revocation affect all derived chunks and embeddings?
  - **Answer:** Delete or update document and all chunks atomically; invalidate derived data.
- Which resume details are stored in Tenant A versus Tenant B, and how does the query prevent Tenant A from retrieving Tenant B's education record?
  - **Answer:** Professional profile in Tenant A; education in Tenant B; Firestore tenant filter excludes Tenant B.
- How would a browser upload workflow differ from the current operator-run seed command?
  - **Answer:** Authenticated upload UI → validation/scanning → trusted metadata assignment → background ingestion. Upload UI is not implemented.

## Embeddings, Indexes, and Retrieval

- What is an embedding, and why is it used for semantic search?
  - **Answer:** Numeric representation of text; supports similarity search beyond exact keyword matches.
- Which model creates query embeddings and which task type does the provider use?
  - **Answer:** `gemini-embedding-001`; `RETRIEVAL_QUERY`.
- Why must query and document embeddings use compatible models and dimensions?
  - **Answer:** Similarity comparisons require vectors in the same embedding space and dimension.
- What does Firestore `find_nearest` do?
  - **Answer:** Returns vectors nearest to the query vector under the selected distance measure.
- Which filters run before `find_nearest`, and why?
  - **Answer:** Tenant equality and allowed-role overlap; constrain search to authorized chunks.
- What does `array_contains_any` mean for the user's role set?
  - **Answer:** Match chunks that allow at least one of the user's roles.
- Why does Firestore require a composite vector index for this query?
  - **Answer:** To support the combined tenant, role, and vector search.
- How do the index fields correspond to the retrieval query?
  - **Answer:** `tenant_id` ascending; `allowed_roles` array contains; `embedding` vector, 768 dimensions.
- What happens while the index is still `CREATING`?
  - **Answer:** Search may fail; wait until index status is `READY`.
- What distance measure is used, and why might cosine distance be appropriate?
  - **Answer:** Cosine; compares vector direction and is commonly used for semantic embeddings.
- How are result count and embedding dimensions validated?
  - **Answer:** Limit is bounded; vectors must be non-empty, numeric, finite, and at most 2,048 dimensions. Seeder expects 768.
- What should the service do if Firestore returns malformed records or a query fails?
  - **Answer:** Skip malformed chunks; surface query failures; never send unverified content to Gemini.
- How would you measure retrieval quality independently from authorization correctness?
  - **Answer:** Labeled queries; recall@k / precision@k; separately test tenant and role isolation.
- How might filtering affect recall or latency in a large collection?
  - **Answer:** Smaller authorized candidate set improves isolation; index/selectivity can affect latency and recall.

## Gemini and Prompt Safety

- What exact data is sent to Gemini during a query?
  - **Answer:** Query text and retrieved authorized chunk text; query embedding is used for search.
- At what point is chunk text allowed to leave the application for generation?
  - **Answer:** Only after tenant/role filtering and metadata authorization checks.
- What happens if retrieval returns no authorized chunks?
  - **Answer:** Return a no-authorized-information response; do not call generation.
- Why is a prompt instruction like “ignore confidential data” not an authorization control?
  - **Answer:** Prompts guide model behavior; they do not enforce access boundaries.
- How does the prompt treat document text that may contain prompt injection?
  - **Answer:** As untrusted reference material, not instructions.
- Can prompt injection in an authorized document still be dangerous? Why?
  - **Answer:** Yes; it may manipulate the answer or model behavior despite authorized retrieval.
- How would you add citations or source references to generated answers?
  - **Answer:** Include chunk/document IDs in context; require citations; validate cited IDs against retrieved chunks.
- How would you constrain answer length, output format, or unsupported claims?
  - **Answer:** Set generation limits; use a structured format; require context-grounded answers and citations.
- How would you avoid sending unnecessary personal data to an external model provider?
  - **Answer:** Redact/minimize at ingestion; retrieve only relevant authorized chunks; review provider retention settings.

## Audit, Privacy, and Operations

- What should a retrieval audit record contain?
  - **Answer:** Request/time, principal, tenant, policy version, outcome, and returned document/chunk IDs.
- Why should ordinary logs avoid storing full queries, passwords, tokens, or document text?
  - **Answer:** Reduce exposure of credentials and personal/sensitive information.
- How would you correlate an answer with the exact chunks retrieved without logging their contents?
  - **Answer:** Record request ID and chunk/document IDs.
- What retention and deletion rules should apply to audit records and embeddings?
  - **Answer:** Defined retention period; delete on policy/legal requirements; cascade document deletion to derived data.
- How should API keys and service credentials be stored in development and production?
  - **Answer:** Local ignored `.env` for development; managed secrets and runtime identity in production.
- Why is a local `.env` file different from a Firebase Web API key?
  - **Answer:** `.env` can hold private server credentials; Firebase Web API key identifies a client project and is not server authorization.
- How would you deploy this server using a runtime service identity rather than a downloaded service-account key?
  - **Answer:** Attach a least-privilege cloud service account; use ADC; avoid key files.
- What metrics would you monitor for auth failures, retrieval latency, empty results, and model errors?
  - **Answer:** Counts/rates, latency percentiles, empty-result rate, provider error codes, index failures.
- How would you respond to a suspected cross-tenant exposure?
  - **Answer:** Contain access; preserve logs; identify affected records/users; notify owners; remediate and verify isolation.

## Testing and Failure Scenarios

- How do the tests prove that tenant and role filters are applied before vector search?
  - **Answer:** Fake Firestore asserts both filters are set before `find_nearest`.
- How does the adversarial test prove that denied chunks never reach Gemini generation?
  - **Answer:** Return a denied chunk; assert it is filtered and generation is not called with it.
- Why do unit tests use fake Firestore and Gemini clients?
  - **Answer:** Fast, deterministic, offline tests without cloud costs or writes.
- Which integration tests still need to run against Firestore Emulator or a test project?
  - **Answer:** Membership resolution/provisioning, composite vector query, index behavior, and end-to-end Gemini flow.
- How would you test that Tenant A content never appears in Tenant B results?
  - **Answer:** Seed distinct tenant fixtures; query as each principal; assert no cross-tenant chunk IDs or text.
- How would you test role revocation after a user has signed in?
  - **Answer:** Revoke membership role; repeat retrieval with the session; verify no newly unauthorized chunks return.
- What should happen if the vector index is missing or still building?
  - **Answer:** Show a clear index-not-ready error; do not fall back to unfiltered search.
- What should happen if Firebase Auth succeeds but membership creation fails?
  - **Answer:** Keep signup pending; grant no tenant access; allow a safe retry.
- How does retry behavior avoid granting access before the membership is committed?
  - **Answer:** Store pending signup state; set authenticated app session only after membership succeeds.
- Which failures should be retried, and which should fail immediately?
  - **Answer:** Retry transient network/service errors; fail immediately on invalid input, identity, permissions, or malformed data.

## Tradeoffs and Future Work

- What are the tradeoffs of using Firestore vector search instead of a dedicated vector database?
  - **Answer:** Simpler Firebase integration; fewer services; less control over advanced retrieval and scaling.
- What limitations arise from Firestore vector filters or composite indexes?
  - **Answer:** Index setup/limits; supported filter combinations; query and scale constraints.
- Why is browser-local persistent authentication not enabled in the current Streamlit build?
  - **Answer:** The current environment has a PyArrow DLL issue with the local-storage component; session state is used.
- What would change if authentication moved to the Firebase Web SDK?
  - **Answer:** Browser-managed sign-in/session; backend must still verify tokens and enforce access.
- How would you scale ingestion and embedding generation for large documents?
  - **Answer:** Background jobs; bounded batches; retries; rate limiting; progress and idempotency tracking.
- How would you support multiple document formats and OCR?
  - **Answer:** Add format-specific extractors/OCR before common normalization, chunking, and ingestion.
- How would you add rate limits, email verification, and abuse protection for tenant signup?
  - **Answer:** Auth email verification; per-user/IP quotas; abuse monitoring; server-side policy checks.
- How would you ensure an administrator cannot accidentally expose one tenant's documents to another?
  - **Answer:** Tenant-scoped admin operations; immutable tenant ownership; audit trails; automated isolation tests.
- What are the top three production-hardening tasks before real company data is allowed?
  - **Answer:** Live security/integration testing; ingestion and deletion controls; audit, monitoring, and privacy review.

## Be Ready to State the Current Status

- Which seed command writes the resume to Firestore, and what credentials does it require?
  - **Answer:** `seed_demo_data.py --firebase-uid <UID>`; Firebase project config, ADC, Gemini API key, and the account UID.
- Has the seed command been run against the live project?
  - **Answer:** Verify with the operator/Firestore; local code cannot confirm live project state.
- Has the live Firestore vector query been tested after the index became `READY`?
  - **Answer:** Verify against the target project; unit tests use fakes.
- Is browser upload implemented?
  - **Answer:** No; current seeding is operator-run.
- Are retrieval audit events persisted to Firestore?
  - **Answer:** No; audit persistence is planned.
- Does a browser refresh preserve sign-in in this Streamlit environment?
  - **Answer:** Not reliably; authentication is currently in Streamlit session state.
- Which tests are unit tests, and which checks have been performed against live services?
  - **Answer:** Unit tests use mocks/fakes; report live checks only after running them against the configured project.
