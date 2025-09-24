# Console Walkthrough

The console is split into two pieces:

- **Console API (Go)** – handles device registry, quarantine actions, and emits SSE notifications for UI updates. See `console/api/README.md`.
- **Console Web (Next.js)** – renders fleet metrics, device lists, and per-device detail pages at <http://localhost:3000>.

## Typical workflow

1. Enroll a device with `oneedgectl` and run the Go agent.
2. Navigate to `/devices` in the console to view the registered agent.
3. Select the device to open the detail view and use the Approve/Quarantine buttons.
4. Observe the agent losing MQTT access within a few seconds when quarantined.

The console surfaces live events via SSE; quarantine and approval actions immediately adjust the fleet metrics on the overview page.

Future enhancements (tracked for later sprints):

- OTA artifact management and rollout orchestration UI.
- Policy editor/testing workflows with diff previews.
- SBOM and attestation drill-downs fed by the `attest-svc` stub.
