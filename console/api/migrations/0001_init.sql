create extension if not exists pgcrypto;

create table if not exists devices (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    spiffe_id text unique not null,
    display_name text,
    class text,
    labels jsonb default '{}'::jsonb,
    status text not null default 'registered',
    last_seen timestamptz,
    current_fw_hash text,
    quarantine_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists attestations (
    id uuid primary key default gen_random_uuid(),
    device_id uuid references devices(id) on delete cascade,
    time timestamptz not null default now(),
    type text not null,
    result text not null,
    evidence_hash text,
    refs_version text
);

create table if not exists credentials (
    id uuid primary key default gen_random_uuid(),
    device_id uuid references devices(id) on delete cascade,
    svid_id text not null,
    not_after timestamptz not null,
    key_slot text,
    rotation_count int default 0,
    created_at timestamptz not null default now()
);

create table if not exists policies (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    name text not null,
    rego text not null,
    version text not null,
    enabled boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists firmware (
    id uuid primary key default gen_random_uuid(),
    version text not null,
    hash text not null,
    tuf_role text,
    meta jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists rollouts (
    id uuid primary key default gen_random_uuid(),
    artifact_id uuid references firmware(id),
    strategy text,
    status text not null default 'draft',
    created_at timestamptz not null default now()
);

create table if not exists audits (
    id uuid primary key default gen_random_uuid(),
    actor text not null,
    action text not null,
    target_type text not null,
    target_id text,
    time timestamptz not null default now(),
    diff jsonb default '{}'::jsonb
);

create index if not exists devices_spiffe_idx on devices(spiffe_id);
create index if not exists devices_status_idx on devices(tenant_id, status);
