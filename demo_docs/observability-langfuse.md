# Langfuse Observability

The observability layer writes RAG traces to Langfuse through an internal SDK. The core pipeline only depends on a tracer interface, so Langfuse can be replaced or disabled without changing retrieval logic.

Each query should record the original query, normalized query, metadata filters, retrieved chunks, retrieval scores, rerank model, rerank scores, selected chunks, context token count, citations, latency, and error details.

If Langfuse is unavailable, the pipeline should degrade to local JSON logs instead of failing the user request.

