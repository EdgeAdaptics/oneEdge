"""Simulate zero-trust device onboarding against a oneEdge gateway."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

import paho.mqtt.client as mqtt


def _post_json(url: str, payload: Dict[str, Any], timeout: float = 10.0, context: ssl.SSLContext | None = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def _print(msg: str) -> None:
    print(f"[device-sim] {msg}")


def provision_device(base_url: str, payload: Dict[str, Any], context: ssl.SSLContext | None) -> Tuple[Dict[str, Any], str | None]:
    response = _post_json(f"{base_url}/api/devices", payload, context=context)
    device = response.get("device", {})
    bootstrap = response.get("bootstrap_secret")
    return device, bootstrap


def register_device(base_url: str, payload: Dict[str, Any], context: ssl.SSLContext | None) -> Dict[str, Any]:
    return _post_json(f"{base_url}/api/devices/register", payload, context=context)


def publish_telemetry(
    mqtt_host: str,
    mqtt_port: int,
    topic: str,
    payload: Dict[str, Any],
    username: str | None = None,
    password: str | None = None,
    use_tls: bool = False,
) -> None:
    client = mqtt.Client(client_id=f"sim-{payload['device_id']}")
    if username:
        client.username_pw_set(username=username, password=password)
    if use_tls:
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

    client.connect(mqtt_host, mqtt_port, keepalive=30)
    client.loop_start()
    client.publish(topic, json.dumps(payload), qos=1)
    time.sleep(1.0)
    client.loop_stop()
    client.disconnect()


def build_hmac(static_secret: str, challenge: str) -> str:
    hashed_secret = hashlib.sha256(static_secret.encode("utf-8")).hexdigest()
    digest = hmac.new(hashed_secret.encode("utf-8"), challenge.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate device onboarding and telemetry emission")
    parser.add_argument("device_id", help="Device identifier used in provisioning and registration")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Dashboard base URL")
    parser.add_argument("--auth-id", default=None, help="Authentication identifier (defaults to device_id)")
    parser.add_argument("--static-key", default=None, help="Device static key for challenge signing")
    parser.add_argument("--auth-secret", default=None, help="Bootstrap secret for MQTT session (defaults to static key)")
    parser.add_argument("--hardware-fingerprint", default=None, help="Hardware fingerprint to register")
    parser.add_argument("--skip-provision", action="store_true", help="Skip provisioning and reuse existing device record")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-base-topic", default="oneEdge/devices", help="Base MQTT topic for telemetry")
    parser.add_argument("--use-secret-mqtt", action="store_true", help="Send the session secret as MQTT password")
    parser.add_argument("--mqtt-tls", action="store_true", help="Use TLS when publishing telemetry")
    parser.add_argument("--insecure-http", action="store_true", help="Disable HTTPS certificate verification for dashboard calls")
    args = parser.parse_args()

    static_secret = args.static_key or f"{args.device_id}-static-secret"
    bootstrap_secret = args.auth_secret or static_secret
    hardware_fingerprint = args.hardware_fingerprint or args.device_id

    http_context = ssl._create_unverified_context() if args.insecure_http else None

    device_payload = {
        "device_id": args.device_id,
        "name": args.device_id.title(),
        "auth_method": "pre_shared_key",
        "auth_id": args.auth_id or args.device_id,
        "rotation_interval_hours": 168,
        "allowed_endpoints": [f"mqtt://{args.mqtt_host}:{args.mqtt_port}"],
        "device_static_key": static_secret,
        "hardware_fingerprint": hardware_fingerprint,
        "metadata": {"simulated": True},
    }

    if not args.skip_provision:
        _print("Provisioning device record ...")
        try:
            device_record, bootstrap = provision_device(args.base_url, device_payload, http_context)
            bootstrap_secret = bootstrap or bootstrap_secret
            if bootstrap:
                _print("Bootstrap secret issued; store securely (displayed once).")
            _print(f"Provisioned {device_record.get('device_id')}")
        except urllib.error.URLError as exc:
            _print(f"Failed to provision device: {exc}")
            sys.exit(1)

    _print("Requesting challenge ...")
    try:
        challenge_response = register_device(
            args.base_url,
            {
                "device_id": args.device_id,
                "auth_id": args.auth_id or args.device_id,
                "auth_secret": static_secret,
                "hardware_fingerprint": hardware_fingerprint,
                "request_challenge": True,
            },
            http_context,
        )
    except urllib.error.URLError as exc:
        _print(f"Failed to request challenge: {exc}")
        sys.exit(1)

    if challenge_response.get("status") != "challenge":
        _print("Unexpected response while requesting challenge.")
        sys.exit(1)

    challenge = challenge_response.get("challenge")
    if not challenge:
        _print("Challenge not provided by gateway.")
        sys.exit(1)
    _print(f"Received challenge: {challenge}")

    signature = build_hmac(static_secret, challenge)

    _print("Submitting challenge response ...")
    try:
        register_response = register_device(
            args.base_url,
            {
                "device_id": args.device_id,
                "challenge_response": signature,
                "hardware_fingerprint": hardware_fingerprint,
                "attributes": {"simulator": "device_onboarding_sim"},
            },
            http_context,
        )
    except urllib.error.URLError as exc:
        _print(f"Failed to complete registration: {exc}")
        sys.exit(1)

    if register_response.get("status") == "challenge":
        _print("Gateway issued a new challenge; retry the handshake.")
        sys.exit(1)

    session_secret = register_response.get("session_secret") or bootstrap_secret
    policy = register_response.get("policy", {})
    telemetry_topic = policy.get("topics", {}).get("telemetry") or f"{args.mqtt_base_topic}/{args.device_id}/telemetry"

    _print(f"Registration succeeded. Telemetry topic: {telemetry_topic}")
    if register_response.get("session_secret"):
        _print("Received rotated session secret; using for telemetry publish.")

    _print("Publishing sample telemetry ...")
    telemetry_payload = {
        "device_id": args.device_id,
        "timestamp": time.time(),
        "metric": "temperature",
        "value": 68.5,
        "source": "device_onboarding_sim",
    }
    publish_telemetry(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        topic=telemetry_topic,
        payload=telemetry_payload,
        username=args.device_id if args.use_secret_mqtt else None,
        password=session_secret if args.use_secret_mqtt else None,
        use_tls=args.mqtt_tls,
    )
    _print("Telemetry published. Simulation complete.")


if __name__ == "__main__":
    main()
