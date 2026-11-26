"""Run the CoreIOT simulator against a dedicated sandbox device token."""

import argparse
import logging
import os
import signal
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

from .classroom import DEFAULT_READINGS, Simulator
from .gateway import RpcBridge


def read_environment(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if path is not None:
        for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name = name.strip()
            if not separator or not name.isidentifier():
                raise ValueError(f"Invalid environment file assignment on line {number}")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[name] = value
    return {**values, **os.environ}


def parse_connection(values: dict[str, str]) -> tuple[str, int, str, bool, str | None]:
    url = values.get("COREIOT_MQTT_URL", "")
    token = values.get("COREIOT_DEVICE_TOKEN", "")
    if not url or not token:
        raise ValueError("Set COREIOT_MQTT_URL and COREIOT_DEVICE_TOKEN for the sandbox device")
    if any(character.isspace() for character in url):
        raise ValueError("COREIOT_MQTT_URL must contain no whitespace")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("mqtt", "mqtts") or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.path not in ("", "/") or parsed.query or parsed.fragment
    ):
        raise ValueError("COREIOT_MQTT_URL must be an MQTT or MQTTS URL without credentials or a path")
    tls = parsed.scheme == "mqtts"
    port = parsed.port if parsed.port is not None else (8883 if tls else 1883)
    if port == 0:
        raise ValueError("COREIOT_MQTT_URL must use a nonzero port")
    ca_file = values.get("COREIOT_MQTT_CA_FILE") or None
    if ca_file and not tls:
        raise ValueError("COREIOT_MQTT_CA_FILE requires an mqtts URL")
    return parsed.hostname, port, token, tls, ca_file


def parse_bool(value: str) -> bool:
    if value not in ("true", "false"):
        raise argparse.ArgumentTypeError("expected true or false")
    return value == "true"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--device-id", help="override COREIOT_DEVICE_ID for the chosen token")
    parser.add_argument("--minimal", action="store_true", help="use humidity and LED telemetry with optional temperature")
    parser.add_argument("--omit-humidity", action="store_true", help="simulate a missing humidity reading (minimal mode)")
    parser.add_argument("--no-led", action="store_true", help="simulate a board without LED support (minimal mode)")
    parser.add_argument("--interval-ms", type=int, default=5000)
    parser.add_argument("--ack-delay-ms", type=int, default=50, help="delay simulated local execution and ACK")
    parser.add_argument("--timeout-ms", type=int, default=3500, help="deadline for a matching device ACK")
    parser.add_argument("--unsynchronized", action="store_true", help="use null timestamps on local device messages")
    fault = parser.add_mutually_exclusive_group()
    fault.add_argument("--drop-ack", action="store_true", help="execute commands and suppress device ACKs")
    fault.add_argument("--offline-device", action="store_true", help="simulate an unreachable local device")
    fault.add_argument("--missing-device", action="store_true", help="reject commands for an unregistered target")
    for name, default in DEFAULT_READINGS.items():
        option = "fw-version" if name == "fwVersion" else name
        value_type = str if name == "fwVersion" else (parse_bool if type(default) is bool else float)
        parser.add_argument(f"--{option}", dest=name, type=value_type, default=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (1 <= args.interval_ms <= 3_600_000 and 1 <= args.timeout_ms <= 60_000 and 0 <= args.ack_delay_ms <= 60_000):
        parser.error("interval must be 1–3600000 ms, timeout 1–60000 ms, and ACK delay 0–60000 ms")
    readings = {name: getattr(args, name) for name in DEFAULT_READINGS if hasattr(args, name)}
    for omit, key in ((args.omit_humidity, "humidity"), (args.no_led, "lamp")):
        if omit:
            if not args.minimal or key in readings:
                parser.error(f"omitting {key} requires --minimal and no explicit --{key}")
            readings[key] = None

    try:
        from .mqtt_client import MqttSettings, run
    except ModuleNotFoundError as exc:
        if exc.name != "paho":
            raise
        parser.error("Install MQTT support using python -m pip install -r coreiot/simulator/requirements.txt")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signal, _frame: stop.set())
    try:
        values = read_environment(args.env_file)
        connection = MqttSettings(*parse_connection(values))
        device_id = args.device_id or values.get("COREIOT_DEVICE_ID") or "classroom-01"
        simulator = Simulator(
            RpcBridge(device_id, args.timeout_ms / 1000),
            readings=readings, minimal=args.minimal,
            interval=args.interval_ms / 1000, ack_delay=args.ack_delay_ms / 1000,
            synchronized=not args.unsynchronized, device_present=not args.missing_device,
            device_online=not args.offline_device, drop_ack=args.drop_ack,
        )
        run(connection, simulator, stop)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
