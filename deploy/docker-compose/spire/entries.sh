#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
COMPOSE_DIR=$(dirname "$SCRIPT_DIR")
cd "$COMPOSE_DIR"

COMPOSE_BIN=${COMPOSE_BIN:-docker compose}

JOIN_SPIFFE_ID=${JOIN_SPIFFE_ID:-spiffe://oneedge.local/spire/agent/dev-node}
DEVICE_SPIFFE_ID=${DEVICE_SPIFFE_ID:-spiffe://oneedge.local/device/dev/agent}
WORKLOAD_UID=${WORKLOAD_UID:-$(id -u)}
WORKLOAD_GID=${WORKLOAD_GID:-$(id -g)}
WORKLOAD_TTL=${WORKLOAD_TTL:-600}

info() { printf "[entries] %s\n" "$*"; }

docker_compose() {
  $COMPOSE_BIN "$@"
}

info "Ensuring SPIRE server is ready..."
docker_compose ps spire-server >/dev/null

token_output=$(docker_compose exec -T spire-server /opt/spire/bin/spire-server token generate -spiffeID "$JOIN_SPIFFE_ID")
JOIN_TOKEN=$(awk -F': ' '/Token/ {print $2}' <<<"$token_output")

if [[ -z "$JOIN_TOKEN" ]]; then
  printf 'Failed to parse join token from output:\n%s\n' "$token_output" >&2
  exit 1
fi

info "Join token issued for $JOIN_SPIFFE_ID"
printf '%s\n' "$token_output"

info "Creating workload entry for $DEVICE_SPIFFE_ID"
entry_args=(
  /opt/spire/bin/spire-server entry create
  -parentID "$JOIN_SPIFFE_ID"
  -spiffeID "$DEVICE_SPIFFE_ID"
  -ttl "$WORKLOAD_TTL"
  -selector "unix:uid:$WORKLOAD_UID"
  -selector "unix:gid:$WORKLOAD_GID"
)

entry_output=$(docker_compose exec -T spire-server "${entry_args[@]}") || true
printf '%s\n' "$entry_output"

if grep -q "Entry already exists" <<<"$entry_output"; then
  info "Workload entry already existed; reusing"
fi

info "Registered entries:"
docker_compose exec -T spire-server /opt/spire/bin/spire-server entry show -spiffeID "$DEVICE_SPIFFE_ID"

info "Active agents:"
docker_compose exec -T spire-server /opt/spire/bin/spire-server agent list

info "Join token (export ONEEDGE_SPIRE_JOIN_TOKEN to reuse): $JOIN_TOKEN"
