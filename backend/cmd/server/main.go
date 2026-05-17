// Package main is the SQL Console API server.
//
// @title           SQL Console API
// @version         1.0
// @description     Multi-fab plain SQL query interface with SSE streaming. Validates SELECT-only queries, wraps ROWNUM, trial-runs on Test DB, then fans out goroutines per Fab.
// @host            localhost:8080
// @BasePath        /
package main

import (
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	httpSwagger "github.com/swaggo/http-swagger/v2"
	"isop-cpnt/backend/internal/config"
	"isop-cpnt/backend/internal/console"
	"isop-cpnt/backend/internal/fabquery"

	_ "isop-cpnt/backend/docs"
)

func main() {
	cfg := config.FromEnv()

	engine := fabquery.NewEngine(cfg.SidecarURLs, 30)
	testDB := fabquery.NewTestDBClient(cfg.TestDBURL, 5)
	templates, err := console.LoadTemplates("config/context_sqls.yaml")
	if err != nil {
		log.Fatalf("failed to load context SQL templates: %v", err)
	}

	h := console.NewHandler(engine, testDB, templates)

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Post("/api/fabs/query", h.Execute)
	r.Get("/api/fabs/stream/{id}", h.Stream)
	r.Get("/api/console/templates", h.Templates)

	r.Get("/swagger/*", httpSwagger.Handler(
		httpSwagger.URL("/swagger/doc.json"),
	))

	log.Printf("listening on :%s  — Swagger UI: http://localhost:%s/swagger/index.html", cfg.Port, cfg.Port)
	log.Fatal(http.ListenAndServe(":"+cfg.Port, r))
}
