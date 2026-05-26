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
		// 合法
		{"SELECT id FROM cpnt", true},
		{"select name FROM sop WHERE id = :id", true},
		{"  \n  SELECT col FROM tbl", true},
		{"WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte", true},
		{"WITH cte AS (SELECT id FROM cpnt) SELECT id FROM cte", true},
		// 非 SELECT 開頭
		{"INSERT INTO cpnt VALUES (1)", false},
		{"UPDATE cpnt SET name = 'x'", false},
		{"DELETE FROM cpnt", false},
		{"DROP TABLE cpnt", false},
		{"CREATE TABLE x (id NUMBER)", false},
		{"MERGE INTO t USING s ON (t.id=s.id) WHEN MATCHED THEN UPDATE SET t.v=s.v", false},
		// WITH + 非 SELECT 主語句
		{"WITH cte AS (SELECT 1 FROM dual) DELETE FROM cpnt", false},
		{"WITH cte AS (SELECT 1 FROM dual) UPDATE cpnt SET name = 'x'", false},
		{"WITH cte AS (SELECT 1 FROM dual) INSERT INTO cpnt VALUES (1)", false},
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

func TestValidateNoStarColumns(t *testing.T) {
	cases := []struct {
		sql   string
		valid bool
	}{
		// 合法
		{"SELECT id, name FROM cpnt", true},
		{"SELECT price * 2 FROM tbl", true},
		{"SELECT (a+b) * c FROM tbl", true},
		{"SELECT a * b FROM tbl", true},
		{"SELECT ROWNUM * 2 FROM cpnt", true},
		{"SELECT a * -b FROM tbl", true},
		// column wildcard
		{"SELECT * FROM cpnt", false},
		{"SELECT t.* FROM cpnt t", false},
		{"SELECT COUNT(*) FROM cpnt", false},
		{"SELECT *, id FROM cpnt", false},
		// 子查詢
		{"SELECT col FROM (SELECT * FROM tbl)", false},
		// CTE
		{"WITH cte AS (SELECT * FROM t) SELECT id FROM cte", false},
		{"WITH cte AS (SELECT t.* FROM t) SELECT id FROM cte", false},
	}
	for _, c := range cases {
		err := fabquery.ValidateNoStarColumns(c.sql)
		if c.valid && err != nil {
			t.Errorf("expected valid for %q, got: %v", c.sql, err)
		}
		if !c.valid && err == nil {
			t.Errorf("expected invalid for %q, got nil error", c.sql)
		}
	}
}
