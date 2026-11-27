"""Read settings for a CoreIOT MQTT device connection."""

import os
from pathlib import Path
from urllib.parse import urlsplit


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


def parse_connection(
    values: dict[str, str], token_key: str = "COREIOT_DEVICE_TOKEN",
) -> tuple[str, int, str, bool, str | None]:
    url = values.get("COREIOT_MQTT_URL", "")
    token = values.get(token_key, "")
    if not url or not token or any(character.isspace() for character in token):
        raise ValueError(f"Set COREIOT_MQTT_URL and a valid {token_key} for this device")
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
