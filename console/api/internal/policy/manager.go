package policy

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Manager updates policy overlays (e.g. quarantine list) for OPA bundles.
type Manager struct {
	quarantinePath string
	versionPath    string
	mu             sync.Mutex
}

// NewManager creates a Manager for the given overlay path.
func NewManager(quarantinePath string) *Manager {
	versionPath := filepath.Join(filepath.Dir(quarantinePath), "version")
	return &Manager{quarantinePath: quarantinePath, versionPath: versionPath}
}

// SetQuarantine flips the quarantine flag for a SPIFFE ID and bumps the version file.
func (m *Manager) SetQuarantine(spiffeID string, quarantined bool) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	type overlay struct {
		Overrides struct {
			Quarantine map[string]bool `json:"quarantine"`
		} `json:"overrides"`
	}

	payload := overlay{}

	if data, err := os.ReadFile(m.quarantinePath); err == nil {
		_ = json.Unmarshal(data, &payload)
	}

	if payload.Overrides.Quarantine == nil {
		payload.Overrides.Quarantine = map[string]bool{}
	}

	if quarantined {
		payload.Overrides.Quarantine[spiffeID] = true
	} else {
		delete(payload.Overrides.Quarantine, spiffeID)
	}

	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}

	if err := os.WriteFile(m.quarantinePath, data, 0o644); err != nil {
		return err
	}

	if err := os.MkdirAll(filepath.Dir(m.versionPath), 0o755); err != nil {
		return err
	}

	stamp := []byte(time.Now().UTC().Format(time.RFC3339Nano))
	return os.WriteFile(m.versionPath, stamp, 0o644)
}
