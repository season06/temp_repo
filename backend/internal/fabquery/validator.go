package fabquery

import (
	"fmt"
	"strings"
)

// ValidateSelectOnly rejects non-SELECT statements.
// For WITH-prefixed SQL it traces past all CTE definitions to verify the
// final DML is SELECT, blocking WITH ... DELETE/UPDATE/INSERT bypass.
func ValidateSelectOnly(sql string) error {
	upper := strings.TrimSpace(strings.ToUpper(sql))
	switch {
	case strings.HasPrefix(upper, "SELECT") && (len(upper) == 6 || upper[6] <= ' ' || upper[6] == '('):
		return nil
	case strings.HasPrefix(upper, "WITH"):
		if dmlAfterWith(sql) == "SELECT" {
			return nil
		}
	}
	return fmt.Errorf("only SELECT queries are allowed")
}

// ValidateNoStarColumns rejects SQL that uses * as a column wildcard.
// Covers SELECT *, t.*, COUNT(*), and wildcards inside subqueries/CTEs.
// Arithmetic multiplication (price * 2) is allowed.
func ValidateNoStarColumns(sql string) error {
	toks := tokenize(sql)
	for i, t := range toks {
		if t != tkStar {
			continue
		}
		var left, right tkind = tkOther, tkOther
		if i > 0 {
			left = toks[i-1]
		}
		if i+1 < len(toks) {
			right = toks[i+1]
		}
		// arithmetic: left produces a value AND right expects a value
		if isLeftVal(left) && isRightVal(right) {
			continue
		}
		return fmt.Errorf("SELECT * is not allowed: use explicit column names")
	}
	return nil
}

// --- token scanner internals ---

type tkind uint8

const (
	tkIdent   tkind = iota // user-defined identifier (column, table, pseudo-column)
	tkKeyword              // SQL reserved word
	tkNumber               // numeric literal
	tkLParen               // (
	tkRParen               // )
	tkDot                  // .
	tkStar                 // *
	tkOther                // comma, other operators, string literals, etc.
)

// sqlKeywords is the set of SQL reserved words that are never value-producing
// and therefore cannot be the LHS of arithmetic *.
var sqlKeywords = map[string]bool{
	"SELECT": true, "FROM": true, "WHERE": true, "AND": true, "OR": true,
	"NOT": true, "IN": true, "IS": true, "AS": true, "ON": true, "BY": true,
	"SET": true, "INTO": true, "DISTINCT": true, "GROUP": true, "ORDER": true,
	"HAVING": true, "UNION": true, "INTERSECT": true, "EXCEPT": true,
	"WITH": true, "JOIN": true, "INNER": true, "LEFT": true, "RIGHT": true,
	"OUTER": true, "FULL": true, "CROSS": true, "USING": true, "CASE": true,
	"WHEN": true, "THEN": true, "ELSE": true, "END": true, "ALL": true,
	"ANY": true, "INSERT": true, "UPDATE": true, "DELETE": true, "MERGE": true,
	"CREATE": true, "DROP": true, "ALTER": true, "TRUNCATE": true,
	"BETWEEN": true, "LIKE": true, "EXISTS": true, "OVER": true,
	"PARTITION": true,
}

func isLeftVal(t tkind) bool  { return t == tkIdent || t == tkNumber || t == tkRParen }
func isRightVal(t tkind) bool { return t == tkIdent || t == tkNumber || t == tkLParen || t == tkOther }

// tokenize converts sql into a flat slice of token kinds,
// stripping comments and string literals.
func tokenize(sql string) []tkind {
	var out []tkind
	i, n := 0, len(sql)
	for i < n {
		// whitespace
		if sql[i] <= ' ' {
			i++
			continue
		}
		// line comment: --
		if i+1 < n && sql[i] == '-' && sql[i+1] == '-' {
			for i < n && sql[i] != '\n' {
				i++
			}
			continue
		}
		// block comment: /* */
		if i+1 < n && sql[i] == '/' && sql[i+1] == '*' {
			i += 2
			for i+1 < n && !(sql[i] == '*' && sql[i+1] == '/') {
				i++
			}
			if i+1 < n {
				i += 2
			}
			continue
		}
		// string literal: '...' (Oracle uses '' to escape a literal quote)
		if sql[i] == '\'' {
			i = skipString(sql, i)
			out = append(out, tkOther)
			continue
		}
		// identifier or SQL keyword
		if isIdentStart(sql[i]) {
			j := i
			for j < n && isIdentCh(sql[j]) {
				j++
			}
			word := strings.ToUpper(sql[i:j])
			if sqlKeywords[word] {
				out = append(out, tkKeyword)
			} else {
				out = append(out, tkIdent)
			}
			i = j
			continue
		}
		// number
		if sql[i] >= '0' && sql[i] <= '9' {
			for i < n && (sql[i] >= '0' && sql[i] <= '9' || sql[i] == '.') {
				i++
			}
			out = append(out, tkNumber)
			continue
		}
		// Oracle bind variable: :name → treat as identifier
		if sql[i] == ':' && i+1 < n && isIdentStart(sql[i+1]) {
			i++
			for i < n && isIdentCh(sql[i]) {
				i++
			}
			out = append(out, tkIdent)
			continue
		}
		// single-char tokens
		switch sql[i] {
		case '(':
			out = append(out, tkLParen)
		case ')':
			out = append(out, tkRParen)
		case '.':
			out = append(out, tkDot)
		case '*':
			out = append(out, tkStar)
		default:
			out = append(out, tkOther)
		}
		i++
	}
	return out
}

// dmlAfterWith returns the uppercased DML keyword of the final statement
// in a WITH-prefixed SQL, after tracing past all CTE definitions.
func dmlAfterWith(sql string) string {
	i, n := 4, len(sql) // skip "WITH"
	depth, pastCTE := 0, false

	for i < n {
		i = skipWS(sql, i)
		if i >= n {
			break
		}
		switch {
		case sql[i] == '\'':
			i = skipString(sql, i)
		case sql[i] == '(':
			depth++
			i++
		case sql[i] == ')':
			depth--
			if depth == 0 {
				pastCTE = true
			}
			i++
		case sql[i] == ',' && depth == 0:
			pastCTE = false
			i++
		case isIdentStart(sql[i]):
			j := i
			for j < n && isIdentCh(sql[j]) {
				j++
			}
			if depth == 0 && pastCTE {
				return strings.ToUpper(sql[i:j])
			}
			i = j
		default:
			i++
		}
	}
	return ""
}

func skipWS(sql string, i int) int {
	for i < len(sql) {
		switch {
		case sql[i] <= ' ':
			i++
		case i+1 < len(sql) && sql[i] == '-' && sql[i+1] == '-':
			for i < len(sql) && sql[i] != '\n' {
				i++
			}
		case i+1 < len(sql) && sql[i] == '/' && sql[i+1] == '*':
			i += 2
			for i+1 < len(sql) && !(sql[i] == '*' && sql[i+1] == '/') {
				i++
			}
			if i+1 < len(sql) {
				i += 2
			}
		default:
			return i
		}
	}
	return i
}

func skipString(sql string, i int) int {
	i++ // skip opening '
	for i < len(sql) {
		if sql[i] == '\'' {
			i++
			if i < len(sql) && sql[i] == '\'' {
				i++ // escaped ''
				continue
			}
			break
		}
		i++
	}
	return i
}

func isIdentStart(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'
}

func isIdentCh(c byte) bool {
	return isIdentStart(c) || (c >= '0' && c <= '9') || c == '$' || c == '#'
}