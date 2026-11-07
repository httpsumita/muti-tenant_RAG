# Build Log

Short, cumulative notes for each completed learning step.

## Step 1 — Security foundation

- Set initial direction: Python/Streamlit, Firebase Authentication and Firestore, Gemini.
- Established tenant isolation, pre-LLM authorization, and auditable retrieval as non-negotiable invariants.
- Next: model identity, tenant, role, document, and chunk data safely.

## Step 2 — UI scaffold

- Added a branded Streamlit landing page showing the build roadmap and integration status.
- Added Python dependencies, secret-file ignore rules, and a safe example secrets template.
- The UI does not accept uploads, retrieve content, authenticate, or call Gemini yet; use synthetic data only.
- Next: integrate Firebase Authentication and define tenant-scoped Firestore collections and access policy.

## Step 3 — Firebase client setup

- Added Firebase Admin SDK initialization using ADC and `FIREBASE_PROJECT_ID` from local configuration.
- Added a sidebar action to initialize a Firestore client; it deliberately performs no document reads or writes.
- Admin SDK bypasses Firestore Security Rules, so the app must remain local until verified identity and server-side authorization are implemented.
- Added `resolve_principal`: it verifies the Firebase ID token, then loads the active tenant and roles from `memberships/{uid}` and denies missing or invalid membership data.
- Connected the Streamlit sidebar sign-in form to email/password auth, ID-token verification, and membership resolution; sessions revalidate on rerun and can sign out.
- Added recruiter signup: preflight Firestore, create or authenticate the Firebase Auth account, and automatically join fixed `tenant-a` with the policy's `employee` role; HR/admin roles are not self-selectable.
- Added `.env` loading so local Firebase configuration is read from the ignored dotenv file or valid Streamlit TOML secrets.
- Added an operator-only, transactional tenant bootstrap that creates the tenant and its initial user membership together and refuses overwrites.
- Firestore database creation and ADC write access are still prerequisites; the configured project currently returns NotFound for its database.
- Next: persist ingested chunks and embeddings in Firestore.
- Validation: 52 unit tests pass; Tenant A signup form renders without a cloud request.

### Step 3 substep — Tenant A onboarding

- Added `provision_tenant_membership` for transactional membership in the policy-defined tenant; a missing Tenant A record is initialized safely.
- The operator CLI remains available for administrative creation of other tenants.
- Tests cover Tenant A membership assignment, idempotent retries, and fixed least-privilege roles.

### Step 3 substep — Trusted principal resolution

- Tested active, missing, inactive, malformed, and role-less memberships; user-supplied identity data is not accepted.
- The Streamlit UI now shows tenant and roles only after trusted membership resolution; those values are rendered as text, not HTML.
- Chat uses the verified principal and selected tenant; uploaded-document ingestion remains a separate step.

## Step 5 — Permission-filtered retrieval boundary

- Added Firestore vector retrieval with tenant equality and `allowed_roles` membership filters applied before nearest-neighbor search.
- Added fail-closed parsing and a Gemini orchestration service that skips generation on no results or retrieval errors.
- Adversarial tests confirm wrong-tenant, wrong-role, and missing-ACL chunks never reach the generation adapter, even when a fake backend returns them.
- Added the composite vector index definition. No live Firestore/Gemini request has been run; chunk persistence remains a prerequisite.
- Validation: 28 unit tests pass.

### Step 5 substep — Tenant-scoped chat UI

- Show chat only after Firebase authentication and verified tenant selection.
- Route questions through `answer_question`; history is kept separately for each user/tenant pair.
- Gemini generation receives only the authorized chunks returned by retrieval. No chunks or retrieval errors do not fall back to unfiltered context.
- Moved authenticated chat to the first main-page workflow and mapped common Firestore errors to actionable guidance.
- Added `firebase.json`; the live project currently has no composite indexes, so deploy the existing vector index before expecting search results.
- Validation: 49 unit tests pass; unauthenticated Streamlit smoke test confirms chat is hidden before sign-in.
- Next: ingest and persist authorized document chunks so chat has tenant content to search.

### Step 5 substep — Chat-only authenticated view

- Authenticated users now see only the tenant chat in the main page; onboarding cards and roadmap remain for signed-out users.
- Tenant selection and sign-out controls remain in the sidebar.
- Validation: 52 unit tests pass; mocked authenticated UI smoke test confirms the chat input is shown without the roadmap/cards.

### Auth persistence note

- Browser localStorage persistence is not enabled. The Streamlit storage component requires PyArrow, and this Windows environment's Application Control blocks its DLL.
- The app remains on Streamlit session-state auth; a browser reload may require signing in again.
- To enable persistence, use an environment where the approved PyArrow component can run, or move authentication to a browser-native Firebase client/server design. Do not bypass the machine's application-control policy.

## Step 4 — Two-tenant resume seed data

- Replaced the fake handbook seed with a contact-redacted professional profile under `tenant-a` and moved education/recognition into a separate `tenant-b` document.
- Updated `seed_demo_data.py` to embed both files separately and preserve each chunk's tenant and employee ACL.
- Tenant A's profile and chunks exclude the education section; Tenant B's education is inaccessible to a Tenant A principal through the tenant-prefiltered query.
- The optional cleanup targets only `DOC-TENA-001` and its `tenant-a` chunks; it cannot delete matching IDs in another tenant.
- Seeding is not run against Firebase yet. It requires the user's Firebase UID and a rotated Gemini API key.
- Updated the signed-out landing page with recruiter-focused candidate-profile cards and question starters.
- Validation: 59 unit tests pass; the Tenant A profile excludes education details, Tenant B contains them, and legacy cleanup remains tenant-scoped.
- Updated the signed-out landing page's right panel with recruiter-focused resume questions; smoke test confirms the seed prerequisite is visible.
