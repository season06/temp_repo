package fabquery_test

import (
	"strings"
	"testing"
	"isop-cpnt/backend/internal/fabquery"
)

func TestWrapWithRownum(t *testing.T) {
	sql := "SELECT name FROM cpnt"
	wrapped := fabquery.WrapWithRownum(sql, 100)

	if !strings.Contains(wrapped, "WHERE ROWNUM <= 100") {
		t.Errorf("missing ROWNUM clause, got: %s", wrapped)
	}
	if !strings.Contains(wrapped, "SELECT name FROM cpnt") {
		t.Errorf("original SQL missing from wrap, got: %s", wrapped)
	}
	// Outer SELECT must wrap the inner
	if !strings.HasPrefix(strings.TrimSpace(wrapped), "SELECT * FROM") {
		t.Errorf("wrapped SQL should start with SELECT * FROM, got: %s", wrapped)
	}
}

func TestWrapWithRownumLimit(t *testing.T) {
	wrapped := fabquery.WrapWithRownum("SELECT 1 FROM dual", 42)
	if !strings.Contains(wrapped, "ROWNUM <= 42") {
		t.Errorf("expected limit 42, got: %s", wrapped)
	}
}
