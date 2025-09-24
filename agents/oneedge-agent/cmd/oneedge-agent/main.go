package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/log"
	mqtt "github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/mqtt"
	spiffe "github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent/internal/spiffe"
)

const (
	defaultBroker  = "localhost:8883"
	defaultTopic   = "sensors/dev/agent/telemetry"
	stateDirName   = ".oneedge"
	rotateFileName = "rotate.signal"
	pidFileName    = "agent.pid"
)

func main() {
	logger := log.New()

	baseCtx := context.Background()
	ctx, stop := signal.NotifyContext(baseCtx, os.Interrupt, syscall.SIGTERM)
	defer stop()

	reloadSignals := make(chan os.Signal, 1)
	signal.Notify(reloadSignals, syscall.SIGHUP)
	defer signal.Stop(reloadSignals)

	stateDir, err := ensureStateDir()
	if err != nil {
		logger.Error("failed to prepare agent state dir", slog.String("err", err.Error()))
		os.Exit(1)
	}

	if err := recordPID(stateDir); err != nil {
		logger.Warn("unable to write PID file", slog.String("err", err.Error()))
	}

	rotatePath := filepath.Join(stateDir, rotateFileName)

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

	var rotateSeen time.Time

	for {
		select {
		case <-ctx.Done():
			logger.Info("shutdown requested")
			return
		case <-reloadSignals:
			logger.Info("received SIGHUP; triggering manual rotate")
			triggerRotate(ctx, logger, manager)
		case now := <-ticker.C:
			if touched, stamp := rotateTouched(rotatePath, rotateSeen); touched {
				rotateSeen = stamp
				logger.Info("rotate signal file touched; triggering refresh")
				triggerRotate(ctx, logger, manager)
			}
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

func ensureStateDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(home, stateDirName)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	return dir, nil
}

func recordPID(dir string) error {
	pidPath := filepath.Join(dir, pidFileName)
	return os.WriteFile(pidPath, []byte(strconv.Itoa(os.Getpid())), 0o644)
}

func triggerRotate(ctx context.Context, logger *slog.Logger, manager *spiffe.Manager) {
	refreshCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := manager.Refresh(refreshCtx); err != nil {
		logger.Warn("manual refresh failed", slog.String("err", err.Error()))
	}
}

func rotateTouched(path string, last time.Time) (bool, time.Time) {
	info, err := os.Stat(path)
	if err != nil {
		return false, last
	}
	stamp := info.ModTime()
	if stamp.After(last) {
		return true, stamp
	}
	return false, last
}
