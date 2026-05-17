package fabquery_test

import (
	"testing"
	"isop-cpnt/backend/internal/fabquery"
)

func TestValidateSelectOnly(t *testing.T) {
	cases := []struct {
		sql   string
		valid bool
	}{
		{"SELECT * FROM cpnt", true},
		{"select name from sop WHERE id = :id", true},
		{"WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte", true},
		{"  \n  SELECT col FROM tbl", true}, // leading whitespace
		{"INSERT INTO cpnt VALUES (1)", false},
		{"UPDATE cpnt SET name = 'x'", false},
		{"DELETE FROM cpnt", false},
		{"DROP TABLE cpnt", false},
		{"CREATE TABLE x (id NUMBER)", false},
		{"MERGE INTO t USING s ON (t.id=s.id) WHEN MATCHED THEN UPDATE SET t.v=s.v", false},
	}
	for _, c := range cases {
		err := fabquery.ValidateSelectOnly(c.sql)
		if c.valid && err != nil {
			t.Errorf("expected valid for %q, got: %v", c.sql, err)
		}
		if !c.valid && err == nil {
			t.Errorf("expected invalid for %q, got nil error", c.sql)
		}
	}
}
