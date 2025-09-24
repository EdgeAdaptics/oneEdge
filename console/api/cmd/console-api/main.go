package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/EdgeAdaptics/oneEdge/console/api/internal/events"
	"github.com/EdgeAdaptics/oneEdge/console/api/internal/handlers"
	"github.com/EdgeAdaptics/oneEdge/console/api/internal/policy"
	"github.com/EdgeAdaptics/oneEdge/console/api/internal/store"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	cfg := store.Config{DSN: envOrDefault("DATABASE_URL", "postgres://oneedge:oneedge_dev_pw@localhost:5432/oneedge?sslmode=disable")}
	st, err := store.New(cfg)
	if err != nil {
		logger.Error("failed to connect to database", slog.String("err", err.Error()))
		os.Exit(1)
	}
	defer st.Close()

	bus := events.NewBus()

	quarantinePath := envOrDefault("OPA_QUARANTINE_PATH", "deploy/docker-compose/opa/bundles/oneedge/overrides/tenant/default/quarantine.json")
	policyMgr := policy.NewManager(quarantinePath)

	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60 * time.Second))

	api := handlers.New(logger, st, bus, policyMgr)
	api.Routes(r)

	srv := &http.Server{
		Addr:         ":8080",
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	if port := os.Getenv("PORT"); port != "" {
		srv.Addr = ":" + port
	}

	shutdownCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	go func() {
		logger.Info("console API starting", slog.String("addr", srv.Addr))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("listen failed", slog.String("err", err.Error()))
			stop()
		}
	}()

	<-shutdownCtx.Done()
	logger.Info("shutdown requested")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Error("server shutdown error", slog.String("err", err.Error()))
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
