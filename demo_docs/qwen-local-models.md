# Local Qwen Models

The RAG Adapter is designed for local-first deployment. The embedding model is Qwen embedding and the vector dimension is 4096.

Every indexed chunk stores metadata for `embedding_provider`, `embedding_model`, `embedding_dimension`, and `embedding_version`. This makes index rebuilds safer when the model changes.

The Qwen embedder adapter sends batch embedding requests to a local model endpoint. The adapter validates that each returned embedding has exactly 4096 dimensions before writing vectors into the vector store.

