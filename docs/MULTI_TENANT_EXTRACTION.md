# How Multi-Tenant Extraction Works

## The short version

Every user's question is searched only against chunks that match the user's selected tenant and allowed roles. Only the matching chunks can be sent to Gemini.

## The flow

1. **Verify the person.** Firebase checks the sign-in token and tells the server which user signed in.
2. **Load that user's workspaces.** The server reads the user's active tenant memberships from Firestore. The tenant dropdown shows only those workspaces.
3. **Choose the current tenant.** The selection gives the server a trusted identity containing the user ID, tenant ID, and roles. A tenant ID typed by the user is not treated as proof of access.
4. **Mark every chunk.** Each stored document chunk has a `tenant_id` and `allowed_roles` alongside its text and embedding. These fields say which tenant owns it and which roles may read it.
5. **Find relevant chunks inside the access boundary.** The question is converted to an embedding. Firestore filters chunks by the selected tenant and the user's roles before doing the similarity search.
6. **Check the returned chunks again.** The server validates each chunk's metadata and rechecks its tenant and role. Missing or invalid access information means the chunk is discarded.
7. **Send only permitted chunks to Gemini.** If no chunks survive, the app returns that it found no information the user is authorized to access. It does not send other tenants' or roles' text to Gemini.

## Picture

```text
Verified sign-in
      -> user's active tenant memberships
      -> selected tenant and roles
      -> Firestore filters tenant + roles
      -> similarity search within those filters
      -> validate and check each chunk again
      -> authorized chunks only -> Gemini
```

## Why it protects tenants

All tenants' chunks can live in the same Firestore collection. The tenant and role filters are part of the database search, so a chunk from another tenant or an unapproved role is not a candidate for the answer. A second check in the application provides another layer of protection.

In the demo dataset, Tenant A contains professional experience, while Tenant B contains education and recognition details. A Tenant A principal should not receive those education chunks, even if they are relevant to the question.

The app uses the Firebase Admin SDK on the server, which bypasses Firestore Security Rules. That is why the server-side filters and checks must remain in place. If Firestore cannot apply the required filters or the vector index is not ready, the search should fail rather than retrying without filters.
