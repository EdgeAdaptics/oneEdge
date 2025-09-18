# Device Onboarding & Zero-Trust Workflow

oneEdge treats every edge asset as an untrusted entity until it completes a registration handshake. Provisioning metadata is created by an operator (via the dashboard or REST API) and the device must authenticate using the configured method before receiving a policy asset and session credentials.

## Provisioning Steps

1. **Create the catalogue entry** – supply the device ID, friendly name, authentication method, optional bootstrap secret, rotation interval, allow-listed endpoints, and a policy template (if required). This can be performed from the dashboard or by POSTing to `/api/devices`.
2. **Distribute bootstrap material** – if a pre-shared key (PSK) method is used and no secret was provided, oneEdge generates a bootstrap secret on creation. Store it securely; it is returned only once.
3. **Device registration** – the device agent performs a challenge/response handshake via `POST /api/devices/register`:
   1. Send `{ "device_id": "...", "auth_id": "...", "auth_secret": "...", "request_challenge": true }` to obtain a challenge.
   2. Sign the returned nonce with the device static key (HMAC-SHA256 of the nonce using the SHA-256 hash of the static key) and resend `{ "device_id": "...", "challenge_response": "<hex>" }`.
   3. On success the gateway records `last_seen_at`, rotates the session secret if due, and returns:
      - `policy` – the policy asset describing allowed MQTT topics/endpoints.
      - `session_secret` – present when a new pre-shared key is issued.
      - `next_rotation_hours` – rotation cadence for planning renewals.
4. **Policy enforcement** – the device stores the policy asset (topics, endpoints, rotation cadence) and uses the provided secret for MQTT/HTTP communications.
5. **Health monitoring** – the dashboard flags devices that:
   - are quarantined by an operator
   - have exceeded their rotation interval without a new key
   - have not authenticated within twice the rotation interval (stale)

## Lifecycle Actions

| Endpoint | Description |
|----------|-------------|
| `POST /api/devices/{device_id}/rotate` | Forces an immediate secret rotation (PSK devices). Returns the new secret for distribution. |
| `POST /api/devices/{device_id}/quarantine` | Isolates a device. Registration attempts return HTTP 423 until authorized. Optional reason recorded. |
| `POST /api/devices/{device_id}/authorize` | Clears quarantine and optionally records an authorization note. |
| `DELETE /api/devices/{device_id}` | Removes the catalogue entry. |

## Example Challenge Flow

1. Request challenge:

   ```json
{
  "device_id": "pressline-01",
  "auth_id": "CN=pressline-01",
  "auth_secret": "device-static-secret",
  "request_challenge": true,
  "hardware_fingerprint": "A1:B2:C3:D4"
}
```

2. Sign challenge using the static secret (`signature = HMAC-SHA256(hash(static_secret), challenge)`):

   ```json
{
  "device_id": "pressline-01",
 "challenge_response": "0f8a4c...",
  "hardware_fingerprint": "A1:B2:C3:D4",
  "attributes": {
    "firmware": "1.2.0"
  }
}
```

Repeated failures automatically increment the device's failure counter; once the configured threshold is reached (default five attempts) the device is quarantined and must be re-authorized by an operator.

Challenges expire after the configured window (default five minutes). Request a fresh challenge if the device cannot respond in time.

## Simulator Script

Use `python scripts/device_onboarding_sim.py` to exercise the full workflow locally (provision → register → publish telemetry). Run `python scripts/device_onboarding_sim.py --help` for options.

> **Note:** These endpoints are intentionally lightweight for the reference implementation. Harden them behind authentication (dashboard basic auth, mTLS, API gateway) and integrate with your PKI/credential management system before production deployments.
