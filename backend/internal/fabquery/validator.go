package fabquery

import (
	"fmt"
	"strings"
)

// ValidateSelectOnly rejects non-SELECT statements.
// Uses prefix matching instead of a SQL parser to avoid Oracle-specific syntax incompatibilities.
func ValidateSelectOnly(sql string) error {
	upper := strings.TrimSpace(strings.ToUpper(sql))
	if strings.HasPrefix(upper, "SELECT") || strings.HasPrefix(upper, "WITH") {
		return nil
	}
	return fmt.Errorf("only SELECT queries are allowed")
}
