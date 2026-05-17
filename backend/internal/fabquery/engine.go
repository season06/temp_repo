package fabquery

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

type FabResult struct {
	Fab     string                   `json:"fab"`
	Columns []string                 `json:"columns,omitempty"`
	Rows    []map[string]interface{} `json:"rows,omitempty"`
	Status  string                   `json:"status"` // "ok" | "error"
	Error   string                   `json:"error,omitempty"`
}

type Engine struct {
	sidecars map[string]string
	timeout  time.Duration
}

func NewEngine(sidecars map[string]string, timeoutSeconds int) *Engine {
	return &Engine{sidecars: sidecars, timeout: time.Duration(timeoutSeconds) * time.Second}
}

func (e *Engine) Execute(ctx context.Context, sql string, fabs []string, params map[string]interface{}) <-chan FabResult {
	if params == nil {
		params = map[string]interface{}{}
	}
	ch := make(chan FabResult, len(fabs))
	var wg sync.WaitGroup
	for _, fab := range fabs {
		wg.Add(1)
		go func(fab string) {
			defer wg.Done()
			ch <- e.queryFab(ctx, fab, sql, params)
		}(fab)
	}
	go func() {
		wg.Wait()
		close(ch)
	}()
	return ch
}

func (e *Engine) queryFab(ctx context.Context, fab, sql string, params map[string]interface{}) FabResult {
	url, ok := e.sidecars[fab]
	if !ok {
		return FabResult{Fab: fab, Status: "error", Error: fmt.Sprintf("unknown fab: %s", fab)}
	}

	ctx, cancel := context.WithTimeout(ctx, e.timeout)
	defer cancel()

	body, _ := json.Marshal(map[string]interface{}{"sql": sql, "params": params})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, url+"/query", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return FabResult{Fab: fab, Status: "error", Error: err.Error()}
	}
	defer resp.Body.Close()

	var payload struct {
		Columns []string                 `json:"columns"`
		Rows    []map[string]interface{} `json:"rows"`
		Detail  string                   `json:"detail"`
	}
	json.NewDecoder(resp.Body).Decode(&payload)

	if resp.StatusCode != http.StatusOK {
		return FabResult{Fab: fab, Status: "error", Error: payload.Detail}
	}
	return FabResult{Fab: fab, Status: "ok", Columns: payload.Columns, Rows: payload.Rows}
}
