package console_test

import (
	"os"
	"testing"
	"isop-cpnt/backend/internal/console"
)

func TestLoadTemplates_Success(t *testing.T) {
	yaml := `
sqls:
  - id: test-sql
    name: Test
    description: A test
    sql: SELECT 1 FROM dual
`
	f, _ := os.CreateTemp("", "*.yaml")
	f.WriteString(yaml)
	f.Close()
	defer os.Remove(f.Name())

	templates, err := console.LoadTemplates(f.Name())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(templates) != 1 || templates[0].ID != "test-sql" {
		t.Errorf("unexpected templates: %+v", templates)
	}
}

func TestLoadTemplates_MissingID(t *testing.T) {
	yaml := `
sqls:
  - name: Missing ID
    sql: SELECT 1 FROM dual
`
	f, _ := os.CreateTemp("", "*.yaml")
	f.WriteString(yaml)
	f.Close()
	defer os.Remove(f.Name())

	_, err := console.LoadTemplates(f.Name())
	if err == nil {
		t.Fatal("expected error for missing id, got nil")
	}
}
