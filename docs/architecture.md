# Architecture Overview

```
+----------------+        +----------------+       +-----------------+
| oneedge-agent  |  mTLS  |    Envoy       |  TCP  |    Mosquitto    |
| (Go)           +------->+  (SPIFFE SDS)  +------>+  (internal bus) |
+--------+-------+        +----------------+       +-----------------+
         |                         |
         | SPIFFE Workload API     | ext_authz (OPA)
         v                         v
  +---------------+        +------------------+
  |  SPIRE Agent  |<------>|  OPA + bundles   |
  +-------+-------+        +------------------+
          |
          | join token
          v
   +--------------+
   | SPIRE Server |
   +------+-------+
          |
          v
   +--------------+           +------------------+
   | Postgres     |<--------->| Console API (Go) |
   +------+-------+           +--------+---------+
          ^                             |
          | SSE / REST                  | REST / SSE
   +------+-------+                     v
   | Console Web  |<---------------------+
   | (Next.js)    |
   +--------------+
```

Key principles baked into the PoC:

- **Zero-trust identities** via SPIFFE/SPIRE issuing 10-minute SVIDs for workloads.
- **Policy enforcement** with Envoy performing mTLS termination and consulting OPA before MQTT publishes.
- **Separation of concerns** between control plane (SPIRE/OPA/Postgres/Console) and data plane (Envoy → Mosquitto).
- **Operator tooling** through `oneedgectl`, the Go console API, and the Next.js dashboard.
