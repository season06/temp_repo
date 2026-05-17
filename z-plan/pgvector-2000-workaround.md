# Workaround: pgvector + Conductor with text-embedding-3-large (3072 dims)

## Problem

Conductor's `LLM_INDEX_TEXT` task hardcodes HNSW index creation when seeding documents into pgvector.
pgvector's HNSW (and IVFFlat) indexes both have a hard cap of **2000 dimensions**, so using
`text-embedding-3-large` (3072 dims) fails at two points:

| Step | Error |
|---|---|
| Index creation | `column cannot have more than 2000 dimensions for hnsw index` |
| Embedding insert | `Embeddings must be of dimensions: 1536` |

Conductor source: `PostgresVectorDB.java` `createVectorIndexIfNotExists()` — only supports
`"hnsw"` (default) and `"ivfflat"` via `indexingMethod` config. No `"none"` option exists.

---

## Workaround (3 steps)

### Step 1 — Recreate the table with vector(3072)

Drop the existing table (which was created with `vector(1536)`) and recreate it with the correct
dimension. No vector index — Conductor will fall back to sequential scan.

```sql
DROP TABLE IF EXISTS runbooks;

CREATE TABLE runbooks (
  id            VARCHAR(255) NOT NULL,
  parent_doc_id VARCHAR(255) NOT NULL,
  embedding     vector(3072),
  doc           TEXT         NOT NULL,
  metadata      TEXT         NOT NULL,
  PRIMARY KEY (id)
);
```

```bash
docker exec conductor-pgvector psql -U conductor -d conductor_vectors -c "
DROP TABLE IF EXISTS runbooks;
CREATE TABLE runbooks (
  id VARCHAR(255) NOT NULL, parent_doc_id VARCHAR(255) NOT NULL,
  embedding vector(3072), doc TEXT NOT NULL, metadata TEXT NOT NULL,
  PRIMARY KEY (id)
);"
```

### Step 2 — Pre-create a dummy index named `incidents`

Conductor calls `CREATE INDEX IF NOT EXISTS incidents ON runbooks USING hnsw (...)`.
PostgreSQL's `IF NOT EXISTS` checks by **index name only** — if an index named `incidents`
already exists (of any type), the statement is silently skipped.

Create a cheap btree index with the same name to block the HNSW attempt:

```sql
CREATE INDEX incidents ON runbooks (id);
```

```bash
docker exec conductor-pgvector psql -U conductor -d conductor_vectors -c "
CREATE INDEX incidents ON runbooks (id);"
```

### Step 3 — Update Conductor config and restart

`config-redis.properties` validates embedding dimensions on insert. Change the `dimensions`
property to match the model:

```properties
# docker/server/config/config-redis.properties
conductor.vectordb.instances[0].postgres.dimensions=3072   # was 1536
conductor.vectordb.instances[0].postgres.indexingMethod=hnsw  # unchanged — blocked by step 2
```

Then restart the server to pick up the new config:

```bash
cd docker && docker compose restart conductor-server
```

---

## Verification

After all 3 steps, seed runbooks with `text-embedding-3-large`:

```bash
# Confirm 4 rows with 3072-dim embeddings (emb_len ≈ 38000+ chars)
docker exec conductor-pgvector psql -U conductor -d conductor_vectors -c "
SELECT id, length(embedding::text) AS emb_len FROM runbooks ORDER BY id;"
```

Expected output:

```
                id                | emb_len
----------------------------------+---------
 runbook_high_cpu_usage           |   38931
 runbook_high_memory_usage        |   38924
 runbook_kube_deployment_mismatch |   38914
 runbook_pod_oomkilled            |   38890
```

---

## Trade-offs

| | With HNSW index | This workaround |
|---|---|---|
| Index type | HNSW (ANN) | None (sequential scan) |
| Query speed | O(log n) | O(n) |
| Max dims | 2000 | Unlimited |
| Suitable for | Production (millions of docs) | POC / small doc sets |

For production with 3072-dim embeddings, options are:
- Upgrade pgvector when HNSW 3072-dim support lands
- Use `text-embedding-3-large` with `dimensions=1536` (OpenAI truncation) — restore HNSW
- Switch to a vector DB without the dim limit (e.g. Weaviate, Qdrant)
