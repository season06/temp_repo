package fabquery

import "fmt"

func WrapWithRownum(sql string, limit int) string {
	return fmt.Sprintf("SELECT * FROM (\n  %s\n) WHERE ROWNUM <= %d", sql, limit)
}
