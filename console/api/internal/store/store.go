package store

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	_ "github.com/jackc/pgx/v5/stdlib"
)

var ErrNotFound = errors.New("resource not found")

// Config defines Store connection settings.
type Config struct {
	DSN string
}

// Store wraps database access for the console API.
type Store struct {
	db *sqlx.DB
}

// New initialises the Store.
func New(cfg Config) (*Store, error) {
	db, err := sqlx.Open("pgx", cfg.DSN)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(10)
	db.SetConnMaxLifetime(30 * time.Minute)
	return &Store{db: db}, nil
}

// Close releases database resources.
func (s *Store) Close() error {
	return s.db.Close()
}

// Device represents a managed edge device.
type Device struct {
	ID              uuid.UUID      `db:"id" json:"id"`
	TenantID        string         `db:"tenant_id" json:"tenant_id"`
	SPIFFEID        string         `db:"spiffe_id" json:"spiffe_id"`
	DisplayName     sql.NullString `db:"display_name" json:"display_name,omitempty"`
	Class           sql.NullString `db:"class" json:"class,omitempty"`
	Labels          []byte         `db:"labels" json:"labels"`
	Status          string         `db:"status" json:"status"`
	LastSeen        sql.NullTime   `db:"last_seen" json:"last_seen,omitempty"`
	CurrentFWHash   sql.NullString `db:"current_fw_hash" json:"current_fw_hash,omitempty"`
	QuarantineReason sql.NullString `db:"quarantine_reason" json:"quarantine_reason,omitempty"`
	CreatedAt       time.Time      `db:"created_at" json:"created_at"`
	UpdatedAt       time.Time      `db:"updated_at" json:"updated_at"`
}

// RegisterDeviceInput captures data for creating or updating a device.
type RegisterDeviceInput struct {
	SPIFFEID    string
	DisplayName string
	Class       string
	Labels      []byte
}

// RegisterDevice inserts or updates a device record.
func (s *Store) RegisterDevice(ctx context.Context, in RegisterDeviceInput) (Device, error) {
	var device Device
	err := s.db.GetContext(ctx, &device, `
		insert into devices (spiffe_id, display_name, class, labels)
		values ($1, nullif($2, ''), nullif($3, ''), coalesce($4, '{}'::jsonb))
		on conflict (spiffe_id) do update set
			display_name = excluded.display_name,
			class = excluded.class,
			labels = excluded.labels,
			updated_at = now()
		returning *
	`, in.SPIFFEID, in.DisplayName, in.Class, in.Labels)
	return device, err
}

// ListDevices returns devices for the tenant.
func (s *Store) ListDevices(ctx context.Context, tenant string) ([]Device, error) {
	var devices []Device
	err := s.db.SelectContext(ctx, &devices, `
		select * from devices where tenant_id = $1 order by created_at desc limit 200
	`, tenant)
	return devices, err
}

// GetDevice fetches a device by UUID.
func (s *Store) GetDevice(ctx context.Context, id uuid.UUID) (Device, error) {
	var device Device
	err := s.db.GetContext(ctx, &device, `select * from devices where id = $1`, id)
	if errors.Is(err, sql.ErrNoRows) {
		return Device{}, ErrNotFound
	}
	return device, err
}

// GetDeviceBySPIFFE fetches a device by SPIFFE ID.
func (s *Store) GetDeviceBySPIFFE(ctx context.Context, spiffeID string) (Device, error) {
	var device Device
	err := s.db.GetContext(ctx, &device, `select * from devices where spiffe_id = $1`, spiffeID)
	if errors.Is(err, sql.ErrNoRows) {
		return Device{}, ErrNotFound
	}
	return device, err
}

// UpdateDeviceStatus sets the device status and optional quarantine reason.
func (s *Store) UpdateDeviceStatus(ctx context.Context, id uuid.UUID, status string, reason *string) (Device, error) {
	var device Device
	err := s.db.GetContext(ctx, &device, `
		update devices set status = $2,
			quarantine_reason = $3,
			updated_at = now()
		where id = $1
		returning *
	`, id, status, reason)
	if errors.Is(err, sql.ErrNoRows) {
		return Device{}, ErrNotFound
	}
	return device, err
}

// FleetMetrics summarises fleet level counts.
type FleetMetrics struct {
	Total       int `db:"total" json:"total"`
	Online      int `db:"online" json:"online"`
	Quarantined int `db:"quarantined" json:"quarantined"`
}

// FleetMetrics returns high level device counts.
func (s *Store) FleetMetrics(ctx context.Context, tenant string) (FleetMetrics, error) {
	var metrics FleetMetrics
	err := s.db.GetContext(ctx, &metrics, `
		select
			count(*) as total,
			sum(case when status = 'online' then 1 else 0 end) as online,
			sum(case when status = 'quarantined' then 1 else 0 end) as quarantined
		from devices
		where tenant_id = $1
	`, tenant)
	return metrics, err
}
