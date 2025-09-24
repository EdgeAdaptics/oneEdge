package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/log"
	spiffe "github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/spiffe"
)

func main() {
	logger := log.New()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	manager, err := spiffe.NewManager(ctx, logger)
	if err != nil {
		logger.Error("failed to initialise SPIFFE manager", slog.String("err", err.Error()))
		os.Exit(1)
	}
	defer manager.Close()

	svid, err := manager.Fetch(ctx)
	if err != nil {
		logger.Error("failed to fetch SVID", slog.String("err", err.Error()))
		os.Exit(1)
	}

	notAfter := svid.Certificates[0].NotAfter
	logger.Info("SVID ready", slog.String("spiffe_id", svid.ID.String()), slog.Time("not_after", notAfter), slog.Duration("ttl", time.Until(notAfter)))

	<-ctx.Done()
	logger.Info("shutdown requested, exiting")
}
