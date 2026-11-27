"""Exercise a running simulator through an authenticated CoreIOT sandbox."""

import argparse
import json
import math
import os
import sys
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID


ACTUATORS = {"setLamp": "lamp", "setDoor": "door"}
LIVE_KEYS = (
    "deviceId", "ts", "temperature", "humidity", "light", "motion", "distance",
    "lamp", "door", "fwVersion",
)
MINIMAL_KEYS = ("deviceId", "ts", "humidity", "lamp", "fwVersion")
MAX_SAMPLE_AGE_MS = 30_000
MAX_CLOCK_SKEW_MS = 5_000


class SandboxAPI:
    def __init__(self, base_url: str, auth: str, entity_id: UUID):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
            raise ValueError("COREIOT_TENANT_URL must be an HTTPS URL without embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("COREIOT_TENANT_URL must not contain a query or fragment")
        scheme, _, credential = auth.partition(" ")
        if scheme not in ("Bearer", "ApiKey") or not credential or any(
            not "!" <= character <= "~" for character in credential
        ):
            raise ValueError("COREIOT_REST_AUTH must contain a Bearer token or ApiKey")
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.entity_id = entity_id

    def request(self, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"})
        request.add_unredirected_header("X-Authorization", self.auth)
        with urlopen(request, timeout=15 if body is not None else 5) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Expected an object in the CoreIOT response")
        return result

    def latest(self, keys: tuple[str, ...]) -> dict:
        query = urlencode({"keys": ",".join(keys)})
        path = f"/api/plugins/telemetry/DEVICE/{self.entity_id}/values/timeseries?{query}"
        result = self.request(path)
        return {key: result[key][0] for key in keys if result.get(key)}

    def rpc(self, method: str, value: bool | int) -> dict:
        return self.request(f"/api/rpc/twoway/{self.entity_id}", {
            "method": method, "params": value, "timeout": 10000, "persistent": False,
        })


def as_boolean(value: object) -> bool:
    if type(value) is bool:
        return value
    if value in ("true", "false"):
        return value == "true"
    raise ValueError("Expected a boolean telemetry value")


def is_current(timestamp: object, now: int) -> bool:
    return type(timestamp) is int and -MAX_CLOCK_SKEW_MS <= now - timestamp <= MAX_SAMPLE_AGE_MS


def wait_for_state(api: SandboxAPI, key: str, desired: bool, previous_ts: int, ack_ts: int) -> int:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        sample = api.latest((key,)).get(key)
        if (sample and is_current(sample["ts"], time.time_ns() // 1_000_000)
                and sample["ts"] > previous_ts and sample["ts"] >= ack_ts
                and as_boolean(sample["value"]) is desired):
            return sample["ts"]
        time.sleep(0.25)
    raise ValueError(f"Timed out waiting for fresh {key}={desired!s} telemetry")


def verify_sandbox(
    api: SandboxAPI, device_name: str, firmware_version: str, *,
    minimal: bool = False, expect_temperature: bool = False,
) -> None:
    device = api.request(f"/api/device/{api.entity_id}")
    if device.get("name") != device_name:
        raise ValueError("The entity name differs from the specified sandbox device")
    expected = MINIMAL_KEYS if minimal else LIVE_KEYS
    if minimal and expect_temperature:
        expected += ("temperature",)
    initial = api.latest(expected)
    if missing := set(expected) - initial.keys():
        raise ValueError(f"Missing telemetry keys {sorted(missing)}")
    now = time.time_ns() // 1_000_000
    if any(not is_current(sample["ts"], now) for sample in initial.values()):
        raise ValueError("Start the simulator and wait for fresh, clock-aligned telemetry")
    if initial["deviceId"]["value"] != device_name or initial["fwVersion"]["value"] != firmware_version:
        raise ValueError("The simulator deviceId or fwVersion differs from the expected telemetry")
    if int(initial["ts"]["value"]) != initial["ts"]["ts"]:
        raise ValueError("The source timestamp differs from its CoreIOT telemetry point timestamp")
    if not minimal:
        as_boolean(initial["motion"]["value"])
    for key in ("temperature", "humidity", "light", "distance"):
        if key not in expected:
            continue
        value = initial[key]["value"]
        number = float(value)
        if type(value) is bool or not math.isfinite(number):
            raise ValueError(f"Expected finite numeric {key} telemetry")
        if minimal and key == "humidity" and not 0 <= number <= 100:
            raise ValueError("Expected humidity between 0 and 100 percent RH")
    actuators = {"setLamp": "lamp"} if minimal else ACTUATORS
    starting_states = {key: as_boolean(initial[key]["value"]) for key in actuators.values()}

    ack_ids = set()
    for method, key in actuators.items():
        reported = starting_states[key]
        previous_ts = initial[key]["ts"]
        for desired in (not reported, reported):
            sent_ts = time.time_ns() // 1_000_000
            started = time.monotonic()
            ack = api.rpc(method, desired)
            elapsed = round((time.monotonic() - started) * 1000, 1)
            received_ts = time.time_ns() // 1_000_000
            earliest_ack = max(previous_ts, sent_ts - MAX_CLOCK_SKEW_MS)
            ack_id = ack.get("id")
            ack_ts = ack.get("ts")
            if (ack.get("ok") is not True or ack.get("actualState") is not desired
                    or not isinstance(ack_id, str) or not ack_id or ack_id in ack_ids
                    or type(ack_ts) is not int or not earliest_ack <= ack_ts <= received_ts + MAX_CLOCK_SKEW_MS):
                raise ValueError(f"{method} returned a rejected, mismatched or duplicate ACK")
            ack_ids.add(ack_id)
            previous_ts = wait_for_state(api, key, desired, previous_ts, ack_ts)
            print(json.dumps({"mode": "synthetic", "method": method, "value": desired,
                              "ackId": ack_id, "ackTs": ack_ts, "rpcMs": elapsed, "telemetryTs": previous_ts}))

    known_method = "setLamp" if minimal else "setDoor"
    for method, value, error in (("unsupportedMethod", True, "unsupported_method"), (known_method, 1, "invalid_value")):
        ack = api.rpc(method, value)
        if ack.get("ok") is not False or ack.get("actualState", False) is not None or ack.get("error") != error:
            raise ValueError(f"{method} did not return the expected application rejection")
        print(json.dumps({"mode": "synthetic", "method": method, "result": "rejected"}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-device", required=True, type=UUID, help="UUID of the simulator-only device")
    parser.add_argument("--device-name", required=True, help="CoreIOT device name and simulator deviceId")
    parser.add_argument("--fw-version", choices=("1.0.0", "1.1.0"), default="1.0.0")
    parser.add_argument("--minimal", action="store_true", help="verify humidity and board LED only")
    parser.add_argument("--expect-temperature", action="store_true", help="require temperature in minimal mode")
    args = parser.parse_args()
    if args.expect_temperature and not args.minimal:
        parser.error("--expect-temperature requires --minimal; extended mode always expects temperature")
    try:
        api = SandboxAPI(os.environ["COREIOT_TENANT_URL"], os.environ["COREIOT_REST_AUTH"], args.sandbox_device)
        verify_sandbox(
            api, args.device_name, args.fw_version, minimal=args.minimal, expect_temperature=args.expect_temperature,
        )
    except KeyError as error:
        print(f"Missing sandbox setting or response field {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, AttributeError, IndexError) as error:
        print(f"Sandbox check failed. {error}", file=sys.stderr)
        return 1
    commands = 2 if args.minimal else 6
    print(f"CoreIOT sandbox passed for synthetic telemetry, {commands} RPC commands and two rejections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
