# oneedge-agent

The Go device agent establishes a SPIFFE identity, keeps it current, and publishes telemetry to the secured MQTT fabric.

This initial scaffold wires up the Workload API client and logging utilities. The MQTT publisher and rotation loop are implemented in subsequent commits.

## Development

```bash
cd agents/oneedge-agent
go run ./cmd/oneedge-agent
```

By default the agent connects to the Workload API socket under `.devdata/spire/socket/public/api.sock`. Override with `SPIFFE_ENDPOINT_SOCKET` if you expose the socket elsewhere.
