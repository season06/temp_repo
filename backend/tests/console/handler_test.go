package console_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"isop-cpnt/backend/internal/console"
	"isop-cpnt/backend/internal/fabquery"
)

// stubTestDB always succeeds or returns configured error
type stubTestDB struct{ err error }

func (s *stubTestDB) TryRun(_ context.Context, _ string, _ map[string]interface{}) error {
	return s.err
}

func newTestHandler(testDBErr error) *console.Handler {
	engine := fabquery.NewEngine(map[string]string{"F12A": "http://unused"}, 5)
	testDB := &stubTestDB{err: testDBErr}
	return console.NewHandler(engine, testDB, nil)
}

func postExecute(t *testing.T, h *console.Handler, body interface{}) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/fabs/query", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.Execute(w, req)
	return w
}

func TestExecute_NonSelectRejected(t *testing.T) {
	h := newTestHandler(nil)
	w := postExecute(t, h, map[string]interface{}{
		"sql": "DELETE FROM cpnt", "fabs": []string{"F12A"}, "rowLimit": 100,
	})
	if w.Code != 400 {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestExecute_NoFabsRejected(t *testing.T) {
	h := newTestHandler(nil)
	w := postExecute(t, h, map[string]interface{}{
		"sql": "SELECT 1 FROM dual", "fabs": []string{}, "rowLimit": 100,
	})
	if w.Code != 400 {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestExecute_RowLimitExceededRejected(t *testing.T) {
	h := newTestHandler(nil)
	w := postExecute(t, h, map[string]interface{}{
		"sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 500,
	})
	if w.Code != 400 {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestExecute_TestDBFailRejected(t *testing.T) {
	h := newTestHandler(fmt.Errorf("query too slow"))
	w := postExecute(t, h, map[string]interface{}{
		"sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 100,
	})
	if w.Code != 400 {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestExecute_ValidRequestReturnsQueryId(t *testing.T) {
	h := newTestHandler(nil)
	w := postExecute(t, h, map[string]interface{}{
		"sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 100,
	})
	if w.Code != 200 {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]string
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["queryId"] == "" {
		t.Error("expected queryId in response")
	}
}

func TestStream_SendsSSEEvents(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"columns": []string{"name"},
			"rows":    []map[string]interface{}{{"name": "cpnt_a"}},
		})
	}))
	defer srv.Close()

	engine := fabquery.NewEngine(map[string]string{"F12A": srv.URL}, 5)
	testDB := &stubTestDB{err: nil}
	h := console.NewHandler(engine, testDB, nil)

	// First: create query
	w := postExecute(t, h, map[string]interface{}{
		"sql": "SELECT name FROM cpnt", "fabs": []string{"F12A"}, "rowLimit": 10,
	})
	var execResp map[string]string
	json.NewDecoder(w.Body).Decode(&execResp)
	queryID := execResp["queryId"]

	// Then: stream it
	req := httptest.NewRequest(http.MethodGet, "/api/fabs/stream/"+queryID, nil)
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("id", queryID)
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))

	streamW := httptest.NewRecorder()
	h.Stream(streamW, req)

	body := streamW.Body.String()
	if !strings.Contains(body, "fab_result") {
		t.Errorf("expected fab_result event, got:\n%s", body)
	}
	if !strings.Contains(body, "done") {
		t.Errorf("expected done event, got:\n%s", body)
	}
}
