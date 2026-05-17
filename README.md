# ISOP Component Platform

This project follows an SDD (Specification-Driven Development) workflow:

- **OpenSpec** — Defines business logic, requirements, and use cases.
- **Superpower** — Plans implementation details and technical execution.
- **Agent-OS** — Defines development conventions, operational rules, and engineering standards.

# Architecture

```
(Angular)     (Go)         (Python)
Frontend  -> Backend -> Tsmcpy - F12A
                     -> Tsmcpy - F12B
                     -> ...
```

**Request flow:**
1. Frontend sends SQL + selected fabs
2. Backend validates (SELECT-only) → wraps ROWNUM → trial-runs on Test DB → returns `queryId`
3. Frontend opens SSE stream; backend fans out one goroutine per fab
4. Each goroutine calls its sidecar → results streamed back as `fab_result` events
5. Final `done` event closes the stream

---

# ● Running the Backend

## Start with Docker Compose

```bash
# Build images and start all services
docker compose up --build

# Run in background
docker compose up --build -d

# Rebuild After Code Changes
docker compose up --build backend
```

Services started:

| Service | Port | Description |
|---------|------|-------------|
| `backend` | 8080 | Go API server |
| `sidecar-test` | 8001 | Python Oracle adapter (Test DB) |

## Stop Services

```bash
docker compose down

# Also remove volumes (if any)
docker compose down -v
```

## Run Without Docker (local Go)

```bash
cd backend
go run ./cmd/server
```

## Swagger UI

Open **http://localhost:8080/swagger/index.html** to explore and try all endpoints interactively.

| URL | Description |
|-----|-------------|
| `/swagger/index.html` | Swagger UI |
| `/swagger/doc.json` | Raw OpenAPI spec (JSON) |

- Regenerate docs after changing annotations
```bash
cd backend
swag init -g cmd/server/main.go -o docs
```

## Run Tests

```bash
cd backend
go test ./...

# Verbose output
go test ./... -v

# Single package
go test ./tests/fabquery/ -v
go test ./tests/console/ -v
```
