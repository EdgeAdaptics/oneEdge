create extension if not exists pgcrypto;

create table if not exists devices(
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null default 'default',
  spiffe_id text unique not null,
  class text,
  labels jsonb default '{}',
  status text not null default 'registered',
  last_seen timestamptz,
  current_fw_hash text,
  quarantine_reason text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_devices_tenant_status on devices(tenant_id, status);
create index if not exists idx_devices_spiffe on devices(spiffe_id);
