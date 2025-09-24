# oneedgectl

Developer convenience CLI for interacting with the oneEdge PoC stack.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r tools/oneedgectl/requirements.txt
```

## Commands

- `enroll --device-id dev/agent` – runs the SPIRE enrollment helper and persists `~/.oneedge/config.yaml`. Optionally registers the device with the Console API.
- `svid` – fetches the current workload SVID via the SPIFFE Workload API.
- `rotate` – touches the agent rotation signal (`~/.oneedge/rotate.signal`) and sends `SIGHUP` if the agent PID is recorded.
- `device-quarantine <spiffe_id>` – toggles quarantine state through the Console API.

Set `ONEEDGE_API_URL` if the Console API is exposed somewhere other than `http://localhost:8080`.
