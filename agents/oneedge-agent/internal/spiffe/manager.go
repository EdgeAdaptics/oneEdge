package spiffe

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

const defaultSocket = ".devdata/spire/socket/public/api.sock"

// Manager wraps the SPIFFE Workload API client and caches the latest X509 SVID.
type Manager struct {
	log    *slog.Logger
	client *workloadapi.Client

	mu     sync.RWMutex
	svid   *workloadapi.X509SVID
	bundle *workloadapi.X509Context

	socketPath string
}

// Option mutates the Manager during construction.
type Option func(*Manager)

// WithSocket overrides the Workload API socket path.
func WithSocket(path string) Option {
	return func(m *Manager) {
		m.socketPath = path
	}
}

// NewManager creates a Manager and eagerly connects to the Workload API.
func NewManager(ctx context.Context, log *slog.Logger, opts ...Option) (*Manager, error) {
	if log == nil {
		return nil, errors.New("logger is required")
	}

	m := &Manager{log: log}
	for _, opt := range opts {
		opt(m)
	}

	if m.socketPath == "" {
		m.socketPath = endpointFromEnv()
	}

	if m.socketPath == "" {
		return nil, errors.New("SPIFFE endpoint socket not configured")
	}

	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	client, err := workloadapi.New(ctx, workloadapi.WithAddr("unix://"+m.socketPath))
	if err != nil {
		return nil, fmt.Errorf("connect workload api: %w", err)
	}

	m.client = client
	return m, nil
}

// Fetch loads the latest X509 context from the Workload API and caches it.
func (m *Manager) Fetch(ctx context.Context) (*workloadapi.X509SVID, error) {
	if m.client == nil {
		return nil, errors.New("workload api client not initialised")
	}

	x509ctx, err := m.client.FetchX509Context(ctx)
	if err != nil {
		return nil, fmt.Errorf("fetch x509 context: %w", err)
	}

	svid := x509ctx.DefaultSVID()
	if svid == nil {
		return nil, errors.New("no default SVID returned")
	}

	m.mu.Lock()
	m.svid = svid
	m.bundle = x509ctx
	m.mu.Unlock()

	m.log.Info("fetched SVID", slog.String("spiffe_id", svid.ID.String()), slog.Time("not_after", svid.Certificates[0].NotAfter))

	return svid, nil
}

// Close releases the underlying Workload API client.
func (m *Manager) Close() {
	if m.client != nil {
		if err := m.client.Close(); err != nil {
			m.log.Warn("closing workload api client", slog.String("err", err.Error()))
		}
	}
}

// Current returns the cached SVID if available.
func (m *Manager) Current() *workloadapi.X509SVID {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.svid
}

func endpointFromEnv() string {
	if fromEnv := os.Getenv("SPIFFE_ENDPOINT_SOCKET"); fromEnv != "" {
		return trimUnixScheme(fromEnv)
	}
	wd, err := os.Getwd()
	if err != nil {
		return defaultSocket
	}
	return filepath.Join(wd, defaultSocket)
}

func trimUnixScheme(addr string) string {
	if addr == "" {
		return addr
	}
	const prefix = "unix://"
	if len(addr) >= len(prefix) && addr[:len(prefix)] == prefix {
		return addr[len(prefix):]
	}
	return addr
}
