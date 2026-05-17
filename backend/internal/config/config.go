package config

import "os"

var ValidFabs = []string{
	"F12A", "F12B", "F14A", "F14B", "F15A", "F15B",
	"F16", "F18A", "F18B", "F21", "F22", "F23", "APOD", "SOIC",
}

type AppConfig struct {
	SidecarURLs map[string]string // fab -> http://host:port
	TestDBURL   string
	Port        string
}

func FromEnv() AppConfig {
	urls := make(map[string]string)
	for _, fab := range ValidFabs {
		key := "SIDECAR_" + fab + "_URL"
		urls[fab] = envOr(key, "http://localhost:8000")
	}
	return AppConfig{
		SidecarURLs: urls,
		TestDBURL:   envOr("SIDECAR_TEST_URL", "http://localhost:8001"),
		Port:        envOr("PORT", "8080"),
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
