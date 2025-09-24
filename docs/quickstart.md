# oneEdge Quickstart

This proof-of-concept spins up a zero-trust edge stack with SPIRE, Envoy, OPA, Mosquitto, Postgres, the console API/web, and a Go-based device agent.

## Prerequisites

- Docker + Docker Compose plugin
- Go 1.21+ (for local agent builds)
- Python 3.10+
- Node 18+ (for optional web development)

## First run

```bash
git clone https://github.com/EdgeAdaptics/oneEdge
cd oneEdge
make up
./deploy/docker-compose/spire/entries.sh
```

Register the demo device and run the agent:

```bash
python3 tools/oneedgectl/oneedgectl.py enroll --device-id dev/agent
make agent
```

Open the console at <http://localhost:3000>. Quarantine the device via the UI or CLI:

```bash
python3 tools/oneedgectl/oneedgectl.py device-quarantine spiffe://oneedge.local/device/dev/agent
```

The agent logs and Envoy policy decisions will reflect the deny within a few seconds.

## Common targets

```bash
make up         # start the full stack
make down       # tear everything down
make logs       # tail docker compose logs
make console-up # only console api + web
make fmt        # gofmt + lint helpers
```

See `docs/console.md` for console workflows and `docs/architecture.md` for an overview diagram.
