"""Translate CoreIOT requests into local MQTT messages and correlate their ACKs."""

import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from uuid import uuid4

TELEMETRY_TOPIC = "v1/devices/me/telemetry"
RPC_REQUEST_PREFIX = "v1/devices/me/rpc/request/"
RPC_RESPONSE_PREFIX = "v1/devices/me/rpc/response/"
ACTUATORS = {"setLamp": "lamp", "setDoor": "door"}
SENSOR_FIELDS = ("temperature", "humidity", "light", "distance")
SENSOR_RANGES = {"temperature": (-40, 85), "humidity": (0, 100), "light": (0, 4095), "distance": (2, 400)}
STATE_FIELDS = ("motion", *ACTUATORS.values())
MINIMAL_SENSOR_FIELDS = ("humidity", "temperature")
MINIMAL_STATE_FIELDS = ("lamp",)
TOPIC_SEGMENT = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
MAX_MQTT_PAYLOAD_BYTES = 4096


@dataclass(frozen=True)
class Publication:
    topic: str
    body: dict


@dataclass(frozen=True)
class PendingRequest:
    request_id: str
    command_id: str
    deadline: float
    requested_state: bool


def failure(command_id: str, error: str) -> dict:
    return {"id": command_id, "ok": False, "actualState": None, "ts": None, "error": error}


def valid_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**63 - 1


def finite_number(value: object) -> bool:
    if type(value) is int:
        return -(2**63) <= value <= 2**63 - 1
    return type(value) is float and math.isfinite(value)


def reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant {value}")


