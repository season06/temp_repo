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
	store     sync.Map // queryID -> storedQuery
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

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func (h *Handler) Execute(w http.ResponseWriter, r *http.Request) {
	var req executeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid request body"})
		return
	}
	if err := fabquery.ValidateSelectOnly(req.SQL); err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}
	if len(req.Fabs) == 0 {
		writeJSON(w, 400, map[string]string{"error": "at least one fab required"})
		return
	}
	if req.RowLimit <= 0 {
		req.RowLimit = 100
	}
	if req.RowLimit > 300 {
		writeJSON(w, 400, map[string]string{"error": "rowLimit max is 300"})
		return
	}

	wrappedSQL := fabquery.WrapWithRownum(req.SQL, req.RowLimit)

	if err := h.testDB.TryRun(r.Context(), wrappedSQL, req.NamedParams); err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}

	queryID := uuid.New().String()
	h.store.Store(queryID, storedQuery{
		wrappedSQL:  wrappedSQL,
		fabs:        req.Fabs,
		namedParams: req.NamedParams,
		expiresAt:   time.Now().Add(5 * time.Minute),
	})

	writeJSON(w, 200, map[string]string{"queryId": queryID})
}

func (h *Handler) Templates(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, 200, h.templates)
}

func (h *Handler) Stream(w http.ResponseWriter, r *http.Request) {
	queryID := chi.URLParam(r, "id")

	val, ok := h.store.Load(queryID)
	if !ok {
		writeJSON(w, 404, map[string]string{"error": "query not found or expired"})
		return
	}
	q := val.(storedQuery)
	if time.Now().After(q.expiresAt) {
		h.store.Delete(queryID)
		writeJSON(w, 404, map[string]string{"error": "query expired, please re-execute"})
		return
	}

	fabquery.SetSSEHeaders(w)

	resultCh := h.engine.Execute(r.Context(), q.wrappedSQL, q.fabs, q.namedParams)
	for result := range resultCh {
		if result.Status == "error" {
			fabquery.WriteSSEEvent(w, "fab_error", map[string]string{
				"fab":     result.Fab,
				"message": result.Error,
			})
		} else {
			fabquery.WriteSSEEvent(w, "fab_result", result)
		}
	}
	fabquery.WriteSSEEvent(w, "done", map[string]string{"status": "complete"})
}
