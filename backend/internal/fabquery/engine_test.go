package fabquery_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"isop-cpnt/backend/internal/fabquery"
)

func makeMockSidecar(t *testing.T, rows []map[string]interface{}) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"columns": []string{"name"},
			"rows":    rows,
		})
	}))
}

func TestEngine_AllFabsSucceed(t *testing.T) {
	srv1 := makeMockSidecar(t, []map[string]interface{}{{"name": "cpnt_a"}})
	srv2 := makeMockSidecar(t, []map[string]interface{}{{"name": "cpnt_b"}})
	defer srv1.Close()
	defer srv2.Close()

	urls := map[string]string{"F12A": srv1.URL, "F12B": srv2.URL}
	engine := fabquery.NewEngine(urls, 5)
	ch := engine.Execute(context.Background(), "SELECT name FROM cpnt", []string{"F12A", "F12B"}, nil)

	results := collect(ch)
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	for _, r := range results {
		if r.Status != "ok" {
			t.Errorf("fab %s expected ok, got %s: %s", r.Fab, r.Status, r.Error)
		}
	}
}

func TestEngine_PartialFailure(t *testing.T) {
	good := makeMockSidecar(t, []map[string]interface{}{{"name": "ok"}})
	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
		json.NewEncoder(w).Encode(map[string]string{"detail": "ORA error"})
	}))
	defer good.Close()
	defer bad.Close()

	urls := map[string]string{"F12A": good.URL, "F12B": bad.URL}
	engine := fabquery.NewEngine(urls, 5)
	ch := engine.Execute(context.Background(), "SELECT name FROM cpnt", []string{"F12A", "F12B"}, nil)

	results := collect(ch)
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	statuses := map[string]string{}
	for _, r := range results {
		statuses[r.Fab] = r.Status
	}
	if statuses["F12A"] != "ok" || statuses["F12B"] != "error" {
		t.Errorf("unexpected statuses: %v", statuses)
	}
}

func collect(ch <-chan fabquery.FabResult) []fabquery.FabResult {
	var results []fabquery.FabResult
	for r := range ch {
		results = append(results, r)
	}
	return results
}
