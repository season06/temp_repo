package console

import (
	"context"
	"encoding/json"
	"net/http"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"isop-cpnt/backend/internal/fabquery"
)

type TestDB interface {
	TryRun(ctx context.Context, sql string, params map[string]interface{}) error
}

type storedQuery struct {
	wrappedSQL  string
	fabs        []string
	namedParams map[string]interface{}
	expiresAt   time.Time
}

type Handler struct {
	engine    *fabquery.Engine
	testDB    TestDB
	templates []SqlTemplate
	// sync.Map is used instead of map+mutex because Execute and Stream
	// are called concurrently from different HTTP goroutines.
	// Entries are deleted lazily on Stream access; never-streamed queries
	// leak until the process restarts (known limitation, see CR-03).
	store sync.Map // queryID -> storedQuery
}

func NewHandler(engine *fabquery.Engine, testDB TestDB, templates []SqlTemplate) *Handler {
	return &Handler{engine: engine, testDB: testDB, templates: templates}
}

type executeRequest struct {
	SQL         string                 `json:"sql"`
	Fabs        []string               `json:"fabs"`
	RowLimit    int                    `json:"rowLimit"`
	NamedParams map[string]interface{} `json:"namedParams"`
}

type executeResponse struct {
	QueryID string `json:"queryId"`
}

type errorResponse struct {
	Error string `json:"error"`
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

// Execute submits a SQL query for multi-fab execution.
//
// @Summary     Submit SQL query
// @Description Validates the SQL (SELECT-only), wraps ROWNUM, trial-runs on Test DB, and returns a queryId for SSE streaming.
// @Tags        query
// @Accept      json
// @Produce     json
// @Param       body body     executeRequest  true "Query request"
// @Success     200  {object} executeResponse
// @Failure     400  {object} errorResponse
// @Router      /api/fabs/query [post]
func (h *Handler) Execute(w http.ResponseWriter, r *http.Request) {
	// Parameter validate
	var req executeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, 400, errorResponse{"invalid request body"})
		return
	}
	if err := fabquery.ValidateSelectOnly(req.SQL); err != nil {
		writeJSON(w, 400, errorResponse{err.Error()})
		return
	}
	if len(req.Fabs) == 0 {
		writeJSON(w, 400, errorResponse{"at least one fab required"})
		return
	}
	if req.RowLimit <= 0 {
		req.RowLimit = 100
	}
	if req.RowLimit > 300 {
		writeJSON(w, 400, errorResponse{"rowLimit max is 300"})
		return
	}

	// Content Pre-process
	wrappedSQL := fabquery.WrapWithRownum(req.SQL, req.RowLimit)

	// Dry-run with test db
	if err := h.testDB.TryRun(r.Context(), wrappedSQL, req.NamedParams); err != nil {
		writeJSON(w, 400, errorResponse{err.Error()})
		return
	}

	queryID := uuid.New().String()
	h.store.Store(queryID, storedQuery{
		wrappedSQL:  wrappedSQL,
		fabs:        req.Fabs,
		namedParams: req.NamedParams,
		expiresAt:   time.Now().Add(5 * time.Minute),
	})

	writeJSON(w, 200, executeResponse{queryID})
}

// Templates returns the list of context SQL templates.
//
// @Summary     List SQL templates
// @Description Returns pre-configured SQL templates from context_sqls.yaml.
// @Tags        templates
// @Produce     json
// @Success     200 {array} SqlTemplate
// @Router      /api/console/templates [get]
func (h *Handler) Templates(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, 200, h.templates)
}

// Stream streams per-fab query results as Server-Sent Events.
//
// @Summary     Stream query results (SSE)
// @Description Opens an SSE stream for the given queryId. Emits fab_result or fab_error events per fab, then a done event.
// @Tags        query
// @Produce     text/event-stream
// @Param       id path     string true "Query ID returned by POST /api/fabs/query"
// @Success     200 {string} string "SSE stream"
// @Failure     404 {object} errorResponse
// @Router      /api/fabs/stream/{id} [get]
func (h *Handler) Stream(w http.ResponseWriter, r *http.Request) {
	queryID := chi.URLParam(r, "id")

	val, ok := h.store.Load(queryID)
	if !ok {
		writeJSON(w, 404, errorResponse{"query not found or expired"})
		return
	}
	q := val.(storedQuery)
	if time.Now().After(q.expiresAt) {
		h.store.Delete(queryID)
		writeJSON(w, 404, errorResponse{"query expired, please re-execute"})
		return
	}

	fabquery.SetSSEHeaders(w)

	// Parallel query execution
	resultCh := h.engine.Execute(r.Context(), q.wrappedSQL, q.fabs, q.namedParams)
	for result := range resultCh {
		if result.Status == "error" {
			fabquery.WriteSSEEvent(w, "fab_error", map[string]string{
				"fab":     result.Fab,
				"message": result.Error,
			})
		} else {
			fabquery.WriteSSEEvent(w, "fab_result", result) // Push to browser immediately
		}
	}
	fabquery.WriteSSEEvent(w, "done", map[string]string{"status": "complete"})
}
