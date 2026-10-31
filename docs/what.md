What we’re building
We’re building a permission-aware, multi-tenant RAG system: an application that answers questions using company documents while enforcing who is allowed to see each document.

RAG means the system retrieves relevant pieces of information—called chunks—and gives them to an AI model to help form an answer. In our project:
Each company’s data is kept within its tenant boundary.
Documents and chunks carry access metadata, such as which roles may read them.
When a user asks a question, the system verifies their identity and permissions.
It searches only within the documents they’re authorized to access.
It sends only those permitted chunks to the AI model.
It records an audit trail of which resources were retrieved for which user.

The system is more than a chatbot over documents: authorization is part of retrieval, not something left to the model or added after search.

Why it matters
Company documents often contain sensitive information—HR files, customer records, financial plans, or internal engineering details. If a RAG system retrieves an unauthorized document, even once, it could expose that information in an answer. A tenant boundary failure could expose one company’s data to another.

The AI model cannot reliably enforce access rules on its own. Telling it “don’t reveal confidential information” is not a security control. The application must prevent unauthorized content from reaching the model in the first place.

Auditing also matters: teams need to investigate what information was retrieved, for whom, and under which permissions. That helps with incident response and operational accountability.

We’re learning to build these protections step by step, starting with the security model in SECURITY_MODEL.md.