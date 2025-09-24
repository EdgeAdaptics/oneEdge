# oneedge-agent

The Go device agent establishes a SPIFFE identity, keeps it current, and publishes telemetry to the secured MQTT fabric via Envoy.

## Features

- Watches the SPIRE Workload API for 10-minute X.509 SVIDs and hot-reloads TLS when they rotate.
- Connects to Envoy using mutual TLS with SPIFFE-aware certificate validation.
- Publishes a heartbeat payload to `sensors/dev/agent/telemetry` every 10 seconds.

## Development

```bash
cd agents/oneedge-agent
# ensure the docker compose stack and SPIRE entries are running first
ONEEDGE_MQTT_BROKER=${ONEEDGE_MQTT_BROKER:-localhost:8883}
go run ./cmd/oneedge-agent
```

Configuration knobs:

- `ONEEDGE_MQTT_BROKER` – broker address exposed by Envoy (default `localhost:8883`).
- `ONEEDGE_MQTT_TOPIC` – telemetry topic (default `sensors/dev/agent/telemetry`).
- `SPIFFE_ENDPOINT_SOCKET` – override the Workload API socket path if not using `.devdata/spire/socket/public/api.sock`.
