# oneEdge Architecture Notes

The oneEdge reference implementation is intentionally modular so that each responsibility can be deployed, updated, and scaled independently.

## Service Overview

| Service      | Role | Notes |
|--------------|------|-------|
| ingestion    | Connects to industrial data sources (OPC UA, simulators) and republishes clean, contextualised telemetry to MQTT topics. |
| analytics    | Subscribes to telemetry streams, applies statistical rules, persists readings, and raises alerts back onto MQTT. |
| dashboard    | FastAPI backend plus SPA frontend for live operations, alerting, zero-trust device provisioning, and historical views. |
| mqtt         | Eclipse Mosquitto broker delivering low-latency pub/sub messaging. |
| retention    | On-demand maintenance job that prunes historical data according to retention policy. |

## Data Flow

1. **Acquisition** — `ingestion` pulls telemetry from PLCs via OPC UA (or generates test data). Each data point is published on a structured topic: `oneEdge/<site>/<device_id>/<metric>`.
2. **Streaming Analytics** — `analytics` listens on wildcard topics, stores readings in SQLite, and triggers rule/z-score based alerts. Alerts are written back to MQTT as `oneEdge/alerts` messages.
3. **Persistence** — Metrics, alerts, health snapshots, and device catalogue records live in `services/storage/database.py`. SQLAlchemy manages schema creation inside SQLite.
4. **Visualisation & Control** — `dashboard` consumes MQTT alerts (via an internal client), exposes REST endpoints for metrics/history/devices, and serves the web UI with auto-refreshing charts and device management.
5. **Notification** — Alerts surface in the UI instantly via Server-Sent Events; the same MQTT topic can be bridged upstream to cloud or maintenance systems.
6. **Onboarding & trust** — The dashboard API stores device auth metadata, enforces quarantine/rotation policies, and only issues session credentials after successful registration.

## Extending the Platform

- **Protocols** — Add additional ingestion adapters (e.g., Modbus TCP, Sparkplug B) by implementing modules under `services/ingestion/` and publishing to MQTT.
- **Analytics** — Replace the rule/z-score engine with ML models by plugging into `AnalyticsEngine.on_message`. Use persisted metrics for offline training.
- **Storage** — Swap SQLite for an external TSDB or Postgres by adjusting `services/storage/database.py` connection string.
- **Security** — Enable TLS for MQTT/OPC UA, integrate dashboard with SSO, and tighten Mosquitto ACLs.

This document complements the inline docstrings, the [device provisioning guide](device-provisioning.md), and the [device onboarding workflow](device-onboarding.md). Use it as a starting point for tailoring oneEdge to specific industrial projects.
