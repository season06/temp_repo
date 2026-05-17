package console_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
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
