"""MQTT 3.1.1 transport for the synthetic gateway."""

from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass, field
from threading import Event
from time import monotonic, time_ns
from uuid import uuid4

import paho.mqtt.client as mqtt

from .classroom import Simulator, log_event
from shared.coreiot import RPC_REQUEST_PREFIX, RPC_RESPONSE_PREFIX, Publication


@dataclass(frozen=True)
class MqttSettings:
    hostname: str
    port: int
    token: str = field(repr=False)
    use_tls: bool = True
    ca_file: str | None = None


class MqttSession:
    """Own one Paho client and discard its outgoing queue at reconnect."""

    def __init__(self, settings: MqttSettings, simulator: Simulator, stop: Event) -> None:
        self.simulator = simulator
        self.stop = stop
        self.device_id = simulator.bridge.device_id
        self.ready = False
        self.failed = False
        self.closing = False
        self.subscription_mid: int | None = None
        self.pending_publishes: set[int] = set()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"sc-{uuid4().hex[:19]}",
            clean_session=True, protocol=mqtt.MQTTv311, reconnect_on_failure=False,
        )
        self.client.username_pw_set(settings.token)
        self.client.connect_timeout = 5.0
        self.client.max_inflight_messages_set(32)
        self.client.max_queued_messages_set(128)
        if settings.use_tls:
            self.client.tls_set_context(ssl.create_default_context(cafile=settings.ca_file))
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            self.failed = True
            log_event("mqtt_connect_rejected", level=logging.WARNING, device_id=self.device_id, code=str(reason_code))
            return
        log_event("mqtt_connected", device_id=self.device_id)
        result, subscription_mid = client.subscribe(RPC_REQUEST_PREFIX + "+", qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.failed = True
            log_event("rpc_subscribe_error", level=logging.WARNING, device_id=self.device_id, code=int(result))
            return
        self.subscription_mid = subscription_mid
        self.simulator.connected(monotonic())

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        if mid != self.subscription_mid or len(reason_codes) != 1 or reason_codes[0].is_failure:
            self.failed = True
            log_event("rpc_subscription_rejected", level=logging.WARNING, device_id=self.device_id)
            return
        self.ready = True
        log_event("rpc_subscription_ready", device_id=self.device_id, qos=reason_codes[0].value)

    def _on_message(self, client, userdata, message) -> None:
        # MQTT permits matching publications before SUBACK. Queue their device
        # work now; the run loop starts stepping the simulator after SUBACK.
        if self.subscription_mid is not None and not self.failed and not self.closing and not self.stop.is_set():
            outgoing = self.simulator.receive_rpc(
                message.topic, message.payload, monotonic(), retained=message.retain, duplicate=message.dup,
            )
            self.publish(outgoing)

    def _on_publish(self, client, userdata, mid, reason_code, properties) -> None:
        self.pending_publishes.discard(mid)
        if not reason_code.is_failure:
            log_event("mqtt_puback", device_id=self.device_id, mid=mid)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.close_state(str(reason_code))

    def close_state(self, reason: str) -> None:
        if self.subscription_mid is not None:
            dropped = self.simulator.disconnected()
            log_event("mqtt_disconnected", device_id=self.device_id, reason=reason, cancelled_requests=dropped)
        self.subscription_mid = None
        self.ready = False
        self.pending_publishes.clear()

    def close(self) -> None:
        self.closing = True
        stop_requested = self.stop.is_set()
        if stop_requested and self.ready:
            deadline = monotonic() + 0.350
            while self.pending_publishes:
                remaining = deadline - monotonic()
                if remaining <= 0 or self.client.loop(timeout=min(0.05, remaining)) != mqtt.MQTT_ERR_SUCCESS:
                    break
            if self.pending_publishes:
                log_event(
                    "mqtt_shutdown_pending", level=logging.WARNING, device_id=self.device_id,
                    unacknowledged=len(self.pending_publishes),
                )

        result = self.client.disconnect()
        write_deadline = monotonic() + 0.150
        while result == mqtt.MQTT_ERR_SUCCESS and self.client.want_write():
            remaining = write_deadline - monotonic()
            if remaining <= 0:
                break
            result = self.client.loop(timeout=min(0.05, remaining))
        sock = self.client.socket()
        if sock is not None:
            sock.close()
        self.close_state("shutdown" if stop_requested else "reconnect")

    def publish(self, publications: list[Publication]) -> None:
        for publication in publications:
            info = self.client.publish(
                publication.topic, json.dumps(publication.body, allow_nan=False, separators=(",", ":")),
                qos=1, retain=False,
            )
            details = {"device_id": self.device_id, "mid": info.mid, "topic": publication.topic}
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                log_event("mqtt_publish_error", level=logging.WARNING, code=int(info.rc), **details)
                continue
            self.pending_publishes.add(info.mid)
            if publication.topic.startswith(RPC_RESPONSE_PREFIX):
                log_event("rpc_response_queued", response=publication.body, **details)
            else:
                log_event("telemetry_queued", telemetry=publication.body, **details)


def run(settings: MqttSettings, simulator: Simulator, stop: Event) -> None:
    """Poll one connection at a time and reconnect with a bounded backoff."""
    retry = 1.0
    while not stop.is_set():
        session = MqttSession(settings, simulator, stop)
        log_event("mqtt_connecting", device_id=session.device_id, host=settings.hostname, port=settings.port)
        try:
            result = session.client.connect(settings.hostname, settings.port, keepalive=30)
            ready_deadline = monotonic() + 5
            while result == mqtt.MQTT_ERR_SUCCESS and not session.failed and not stop.is_set():
                result = session.client.loop(timeout=0.05)
                if result != mqtt.MQTT_ERR_SUCCESS or session.failed or stop.is_set():
                    break
                now = monotonic()
                if session.ready:
                    retry = 1.0
                    session.publish(simulator.step(now, time_ns() // 1_000_000))
                elif now >= ready_deadline:
                    log_event("mqtt_subscription_timeout", level=logging.WARNING, device_id=session.device_id)
                    break
            if result != mqtt.MQTT_ERR_SUCCESS and not stop.is_set():
                log_event("mqtt_loop_ended", level=logging.WARNING, device_id=session.device_id, code=int(result))
        except OSError as exc:
            log_event("mqtt_connection_error", level=logging.WARNING, device_id=session.device_id, error=str(exc))
        finally:
            session.close()
        if not stop.is_set():
            log_event("mqtt_retry_scheduled", device_id=session.device_id, seconds=retry)
            stop.wait(retry)
            retry = min(retry * 2, 15.0)
    log_event("simulator_stopped", device_id=simulator.bridge.device_id)
