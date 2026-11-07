# Permission-Aware Multi-Tenant RAG

A learning project for building a production-minded RAG service where tenant boundaries and document permissions are enforced before retrieved content reaches a model.

## Learning path

We will build this in small, reviewable steps. Each completed step gets a short entry in [docs/BUILD_LOG.md](docs/BUILD_LOG.md).

1. Define security invariants and architecture.
2. Build the Streamlit interface and establish local development.
3. Add tenant-scoped Firestore data and (for authenticated deployments) Firebase Authentication.
4. Ingest documents and persist chunk-level access metadata.
5. Implement permission-filtered retrieval and prove denied chunks never reach Gemini.
6. Add audit events, retention, and integrity controls.
7. Add adversarial tests, observability, deployment hardening, and operational runbooks.

## Initial technology direction

Python + Streamlit for the learning app, Cloud Firestore for chunk storage/vector search, and Gemini for embeddings and answer generation. The current public demo has no visitor authentication; Firebase Authentication utilities remain for operator scripts. Local development should use synthetic data only. Firebase Admin credentials and Gemini API keys must stay outside source control.

## Security is a design constraint

Tenant filtering and authorization are server-side requirements, not prompt instructions. Retrieval must be authorized in the database query before any chunk content is returned to application/model code. See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Run the UI scaffold

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the interface with `streamlit run app.py`.

The Streamlit app is a public demo: no user sign-in or account creation is required. When a visitor opens chat, the server assigns a fixed `tenant-a` / `employee` principal and runs tenant- and role-filtered Firestore vector search before Gemini generation. This means anyone can query all employee-readable Tenant A content and use the app owner's Gemini quota. Keep only intentionally public, non-sensitive data in Tenant A; Tenant B remains excluded. Browser upload UI is not implemented; the operator-run seed command below populates Firestore.

For local setup, set `FIREBASE_PROJECT_ID` and `GEMINI_API_KEY` in the ignored root `.env` file or in valid TOML at `.streamlit/secrets.toml`. The app loads `.env` at startup. For local Firestore access, complete `gcloud auth application-default login` and grant the ADC identity `Cloud Datastore User` (`roles/datastore.user`) on the project.

For Cloud Run, assign a dedicated runtime service account with `Cloud Datastore User` on the Firebase project. Cloud Run provides Application Default Credentials automatically, so no service-account key is needed. Set `FIREBASE_PROJECT_ID` and `GEMINI_API_KEY` as environment variables/secrets. Streamlit Community Cloud does not provide Google Cloud ADC; using it requires a service-account key in Streamlit Secrets, if your organization permits key creation.

```toml
FIREBASE_PROJECT_ID = "your-firebase-project-id"
GEMINI_API_KEY = "your-gemini-api-key"
```

### Operator provisioning

The public demo does not create user accounts or memberships. The following command remains available for administrative tenant provisioning and is not part of visitor sign-in.

Operators can also bootstrap or recover a tenant using a Firebase Authentication UID and the command:

```powershell
.\.venv\Scripts\python.exe provision_tenant.py --tenant-id acme --name "Acme" --firebase-uid FIREBASE_AUTH_UID --role reader
```

Replace the sample tenant values and UID. The command atomically creates `tenants/{tenant_id}` and `memberships/{firebase_uid}` and refuses to overwrite either. It does not accept or store passwords.

### Seed the resume and two tenants

The fake `knowledge/policy.txt` has been removed. The contact-redacted professional profile is stored in `knowledge/tenant-a-resume.txt`; education details are stored separately in `knowledge/tenant-b-education.txt` and seeded only into `tenant-b`. Tenant A's resume source and chunks do not contain the education section.

Create the embeddings and Firestore chunks with:

```powershell
.\.venv\Scripts\python.exe seed_demo_data.py --replace-legacy-policy
```

The command embeds Tenant A's professional profile and Tenant B's education record, then writes chunk tenant/role metadata. It does not create user accounts or memberships. The replacement flag removes only the known `DOC-TENA-001` fake policy metadata and chunks from `tenant-a`. It does not touch same-ID content in another tenant. The script makes live Firestore writes and Gemini embedding requests; unit tests use mocks and do not perform those writes.

# gcloud.cmd auth application-default login

The prefiltered vector query requires the composite index in [firestore.indexes.json](firestore.indexes.json). The Firebase CLI config is in [firebase.json](firebase.json); the configured project has the tenant-filtered vector index. If its status is `CREATING`, wait until it is `READY` before testing chat. Chunks must be stored in the `chunks` collection with `tenant_id`, `allowed_roles`, `embedding` (768 dimensions), `document_id`, `chunk_index`, and `text` fields. The public app constructs a fixed server-side `Principal` for Tenant A's `employee` role.

Run the unit tests with `.venv\Scripts\python.exe -m unittest discover -s tests -v` on Windows. The retrieval tests use fake Firestore and Gemini clients and do not require cloud access.

## Current status

The public demo uses a fixed Tenant A `employee` principal and has no visitor sign-in. The two-tenant seeder does not create user accounts or memberships. Tenant A content is public; Tenant B remains excluded. Whether the seed command has run and whether live vector retrieval/Gemini work must be checked in the target project. Browser upload UI and persistent audit writes are not implemented.


The key idea is:
Assign the fixed public demo principal → retrieve only matching Tenant A employee chunks → verify permissions again → generate an answer only from those chunks.

1. User sends a question
A["Question + Principal"] → B["answer_question()"]

The system receives two things:
- Question — what the visitor wants to know.
- Principal — a fixed server-side public-demo authorization context.
For example:
Question:
"What is the company's leave policy?"

Principal:
tenant_id = "tenant-a"
roles = ["employee"]

The principal fixes the visitor's access to Tenant A's `employee`-allowed chunks; the visitor cannot select a tenant or role.
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