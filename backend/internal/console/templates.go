package console

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type SqlParam struct {
	Name    string      `yaml:"name"    json:"name"`
	Label   string      `yaml:"label"   json:"label"`
	Type    string      `yaml:"type"    json:"type"`
	Default interface{} `yaml:"default" json:"default"`
}

type SqlTemplate struct {
	ID          string     `yaml:"id"          json:"id"`
	Name        string     `yaml:"name"        json:"name"`
	Description string     `yaml:"description" json:"description"`
	SQL         string     `yaml:"sql"         json:"sql"`
	Params      []SqlParam `yaml:"params"      json:"params"`
}

func LoadTemplates(path string) ([]SqlTemplate, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", path, err)
	}
	var cfg struct {
		Sqls []SqlTemplate `yaml:"sqls"`
	}
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parsing %s: %w", path, err)
	}
	for i, t := range cfg.Sqls {
		if t.ID == "" {
			return nil, fmt.Errorf("template[%d] missing required field: id", i)
		}
		if t.SQL == "" {
			return nil, fmt.Errorf("template %q missing required field: sql", t.ID)
		}
	}
	return cfg.Sqls, nil
}
