# Permission-Aware Multi-Tenant RAG

A learning project for building a production-minded RAG service where tenant boundaries and document permissions are enforced before retrieved content reaches a model.

## Learning path

We will build this in small, reviewable steps. Each completed step gets a short entry in [docs/BUILD_LOG.md](docs/BUILD_LOG.md).

1. Define security invariants and architecture.
2. Build the Streamlit interface and establish local development.
3. Add Firebase Authentication and a tenant-scoped Firestore data model.
4. Ingest documents and persist chunk-level access metadata.
5. Implement permission-filtered retrieval and prove denied chunks never reach Gemini.
6. Add audit events, retention, and integrity controls.
7. Add adversarial tests, observability, deployment hardening, and operational runbooks.

## Initial technology direction

Python + Streamlit for the learning app, Firebase Authentication and Cloud Firestore for identity/data when those milestones are reached, and Gemini for answer generation. Local development should use synthetic data only. Firebase Admin credentials and Gemini API keys must stay outside source control.

## Security is a design constraint

Tenant filtering and authorization are server-side requirements, not prompt instructions. Retrieval must be authorized in the database query before any chunk content is returned to application/model code. See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Run the UI scaffold

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the interface with `streamlit run app.py`.

The Streamlit UI supports Firebase email/password sign-in, automatic Tenant A signup, tenant selection, and tenant-scoped chat. New accounts join `tenant-a` with the policy's least-privilege `employee` role; users cannot select a tenant ID or role. HR and admin access must be assigned through trusted administration. Chat uses the selected tenant's verified principal and permission-filtered Firestore retrieval before Gemini generation. Browser upload UI is not implemented; the resume/demo seed command below can populate Firestore. Authentication currently lives in Streamlit session state; browser reload may require signing in again because this machine blocks the PyArrow DLL required by Streamlit localStorage components. Do not enter real company data.

For local Firebase setup, set `FIREBASE_PROJECT_ID` and `FIREBASE_WEB_API_KEY` in the ignored root `.env` file or in valid TOML at `.streamlit/secrets.toml`. The app loads `.env` at startup. Enable Email/Password in Firebase Authentication, and complete `gcloud auth application-default login`. Provision active `memberships/{uid}` documents with `tenant_id` and non-empty `roles` for allowed users. Keep this scaffold local and do not use private data until retrieval and audit logging are connected.

### Tenant A signup and operator provisioning

For self-service signup, choose **Join Tenant A** in the sidebar and enter an email and password. Firestore is checked before Firebase Auth creates the account. The server automatically joins the user to `tenant-a` with the fixed `employee` role. If the tenant record does not exist yet, it is created as part of the same transaction as the membership. Users cannot choose a tenant ID or role. If membership setup fails after Auth signup, the session preserves a retry action and grants no tenant access until Firestore commits the membership.

For local provisioning, the ADC account needs the `Cloud Datastore User` role (`roles/datastore.user`) on the development project.

Operators can also bootstrap or recover a tenant using a Firebase Authentication UID and the command:

```powershell
.\.venv\Scripts\python.exe provision_tenant.py --tenant-id acme --name "Acme" --firebase-uid FIREBASE_AUTH_UID --role reader
```

Replace the sample tenant values and UID. The command atomically creates `tenants/{tenant_id}` and `memberships/{firebase_uid}` and refuses to overwrite either. It does not accept or store passwords.

### Seed the resume and two tenants

The fake `knowledge/policy.txt` has been removed. The contact-redacted professional profile is stored in `knowledge/tenant-a-resume.txt`; education details are stored separately in `knowledge/tenant-b-education.txt` and seeded only into `tenant-b`. Tenant A's resume source and chunks do not contain the education section.

After rotating the exposed Gemini API key, create the embeddings and Firestore chunks with your Firebase Authentication UID:

```powershell
.\.venv\Scripts\python.exe seed_demo_data.py --firebase-uid YOUR_FIREBASE_UID --replace-legacy-policy
```

The command gives that UID employee membership in both tenants, embeds Tenant A's professional profile and Tenant B's education record, and writes chunk tenant/role metadata. The replacement flag removes only the known `DOC-TENA-001` fake policy metadata and chunks from `tenant-a`. It does not touch same-ID content in another tenant. The script makes live Firestore writes and Gemini embedding requests; unit tests use mocks and do not perform those writes.

# gcloud.cmd auth application-default login

The prefiltered vector query requires the composite index in [firestore.indexes.json](firestore.indexes.json). The Firebase CLI config is in [firebase.json](firebase.json); the configured project has the tenant-filtered vector index. If its status is `CREATING`, wait until it is `READY` before testing chat. Chunks must be stored in the `chunks` collection with `tenant_id`, `allowed_roles`, `embedding` (768 dimensions), `document_id`, `chunk_index`, and `text` fields. The retrieval API requires a `Principal` created from verified identity and trusted tenant/role data; never construct it from form fields.

