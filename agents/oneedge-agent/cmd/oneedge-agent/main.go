package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"os"
	"os/signal"
	"time"

	"github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/log"
	mqtt "github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/mqtt"
	spiffe "github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/spiffe"
)

const (
	defaultBroker = "localhost:8883"
	defaultTopic  = "sensors/dev/agent/telemetry"
)

func main() {
	logger := log.New()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	manager, err := spiffe.NewManager(ctx, logger)
	if err != nil {
		logger.Error("failed to initialise SPIFFE manager", slog.String("err", err.Error()))
		os.Exit(1)
	}
	defer manager.Close()

	updates := manager.Updates()
	go func() {
		if err := manager.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("spire workload watch ended", slog.String("err", err.Error()))
		}
	}()

	broker := envOrDefault("ONEEDGE_MQTT_BROKER", defaultBroker)
	topic := envOrDefault("ONEEDGE_MQTT_TOPIC", defaultTopic)

	publisher := mqtt.NewPublisher(logger, broker, topic)

	select {
	case update := <-updates:
		if update == nil {
			logger.Error("received empty SVID snapshot")
			os.Exit(1)
		}
		if err := publisher.ApplySnapshot(update); err != nil {
			logger.Error("failed to apply initial SVID", slog.String("err", err.Error()))
			os.Exit(1)
		}
	case <-time.After(10 * time.Second):
		logger.Error("timeout waiting for initial SVID")
		os.Exit(1)
	case <-ctx.Done():
		logger.Error("context cancelled before SVID ready")
		return
	}

	go func() {
		if err := publisher.Run(ctx, updates); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("publisher stopped", slog.String("err", err.Error()))
		}
	}()

	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	logger.Info("agent running", slog.String("broker", broker), slog.String("topic", topic))

	for {
		select {
		case <-ctx.Done():
			logger.Info("shutdown requested")
			return
		case now := <-ticker.C:
			payload := telemetryPayload(now)
			if err := publisher.Publish(ctx, payload); err != nil {
				logger.Warn("publish failed", slog.String("err", err.Error()))
			} else {
				logger.Info("telemetry sent")
			}
		}
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func telemetryPayload(ts time.Time) []byte {
	payload := map[string]any{
		"ts":        ts.UTC().Format(time.RFC3339Nano),
		"message":   "hello from oneedge-agent",
		"component": "oneedge-agent",
	}
	data, _ := json.Marshal(payload)
	return data
}
