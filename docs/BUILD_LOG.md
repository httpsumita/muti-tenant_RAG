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
- Next: authenticate users and derive tenant/role context from verified identity.

## Step 5 — Permission-filtered retrieval boundary

- Added Firestore vector retrieval with tenant equality and `allowed_roles` membership filters applied before nearest-neighbor search.
- Added fail-closed parsing and a Gemini orchestration service that skips generation on no results or retrieval errors.
- Adversarial tests confirm wrong-tenant, wrong-role, and missing-ACL chunks never reach the generation adapter, even when a fake backend returns them.
- Added the composite vector index definition. No live Firestore/Gemini request or Streamlit chat integration has been run; chunk persistence and trusted principal wiring remain prerequisites.
- Validation: 28 unit tests pass.