Run the unit tests with `.venv\Scripts\python.exe -m unittest discover -s tests -v` on Windows. The retrieval tests use fake Firestore and Gemini clients and do not require cloud access.

## Current status

Steps 1–5 have local implementations, including a two-tenant profile seeder. Tenant A contains professional experience; Tenant B contains education details, so the latter must not be returned to a Tenant A principal. The seed command has not yet written to Firestore. Browser upload UI, audit writes, and live end-to-end retrieval/Gemini still need validation.


The key idea is:
Authenticate/validate the user → retrieve only authorized chunks → verify permissions again → generate an answer only from those chunks.

1. User sends a question
A["Question + Principal"] → B["answer_question()"]

The system receives two things:
- Question — what the user wants to know.
- Principal — the identity and authorization information of the user.
For example:
Question:
"What is the company's leave policy?"

Principal:
tenant_id = "tenant-a"
roles = ["employee"]

The Principal is important because the system should not answer based only on what is relevant. It must also determine what this particular user is allowed to see.
2. Validate that the question exists
C{"Question non-empty?"}

The first check is whether the user actually provided a question.

If the question is empty:

C -- No --> E["Raise ValueError"]

The system stops and raises an error.

For example:
Question = ""

would be invalid.

If the question contains text, processing continues.
3. Validate the Principal
D{"Principal is a Principal object?"}

The system checks whether the supplied user identity is actually represented by the expected Principal object.

If not:

D -- No --> F["Raise TypeError"]

This prevents the authorization layer from receiving arbitrary or malformed data.

A valid principal might conceptually look like:
Principal(
    tenant_id="tenant-a",
    roles=["employee"]
)

4. Check whether the user has any roles
G{"Principal has roles?"}

Next, the system checks whether the principal has at least one role.

For example:
roles = ["employee"]

is valid.

But:
roles = []

means the user has no authorization roles.

In that case:

G -- No --> H["Return: no authorized information"]

The system immediately returns something like:
No authorized information is available for this request.

This is an important security boundary. No role = no access.
5. Convert the question into an embedding
I["GeminiProvider.embed_query(query)"]

If the user has a valid role, the question is converted into an embedding.

For example:
"What is the company's leave policy?"

might become a vector such as:
[0.12, -0.34, 0.81, ...]

The exact numbers aren't important.

The embedding represents the semantic meaning of the question, allowing the system to find chunks that are conceptually similar.

This is what makes semantic search possible.
6. Retrieve authorized chunks
J["retrieve_authorized_chunks(db, principal, embedding)"]

The embedding and the user's principal are passed into the retrieval function.

This function's job is:
Find relevant chunks that the user is authorized to access.

This is where your multi-tenant security model becomes important.
7. Validate retrieval parameters
K["Validate embedding, role count, and result limit"]

Before querying the database, the system validates things such as:
- Is the embedding valid?
- Does the principal have a reasonable number of roles?
- Is the requested number of results within an allowed limit?
For example, the system might prevent someone from requesting:
limit = 1,000,000

This protects the retrieval system from malformed or abusive requests.
8. Filter by tenant
L["Firestore query: tenant_id matches"]

Now the system queries Firestore.

The first major security filter is:
chunk.tenant_id == principal.tenant_id

For example, if the user belongs to:
tenant-a

then the system should only retrieve:
tenant-a

documents/chunks.

It must not retrieve:
tenant-b
tenant-c

even if those chunks are semantically more relevant.

This is the core of multi-tenant isolation.
9. Filter by role
M["Firestore query: allowed_roles intersects principal.roles"]

The second security filter checks roles.

Suppose a chunk has:
allowed_roles = ["employee", "manager", "hr"]

and the user's roles are:
roles = ["employee"]

There is an intersection:
employee ∩ [employee, manager, hr]

Therefore, the user can potentially access the chunk.

But imagine another chunk:
allowed_roles = ["hr"]

The employee has:
roles = ["employee"]

There is no intersection.

Therefore:
employee ∩ hr = ∅

and the user should not receive that chunk.
10. Perform semantic similarity search
N["find_nearest(embedding)"]

After applying the database filters, the system performs vector similarity search.

It essentially asks:
"Among the chunks belonging to this tenant and accessible to this role, which ones are most similar to the user's question?"

For example, the question:
"What is the company's leave policy?"

might retrieve chunks discussing:
Annual leave
Sick leave
Leave approval
Leave requests

The important point is that the vector search is happening after authorization-related filtering, rather than blindly searching every document in the database.
11. Convert database results into Chunk objects
O["For each result: parse snapshot as Chunk"]

Firestore returns database records/snapshots.

The system converts each result into your application's Chunk model.

Conceptually:
Firestore document
        ↓
     Chunk

