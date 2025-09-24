package log

import (
	"log/slog"
	"os"
)

// New returns a text slog.Logger configured for stdout with timestamps.
func New() *slog.Logger {
	h := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})
	return slog.New(h)
}
