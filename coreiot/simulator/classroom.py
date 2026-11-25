"""Synthetic local device and timing for the cloud-facing gateway."""

import json
import logging
import math
from collections import deque
from datetime import datetime, timezone

from .gateway import ACTUATORS, Publication, RpcBridge, cloud_telemetry

LOGGER = logging.getLogger("coreiot.simulator")
LOGGER.addHandler(logging.NullHandler())

DEFAULT_READINGS = {
    "temperature": 28.5,
    "humidity": 65.0,
    "light": 320,
    "motion": True,
    "distance": 42.0,
    "lamp": False,
    "fan": False,
    "door": False,
    "fwVersion": "1.0.0",
}


def log_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    LOGGER.log(level, "%s", json.dumps({
        "time": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level),
        "event": event,
        "synthetic": True,
        **fields,
    }))


class Simulator:
    """Run synthetic local commands and cloud publications in a single event loop."""

    def __init__(
        self, bridge: RpcBridge, *, readings: dict | None = None, interval: float = 5,
        ack_delay: float = 0.050, synchronized: bool = True, device_present: bool = True,
        device_online: bool = True, drop_ack: bool = False,
    ) -> None:
        if not math.isfinite(interval) or interval <= 0 or not math.isfinite(ack_delay) or ack_delay < 0:
            raise ValueError("Telemetry interval must be positive and ACK delay must be nonnegative")
        self.bridge = bridge
        self.interval = interval
        self.ack_delay = ack_delay
        self.synchronized = synchronized
        self.device_present = device_present
        self.device_online = device_online
        self.drop_ack = drop_ack
        self.telemetry_topic = f"classroom/{bridge.device_id}/telemetry"
        self._values = {**DEFAULT_READINGS, **(readings or {}), "deviceId": bridge.device_id}
        self._commands: deque[tuple[float, Publication]] = deque()
        self._next_telemetry = 0.0
        self._last_sample_ms = -1
        self._connected = False
        self.sample(0)

    def connected(self, now: float) -> None:
        self.disconnected()
        self._next_telemetry = now
        self._connected = True

    def disconnected(self) -> int:
        cancelled = self.bridge.pending_count
        self._connected = False
        self.bridge.clear_session()
        self._commands.clear()
        return cancelled

    def sample(self, wall_ms: int) -> Publication:
        source = {**self._values, "ts": wall_ms if self.synchronized else None}
        return cloud_telemetry(self.telemetry_topic, source, self.bridge.device_id, wall_ms)

    def receive_rpc(
        self, topic: str, payload: bytes, now: float, *, retained: bool = False, duplicate: bool = False,
    ) -> list[Publication]:
        if not self._connected:
            return []

        output = self.bridge.expire(now)
        if duplicate:
            log_event("mqtt_duplicate_received", device_id=self.bridge.device_id, topic=topic)
        outgoing = self.bridge.accept_rpc(
            topic, payload, now, device_available=self.device_present, retained=retained,
        )
        if outgoing is None:
            return output
        if outgoing.topic != self.bridge.command_topic:
            return [*output, outgoing]

        command_id = outgoing.body["id"]
        if len(self._commands) >= self.bridge.max_pending:
            return [*output, self.bridge.reject_command(command_id, "gateway_busy")]
        log_event(
            "simulated_command", device_id=self.bridge.device_id, topic=outgoing.topic,
            command_id=command_id, method=outgoing.body["method"], value=outgoing.body["value"],
        )
        if self.device_online:
            self._commands.append((now + self.ack_delay, outgoing))
        return output

    def step(self, now: float, wall_ms: int) -> list[Publication]:
        if not self._connected:
            return []
        output = self.bridge.expire(now)
        while self._commands and now >= self._commands[0][0]:
            _, command = self._commands.popleft()
            actuator = ACTUATORS[command.body["method"]]
            state = command.body["value"]
            command_id = command.body["id"]
            self._values[actuator] = state
            telemetry = self._fresh_sample(now, wall_ms)
            if self.drop_ack:
                log_event("simulated_ack_dropped", device_id=self.bridge.device_id, command_id=command_id)
                output.append(telemetry)
                continue
            ack = {
                "id": command_id, "ok": True, "actualState": state,
                "ts": telemetry.body["ts"] if self.synchronized else None,
            }
            response = self.bridge.accept_ack(self.bridge.ack_topic, ack, now)
            if response is None:
                log_event(
                    "late_or_unmatched_ack", level=logging.WARNING,
                    device_id=self.bridge.device_id, command_id=command_id,
                )
            else:
                output.append(response)
            output.append(telemetry)
        if self.device_present and self.device_online and now >= self._next_telemetry:
            output.append(self._fresh_sample(now, wall_ms))
        return output

    def _fresh_sample(self, now: float, wall_ms: int) -> Publication:
        self._next_telemetry = now + self.interval
        # Keep distinct sample keys when several synthetic actions share a clock tick.
        self._last_sample_ms = max(wall_ms, self._last_sample_ms + 1)
        return self.sample(self._last_sample_ms)
