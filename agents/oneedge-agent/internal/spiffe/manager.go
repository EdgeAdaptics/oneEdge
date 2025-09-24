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

	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

const defaultSocket = ".devdata/spire/socket/public/api.sock"

// Manager watches the SPIFFE Workload API for X.509 SVID updates.
type Manager struct {
	log    *slog.Logger
	client *workloadapi.Client

	mu     sync.RWMutex
	svid   *x509svid.SVID
	bundle *workloadapi.X509Context

	socketPath string
	updates    chan *workloadapi.X509Context
}

// Option mutates the Manager during construction.
type Option func(*Manager)

// WithSocket overrides the Workload API socket path.
func WithSocket(path string) Option {
	return func(m *Manager) {
		m.socketPath = path
	}
}

// NewManager creates a Manager and connects to the Workload API.
func NewManager(ctx context.Context, log *slog.Logger, opts ...Option) (*Manager, error) {
	if log == nil {
		return nil, errors.New("logger is required")
	}

	m := &Manager{log: log, updates: make(chan *workloadapi.X509Context, 1)}
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

// Run blocks and watches for X.509 context updates until the context is cancelled.
func (m *Manager) Run(ctx context.Context) error {
	if m.client == nil {
		return errors.New("workload api client not initialised")
	}
	return m.client.WatchX509Context(ctx, m)
}

// Updates returns a channel that receives the latest X.509 context snapshots.
func (m *Manager) Updates() <-chan *workloadapi.X509Context {
	return m.updates
}

// Current returns the cached SVID if available.
func (m *Manager) Current() *x509svid.SVID {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.svid
}

// Close releases the underlying Workload API client.
func (m *Manager) Close() {
	if m.client != nil {
		if err := m.client.Close(); err != nil {
			m.log.Warn("closing workload api client", slog.String("err", err.Error()))
		}
	}
}

// OnX509ContextUpdate handles Workload API updates.
func (m *Manager) OnX509ContextUpdate(update *workloadapi.X509Context) {
	if update == nil {
		return
	}

	svid := update.DefaultSVID()
	if svid == nil {
		m.log.Warn("received X509 update without default SVID")
		return
	}

	m.mu.Lock()
	m.svid = svid
	m.bundle = update
	m.mu.Unlock()

	notAfter := svid.Certificates[0].NotAfter
	m.log.Info("SVID refreshed", slog.String("spiffe_id", svid.ID.String()), slog.Time("not_after", notAfter), slog.Duration("ttl", time.Until(notAfter)))

	select {
	case m.updates <- update:
	default:
		// Drop if listener is slow; they can always call Current().
	}
}

// OnX509ContextWatchError is invoked when the watch stream errors.
func (m *Manager) OnX509ContextWatchError(err error) {
	m.log.Error("workload api watch error", slog.String("err", err.Error()))
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
