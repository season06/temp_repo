package fabquery

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type TestDBClient struct {
	url     string
	timeout time.Duration
}

func NewTestDBClient(url string, timeoutSeconds int) *TestDBClient {
	return &TestDBClient{url: url, timeout: time.Duration(timeoutSeconds) * time.Second}
}

func (c *TestDBClient) TryRun(ctx context.Context, sql string, params map[string]interface{}) error {
	if params == nil {
		params = map[string]interface{}{}
	}
	body, _ := json.Marshal(map[string]interface{}{"sql": sql, "params": params})

	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, c.url+"/query", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("query too slow: exceeded %s timeout on test DB", c.timeout)
		}
		return fmt.Errorf("test DB unreachable: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errBody struct {
			Detail string `json:"detail"`
		}
		json.NewDecoder(resp.Body).Decode(&errBody)
		return fmt.Errorf("test DB rejected query: %s", errBody.Detail)
	}
	return nil
}