A chunk might contain:
chunk_id
document_id
tenant_id
text
allowed_roles

For example:
chunk_id = "CHUNK-001"
document_id = "DOC-TENA-002"
tenant_id = "tenant-a"
allowed_roles = ["employee"]
text = "Employees may request annual leave..."

12. Validate chunk metadata
P{"Chunk metadata valid?"}

The system checks whether the chunk contains valid metadata.

For example:
- Does it have a tenant ID?
- Does it have a document ID?
- Does it contain allowed roles?
- Is the text valid?
- Is the metadata correctly formatted?
If the metadata is invalid:

P -- No --> Q["Discard chunk"]

The chunk is simply removed from consideration.

This is safer than trusting potentially malformed database data.
13. Perform a second authorization check
R["can_access_chunk_metadata(principal, chunk)"]

Even though Firestore already filtered the results, the system performs another authorization check.

This is an important defense-in-depth mechanism.

The function essentially asks:
"Given this exact principal and this exact chunk, is access allowed?"

It checks things such as:
principal.tenant_id == chunk.tenant_id

and:
principal.roles ∩ chunk.allowed_roles != ∅

14. Tenant and role authorization
S{"Tenant and role allowed?"}

If either the tenant or role check fails:

S -- No --> Q["Discard chunk"]

The chunk is discarded.

If both succeed:

S -- Yes --> T["Keep authorized chunk"]

The chunk becomes part of the authorized context.

So there are effectively two layers of protection:
Firestore filtering
        ↓
Application-level authorization
        ↓
Authorized chunk

15. Collect authorized chunks
U["Return authorized chunks"]

The system collects all chunks that survived the validation and authorization process.

For example:
Authorized chunks:

CHUNK-001
CHUNK-004
CHUNK-007

All three should satisfy:
tenant = user's tenant
AND
allowed_roles intersects user's roles
AND
metadata is valid

16. Check whether anything was actually authorized
V{"Any authorized chunks?"}

The system asks:
"Do we have at least one chunk that this user is allowed to see?"

If not:

V -- No --> H["Return: no authorized information"]

The system does not generate an answer from unauthorized information.

This is extremely important.

For example, suppose the user asks:
"What is the salary structure for executives?"

The database might contain relevant executive compensation documents, but if the user is an ordinary employee without permission, those chunks are filtered out.

The correct result is therefore:
No authorized information is available.

Not:
"The executive salary structure is..."

17. Generate the answer
If authorized chunks exist:

V -- Yes --> W["GeminiProvider.generate_answer(query, chunks)"]

Now the system sends the question and authorized chunks to Gemini.

The important thing is that Gemini doesn't receive the entire database.

It receives only:
Question
+
Authorized context

18. Build the prompt
X["Build prompt from authorized context"]

The application constructs a prompt containing the user's question and the retrieved chunks.

Conceptually:
Question:
What is the company's leave policy?

Authorized context:
1. Employees can request annual leave...
2. Leave requests must be submitted...
3. Managers approve leave requests...

The prompt tells the model to answer using the supplied context.
19. Gemini generates the response
Y["Gemini generation model"]

Gemini processes:
User question
+
Authorized context

and generates a natural-language answer.

For example:
Employees can request annual leave through the designated HR system. Planned leave should generally be submitted in advance and requires manager approval.

20. Return the final answer
Z["Return answer"]

Finally, the generated answer is returned to the user.

So the complete flow is:
Question + User
      ↓
Validate question
      ↓
Validate Principal
      ↓
Check user roles
      ↓
Create query embedding
      ↓
Filter by tenant
      ↓
Filter by roles
      ↓
Semantic similarity search
      ↓
Validate chunks
      ↓
Re-check authorization
      ↓
Authorized chunks only
      ↓
Build AI prompt
      ↓
Gemini
      ↓
Answer

The most important security principle
The architecture is essentially enforcing this rule:
Relevance is not enough. A chunk must be both relevant AND authorized before it can reach the LLM.

For your example:
Document:
Sample leave policy

tenant_id:
tenant-a

allowed_roles:
["employee"]

Chunk:
"Employees can take 20 days of annual leave..."

If the user is:
tenant_id = tenant-a
roles = ["employee"]

then:
Tenant matches       ✓
Role matches         ✓
Chunk is relevant    ✓
→ Send to Gemini

But if the user is:
tenant_id = tenant-b
roles = ["employee"]

then:
Tenant matches       ✗
→ Discard chunk
→ Do not send to Gemini

And if the user is:
tenant_id = tenant-a
roles = ["intern"]

while the chunk allows only:
["employee"]

then:
Tenant matches       ✓
Role matches         ✗
→ Discard chunk
→ Do not send to Gemini

This prevents a major RAG security problem: retrieving unauthorized information and accidentally exposing it through an AI-generated response.