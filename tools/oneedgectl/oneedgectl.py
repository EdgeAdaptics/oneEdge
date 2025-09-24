#!/usr/bin/env python3
"""oneedgectl: helper CLI for managing oneEdge dev workloads."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import typer
import yaml
from rich import print
from rich.console import Console
from rich.table import Table

try:
    from pyspiffe.workloadapi.default_workload_api_client import (
        DefaultWorkloadApiClient,
    )
except ImportError as exc:  # pragma: no cover - guidance when deps missing
    DefaultWorkloadApiClient = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

APP = typer.Typer(add_completion=False, help="oneEdge developer control plane helper")
CONSOLE = Console()

CONFIG_DIR = Path.home() / ".oneedge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ROTATE_SIGNAL = CONFIG_DIR / "rotate.signal"
PID_FILE = CONFIG_DIR / "agent.pid"
DEFAULT_SOCKET = Path.cwd() / ".devdata" / "spire" / "socket" / "public" / "api.sock"
DEFAULT_API_URL = "http://localhost:8080"
TRUST_DOMAIN = "oneedge.local"


def ensure_deps() -> None:
    if DefaultWorkloadApiClient is None:
        print(
            "[bold red]py-spiffe is not installed.\n"
            "Run `pip install -r tools/oneedgectl/requirements.txt` first."\
        )
        raise typer.Exit(code=2)


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def write_config(device_id: str, spiffe_id: str) -> None:
    ensure_config_dir()
    payload = {"device_id": device_id, "spiffe_id": spiffe_id, "updated_at": datetime.now(timezone.utc).isoformat()}
    CONFIG_FILE.write_text(yaml.safe_dump(payload, sort_keys=True))
    print(f"[green]Updated[/green] {CONFIG_FILE}")


def run_entries(sh_script: Path, device_id: str, spiffe_id: str) -> None:
    env = os.environ.copy()
    env.setdefault("DEVICE_SPIFFE_ID", spiffe_id)
    env.setdefault("JOIN_SPIFFE_ID", f"spiffe://{TRUST_DOMAIN}/spire/agent/{device_id.replace('/', '-')}")
    result = subprocess.run(
        ["./spire/" + sh_script.name],
        cwd=str(sh_script.parent.parent),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[bold red]entries.sh failed ({result.returncode})[/bold red]\n{result.stderr}")
        raise typer.Exit(code=result.returncode)


@APP.command()
def enroll(
    device_id: str = typer.Option(..., "--device-id", help="Device ID within the trust domain, e.g. dev/agent"),
    socket: Optional[Path] = typer.Option(None, help="Override SPIFFE Workload API socket"),
    autoregister: bool = typer.Option(True, help="Register device with Console API if available"),
) -> None:
    """Generate SPIRE entries and persist local device config."""

    spiffe_id = f"spiffe://{TRUST_DOMAIN}/device/{device_id}"
    write_config(device_id, spiffe_id)

    entries_script = Path("deploy/docker-compose/spire/entries.sh")
    if not entries_script.exists():
        print(f"[bold red]Cannot locate {entries_script}[/bold red]")
        raise typer.Exit(code=1)

    run_entries(entries_script, device_id, spiffe_id)

    if autoregister:
        register_device(spiffe_id)

    print("[green]Enrollment complete.[/green]")
    if socket:
        print(f"Using SPIFFE socket override: {socket}")


@APP.command("svid")
def svid_show(
    show: bool = typer.Option(True, "--show", help="Display the current X.509 SVID"),
    socket: Optional[Path] = typer.Option(None, help="SPIFFE Workload API socket path"),
) -> None:
    """Display the current SPIFFE ID and certificate expiry."""

    ensure_deps()

    target_socket = socket or Path(os.environ.get("SPIFFE_ENDPOINT_SOCKET", DEFAULT_SOCKET))
    client = DefaultWorkloadApiClient(spiffe_endpoint_socket=str(target_socket))
    try:
        svid = client.fetch_x509_svid()
    finally:
        client.close()

    cert = svid.cert_chain[0]
    spiffe_id = svid.spiffe_id.spiffe_id
    not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
    ttl = not_after - datetime.now(timezone.utc)

    table = Table(title="Current X.509 SVID", show_header=False)
    table.add_row("SPIFFE ID", spiffe_id)
    table.add_row("Not After", not_after.isoformat())
    table.add_row("TTL", str(ttl))
    CONSOLE.print(table)


@APP.command()
def rotate() -> None:
    """Signal the local agent to re-fetch credentials."""

    ensure_config_dir()
    ROTATE_SIGNAL.touch()
    print(f"[green]Touched[/green] {ROTATE_SIGNAL}")

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            print(f"[yellow]Warning:[/yellow] invalid PID in {PID_FILE}")
        else:
            try:
                os.kill(pid, signal.SIGHUP)
                print(f"Sent SIGHUP to agent PID {pid}")
            except ProcessLookupError:
                print(f"[yellow]Warning:[/yellow] agent process {pid} not found")


@APP.command()
def device_quarantine(
    spiffe_id: str,
    reason: str = typer.Option("manual quarantine", help="Reason to log on the device record"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="ONEEDGE_API_URL", help="Console API base URL"),
) -> None:
    """Quarantine the device via the Console API."""

    endpoint = f"{api_url.rstrip('/')}/v1/devices/{spiffe_id}:quarantine"
    try:
        response = requests.post(endpoint, json={"reason": reason}, timeout=5)
    except requests.RequestException as exc:
        print(f"[bold red]Request failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if response.status_code >= 400:
        print(f"[bold red]API error {response.status_code}[/bold red]: {response.text}")
        raise typer.Exit(code=1)

    print(f"[green]Device {spiffe_id} quarantined[/green]")


def register_device(spiffe_id: str) -> None:
    api_url = os.environ.get("ONEEDGE_API_URL", DEFAULT_API_URL)
    endpoint = f"{api_url.rstrip('/')}/v1/devices"
    payload = {"spiffe_id": spiffe_id, "display_name": spiffe_id.split('/')[-1]}
    try:
        resp = requests.post(endpoint, json=payload, timeout=3)
    except requests.RequestException:
        print("[yellow]Console API not reachable; skipping device registration.[/yellow]")
        return

    if resp.status_code >= 300:
        print(f"[yellow]Device registration responded with {resp.status_code}: {resp.text}[/yellow]")
    else:
        print("[green]Device registered with Console API[/green]")


if __name__ == "__main__":
    APP()
