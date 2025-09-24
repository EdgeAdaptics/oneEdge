# SPIRE Dev Setup

This directory contains development-time configuration for the SPIRE server and agent powering the `oneEdge` trust domain.

## Utilities

- `spire-server.conf` – standalone server configuration for the `spiffe://oneedge.local` trust domain.
- `spire-agent.conf` – agent configuration exposing the Workload API socket over the shared volume `../../.devdata/spire/socket`.
- `entries.sh` – helper script that provisions a join token for the dev agent node and registers the device workload entry used by the demo agent.

## Usage

```bash
cd deploy/docker-compose
./spire/entries.sh
```

The script will:

1. Generate a fresh join token for the SPIRE agent container (displayed in the output).
2. Register a workload entry for the demo agent `spiffe://oneedge.local/device/dev/agent` bound to your current UNIX `uid`/`gid` selectors.
3. Print the registered entries and active agents so you can confirm enrollment.

Environment overrides:

- `JOIN_SPIFFE_ID` – custom SPIFFE ID for the SPIRE agent node (default `spiffe://oneedge.local/spire/agent/dev-node`).
- `DEVICE_SPIFFE_ID` – workload SPIFFE ID (default `spiffe://oneedge.local/device/dev/agent`).
- `WORKLOAD_UID` / `WORKLOAD_GID` – selectors to bind the workload entry to (defaults to `id -u` / `id -g`).
- `WORKLOAD_TTL` – TTL in seconds for the issued SVID (default `600`, i.e. 10 minutes).

After running the script, start the agent binary and it will automatically obtain an SVID from the Workload API socket exposed at `.devdata/spire/socket/public/api.sock`.
