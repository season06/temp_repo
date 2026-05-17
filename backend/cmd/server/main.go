package main

import (
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"isop-cpnt/backend/internal/config"
	"isop-cpnt/backend/internal/console"
	"isop-cpnt/backend/internal/fabquery"
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

	log.Printf("listening on :%s", cfg.Port)
	log.Fatal(http.ListenAndServe(":"+cfg.Port, r))
}
