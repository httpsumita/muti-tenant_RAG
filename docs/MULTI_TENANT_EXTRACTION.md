# How Multi-Tenant Extraction Works

## The short version

This public demo has no user sign-in. Every visitor receives the same fixed server-side principal: `tenant-a` with the `employee` role. Only matching chunks can be sent to Gemini. Therefore all employee-readable Tenant A content must be intentionally public.

## The flow

1. **Open the public chat.** Visitors do not create accounts or sign in.
2. **Assign the demo principal.** Server code fixes the tenant to `tenant-a` and the role to `employee`; visitors cannot choose either.
3. **Mark every chunk.** Each stored document chunk has a `tenant_id` and `allowed_roles` alongside its text and embedding. These fields say which tenant owns it and which roles may read it.
4. **Find relevant chunks inside the access boundary.** The question is converted to an embedding. Firestore filters chunks by `tenant-a` and `employee` before doing the similarity search.
5. **Check the returned chunks again.** The server validates each chunk's metadata and rechecks its tenant and role. Missing or invalid access information means the chunk is discarded.
6. **Send only permitted chunks to Gemini.** If no chunks survive, the app returns that it found no information the user is authorized to access. It does not send other tenants' or roles' text to Gemini.

## Picture

```text
Public visitor
      -> fixed tenant-a / employee principal
      -> Firestore filters tenant + roles
      -> similarity search within those filters
      -> validate and check each chunk again
      -> authorized chunks only -> Gemini
```

## Why it protects tenants

All tenants' chunks can live in the same Firestore collection. The tenant and role filters are part of the database search, so a chunk from another tenant or an unapproved role is not a candidate for the answer. A second check in the application provides another layer of protection.

In the demo dataset, Tenant A contains professional experience, while Tenant B contains education and recognition details. A public Tenant A visitor cannot retrieve those education chunks, even if they are relevant to the question. All employee-readable Tenant A content is public.

The app uses the Firebase Admin SDK on the server, which bypasses Firestore Security Rules. That is why the server-side filters and checks must remain in place. If Firestore cannot apply the required filters or the vector index is not ready, the search should fail rather than retrying without filters.
