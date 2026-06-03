# Security And Tenancy

Tenant isolation is a first-class requirement. Each chunk stores `tenant_id`, `document_id`, `chunk_id`, source URI, section path, page number, and ACL metadata.

Retrieval must apply tenant filters and ACL metadata filters before context assembly. A user should only retrieve chunks from documents they are allowed to access.

The RAG Adapter keeps retrieval scores and rerank scores in the trace so engineers can debug why a chunk was selected. This is especially important for permission-sensitive enterprise search.