def json_object(payload: bytes) -> dict:
    if len(payload) > MAX_MQTT_PAYLOAD_BYTES:
        raise ValueError("MQTT payload is too large")
    try:
        value = json.loads(payload.decode("utf-8"), parse_constant=reject_json_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValueError("Invalid JSON payload") from None
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def cloud_telemetry(
    topic: str, sample: dict, device_id: str, received_ms: int, *, minimal: bool = False,
) -> Publication:
    """Validate the shared sample and use the receipt time for an unsynchronized device."""
    if topic != f"classroom/{device_id}/telemetry" or sample.get("deviceId") != device_id:
        raise ValueError("Unknown or mismatched telemetry device")
    if "ts" not in sample or (sample["ts"] is not None and not valid_timestamp(sample["ts"])):
        raise ValueError("Telemetry ts must be Unix milliseconds or null")
    if not valid_timestamp(received_ms):
        raise ValueError("Gateway receipt time must be Unix milliseconds")
    values = {"deviceId": device_id}
    sensor_fields = MINIMAL_SENSOR_FIELDS if minimal else SENSOR_FIELDS
    state_fields = MINIMAL_STATE_FIELDS if minimal else STATE_FIELDS
    for key in sensor_fields:
        value = sample.get(key)
        if value is None:
            continue
        if not finite_number(value):
            raise ValueError(f"Telemetry {key} must be a finite number")
        low, high = SENSOR_RANGES[key]
        if not low <= value <= high or (key == "light" and type(value) is not int):
            raise ValueError(f"Telemetry {key} is outside the supported measurement range or format")
        values[key] = value
    for key in state_fields:
        value = sample.get(key)
        if value is None:
            continue
        if type(value) is not bool:
            raise ValueError(f"Telemetry {key} must be a boolean")
        values[key] = value
    version = sample.get("fwVersion")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Telemetry fwVersion must be a nonempty string")

    values["fwVersion"] = version
    timestamp = sample["ts"]
    if timestamp is not None:
        values["ts"] = timestamp
    return Publication(TELEMETRY_TOPIC, {"ts": received_ms if timestamp is None else timestamp, "values": values})


def production_telemetry(topic: str, sample: dict, device_id: str, received_ms: int, *, minimal: bool) -> Publication:
    if device_id in ("classroom-01", "classroom-ota-board") and sample.get("mockMode") is not False:
        raise ValueError("Physical device reports must identify genuine acquisition")
    timestamp = sample.get("ts")
    if valid_timestamp(timestamp) and not fresh_telemetry(timestamp, received_ms):
        raise ValueError("Telemetry timestamp is stale or too far in the future")
    return cloud_telemetry(topic, sample, device_id, received_ms, minimal=minimal)


def fresh_telemetry(timestamp: int, now_ms: int) -> bool:
    return -5000 <= now_ms - timestamp <= 30000


def valid_ack(body: dict) -> bool:
    command_id = body.get("id")
    state = body.get("actualState")
    if (
        not isinstance(command_id, str)
        or not command_id
        or type(body.get("ok")) is not bool
        or "actualState" not in body
        or (state is not None and type(state) is not bool)
        or "ts" not in body
        or (body["ts"] is not None and not valid_timestamp(body["ts"]))
    ):
        return False
    if body["ok"]:
        return type(state) is bool
    error = body.get("error")
    return isinstance(error, str) and bool(error.strip())


class RpcBridge:
    """Keep bounded request state for one classroom and one current cloud session."""

    def __init__(
        self, device_id: str, timeout: float, *, max_pending: int = 64, max_completed: int = 256
    ) -> None:
        if not device_id.strip() or any(character in device_id for character in "/+#\0"):
            raise ValueError("Device ID must be a single MQTT topic segment")
        if not math.isfinite(timeout) or timeout <= 0 or max_pending < 1 or max_completed < 1:
            raise ValueError("Timeout and request-cache sizes must be positive")
        self.device_id = device_id
        self.command_topic = f"classroom/{device_id}/cmd"
        self.ack_topic = f"classroom/{device_id}/ack"
        self.timeout = timeout
        self.max_pending = max_pending
        self.max_completed = max_completed
        self._pending: dict[str, PendingRequest] = {}
        self._command_ids: dict[str, str] = {}
        self._completed: OrderedDict[str, dict] = OrderedDict()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def clear_session(self) -> None:
        self._pending.clear()
        self._command_ids.clear()
        self._completed.clear()

    def accept_rpc(
        self, topic: str, payload: bytes, now: float, *,
        device_available: bool = True, retained: bool = False,
        supported_methods: tuple[str, ...] = tuple(ACTUATORS),
    ) -> Publication | None:
        if retained or not topic.startswith(RPC_REQUEST_PREFIX):
            return None
        request_id = topic.removeprefix(RPC_REQUEST_PREFIX)
        if not TOPIC_SEGMENT.fullmatch(request_id) or request_id in self._pending:
            return None
        if request_id in self._completed:
            return Publication(RPC_RESPONSE_PREFIX + request_id, self._completed[request_id])

        command_id = f"cmd-{uuid4().hex}"
        try:
            request = json_object(payload)
        except ValueError:
            return self._finish(request_id, failure(command_id, "invalid_json"))
        method = request.get("method")
        value = request.get("params")
        if not isinstance(method, str) or method not in supported_methods:
            return self._finish(request_id, failure(command_id, "unsupported_method"))
        if type(value) is not bool:
            return self._finish(request_id, failure(command_id, "invalid_value"))
        if not device_available:
            return self._finish(request_id, failure(command_id, "unknown_device"))
        if self.pending_count >= self.max_pending:
            return self._finish(request_id, failure(command_id, "gateway_busy"))

        self._pending[request_id] = PendingRequest(request_id, command_id, now + self.timeout, value)
        self._command_ids[command_id] = request_id
        return Publication(self.command_topic, {"id": command_id, "method": method, "value": value, "source": "coreiot"})

    def accept_ack(self, topic: str, body: dict, now: float) -> Publication | None:
        if topic != self.ack_topic or not valid_ack(body):
            return None
        request_id = self._command_ids.get(body["id"])
        if request_id is None or now >= self._pending[request_id].deadline:
            return None
        if body["ok"] and body["actualState"] is not self._pending[request_id].requested_state:
            body = {**body, "ok": False, "error": "unexpected_state"}
        return self._finish(request_id, body)

    def expire(self, now: float) -> list[Publication]:
        expired = [request for request in self._pending.values() if now >= request.deadline]
        return [
            self._finish(request.request_id, failure(request.command_id, "device_timeout"))
            for request in expired
        ]

    def reject_command(self, command_id: str, error: str) -> Publication:
        """Complete a pending request when the local transport rejects its command."""
        return self._finish(self._command_ids[command_id], failure(command_id, error))

    def reject_pending(self, error: str) -> list[Publication]:
        return [self.reject_command(command_id, error) for command_id in tuple(self._command_ids)]

    def _finish(self, request_id: str, body: dict) -> Publication:
        pending = self._pending.pop(request_id, None)
        if pending is not None:
            del self._command_ids[pending.command_id]
        self._completed[request_id] = body
        if len(self._completed) > self.max_completed:
            self._completed.popitem(last=False)
        return Publication(RPC_RESPONSE_PREFIX + request_id, body)
