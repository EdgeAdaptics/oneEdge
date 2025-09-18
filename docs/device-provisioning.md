# Device Provisioning Guide

The oneEdge dashboard ships with a zero-trust device catalogue that keeps track of the assets supervised by the gateway. Catalogue entries store authentication preferences, allow-listed endpoints, rotation cadence, and optional policy templates. Records are persisted in SQLite and exposed via the REST API.

## REST Endpoints

- `GET /api/devices` — returns the full list of provisioned devices sorted by name.
- `POST /api/devices` — creates a new device or updates an existing one by `device_id`.
- `POST /api/devices/{device_id}/rotate` — forces a secret rotation (PSK devices).
- `POST /api/devices/{device_id}/quarantine` — isolates a device (optional reason).
- `POST /api/devices/{device_id}/authorize` — removes quarantine (optional reason).
- `DELETE /api/devices/{device_id}` — removes a device from the catalogue.

### Provisioning Payload (`POST /api/devices`)

```json
{
  "device_id": "pressline-01",
  "name": "Press Line 01",
  "device_type": "Press",
  "location": "Zone A",
  "status": "inactive",
  "auth_method": "pre_shared_key",
  "auth_id": "CN=pressline-01",
  "rotation_interval_hours": 168,
  "allowed_endpoints": [
    "mqtt://192.168.1.10:1883",
    "https://api.partner.example"
  ],
  "initial_secret": "optional-bootstrap-secret",
  "device_static_key": "permanent-device-secret",
  "hardware_fingerprint": "A1:B2:C3:D4",
  "device_public_key": "-----BEGIN PUBLIC KEY-----...",
  "policy_template": {
    "topics": {
      "telemetry": "oneEdge/devices/pressline-01/telemetry"
    }
  },
  "metadata": {
    "oee_target": 0.9,
    "line_lead": "Alexei"
  }
}
```

- `device_id` is required and must be unique.
- `auth_method` defaults to `pre_shared_key`. Other values (e.g. `x509`, `token`) can be used for integration-specific logic.
- `device_static_key` is required for challenge-response authentication. It should be an immutable value derived from the device (e.g. fused secret or TPM output).
- `initial_secret` is optional. If omitted for PSK devices and no static key is present, oneEdge returns a bootstrap secret in the response.
- `hardware_fingerprint` records a unique identifier (serial number, TPM hash). Subsequent registration attempts must provide the same value.
- `rotation_interval_hours` controls how often secrets are rotated automatically during registration.
- `rotation_interval_hours` controls how often secrets are rotated automatically during registration.
- `allowed_endpoints` help declare the services the device may contact. Policies can reference this list for enforcement.
- `device_public_key` and `hardware_fingerprint` are optional but recommended when integrating with X.509/token-based attestation flows.

### Registration Payload (`POST /api/devices/register`)

```json
{
  "device_id": "pressline-01",
  "auth_id": "CN=pressline-01",
  "auth_secret": "permanent-device-secret",
  "request_challenge": true
}
```

1. **Request a challenge** by sending `request_challenge: true` (as above). The gateway replies with `{ "status": "challenge", "challenge": "<nonce>" }`.
2. **Sign the challenge** with the device static key and repost:

```json
{
  "device_id": "pressline-01",
  "challenge_response": "<hex-encoded-hmac>",
  "attributes": {
    "firmware": "1.2.0"
  }
}
```

Successful responses include an updated device record, the active policy, and (if rotated) a new `session_secret` that should replace the previous PSK.

## Dashboard Workflow

1. Open the **Device Catalogue** card on the dashboard (`http://<gateway-ip>:8000`).
2. Populate the provisioning form — ID, auth method, allow-listed endpoints, rotation interval, metadata, and optional policy template.
3. Submit to persist the record. A bootstrap secret is displayed if oneEdge generated it.
4. Run the device agent to request a challenge (`request_challenge: true`), sign it with the static key, and resend the `challenge_response`. The response contains the policy asset and any rotated secret.
5. Monitor the device table. Rows are flagged for quarantine, overdue rotations, or stale registrations.

Devices can be edited by re-submitting the form with the same `device_id`. Lifecycle actions (rotate/quarantine/authorize/delete) are available both via the API and inline buttons on the dashboard.

For production deployments ensure device provisioning endpoints are protected behind firewall rules, IAM, and PKI infrastructure appropriate for your security posture.
