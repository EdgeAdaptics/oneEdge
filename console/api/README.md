# Console API

Go service providing the fleet management API for oneEdge.

## Running locally

```bash
export DATABASE_URL=postgres://oneedge:oneedge_dev_pw@localhost:5432/oneedge?sslmode=disable
export OPA_QUARANTINE_PATH=deploy/docker-compose/opa/bundles/oneedge/overrides/tenant/default/quarantine.json
cd console/api
go run ./cmd/console-api
```

Endpoints implemented in this pass:

- `POST /v1/devices` – register or update a device record.
- `GET /v1/devices` – list devices for the default tenant.
- `GET /v1/devices/{id}` – fetch a device by UUID.
- `POST /v1/devices/{id}:approve|quarantine|blacklist|deauthorize|rotate` – transition device state with quarantine support wired into the OPA bundle overlay.
- `GET /v1/events/stream` – server-sent events feed for console UI live updates.
- `GET /v1/metrics/fleet` – simple card metrics (total/online/quarantined).

Policy endpoints currently return stub responses until the policy workflow is fleshed out.
