
### Example: `Document_RAG_Workflow`

Index a text chunk into pgvector, run a semantic search, and answer a question — all in one synchronous call.

**Input parameters:**

| Field | Type | Description |
|---|---|---|
| `text` | string | Document text to embed and index |
| `docId` | string | Unique identifier for this document chunk |
| `question` | string | Question to answer from the indexed content |

**Output parameters:**

| Field | Description |
|---|---|
| `search_results` | List of matching chunks with scores and metadata |
| `answer` | LLM-generated answer grounded in the retrieved context |

```bash
curl -X POST "http://localhost:8000/api/workflow/execute/Document_RAG_Workflow/1" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "docId": "doc-001",
      "text": "Conductor is a distributed workflow orchestration platform. It supports vector databases like pgvector, MongoDB, and Pinecone for AI-powered RAG pipelines.",
      "question": "What vector databases does Conductor support?"
    }
  }'
```

Register or update the definition first if needed:

```bash
curl -X PUT http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d "[$(cat workflows/docs_retrieval.json)]"
```
