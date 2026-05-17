package fabquery_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
	"isop-cpnt/backend/internal/fabquery"
)

func TestTestDBClient_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"columns": []string{"id"},
			"rows":    []map[string]interface{}{{"id": 1}},
		})
	}))
	defer srv.Close()

	client := fabquery.NewTestDBClient(srv.URL, 5)
	err := client.TryRun(context.Background(), "SELECT 1 FROM dual", nil)
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
}

func TestTestDBClient_Timeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := fabquery.NewTestDBClient(srv.URL, 0) // 0s timeout → immediate
	err := client.TryRun(context.Background(), "SELECT 1 FROM dual", nil)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
}

func TestTestDBClient_DBError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
		json.NewEncoder(w).Encode(map[string]string{"detail": "ORA-00942: table not found"})
	}))
	defer srv.Close()

	client := fabquery.NewTestDBClient(srv.URL, 5)
	err := client.TryRun(context.Background(), "SELECT * FROM no_table", nil)
	if err == nil {
		t.Fatal("expected error for DB 400, got nil")
	}
}
