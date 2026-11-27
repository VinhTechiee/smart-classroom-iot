"""Bridge one classroom's local MQTT traffic to its CoreIOT device session."""

import argparse
import json
import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep, time_ns
from typing import Callable
from uuid import uuid4

import paho.mqtt.client as mqtt

from coreiot.simulator.__main__ import parse_connection, read_environment
from coreiot.simulator.gateway import (
    ACTUATORS,
    MAX_MQTT_PAYLOAD_BYTES,
    RPC_REQUEST_PREFIX,
    Publication,
    RpcBridge,
    cloud_telemetry,
    json_object,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerSettings:
    host: str
    port: int
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    tls: ssl.SSLContext | None = None


def local_broker_settings(values: dict[str, str]) -> BrokerSettings:
    port = int(values.get("GATEWAY_MQTT_PORT", "1883"))
    if not 1 <= port <= 65535:
        raise ValueError("GATEWAY_MQTT_PORT must be between 1 and 65535")
    return BrokerSettings(
        values.get("GATEWAY_MQTT_HOST", "127.0.0.1"), port,
        values.get("GATEWAY_MQTT_USERNAME") or None, values.get("GATEWAY_MQTT_PASSWORD") or None,
    )


class MqttLink:
    """Poll a broker and create a fresh client after each disconnection."""

    def __init__(
        self, name: str, settings: BrokerSettings, topics: tuple[str, ...],
        on_message: Callable[[mqtt.MQTTMessage], None], on_close: Callable[[], None] | None = None,
    ):
        self.name = name
        self.settings = settings
        self.topics = topics
        self.handle_message = on_message
        self.on_close = on_close
        self.ready = False
        self.client = None
        self.failed = False
        self.subscribe_mid = None
        self.deadline = 0.0
        self.retry_at = 0.0
        self.retry_delay = 1.0
        self.before_suback = []

    def _connect(self):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"sc-b-{uuid4().hex[:17]}", reconnect_on_failure=False,
        )
        client.connect_timeout = 1.5
        client.max_queued_messages_set(128)
        if self.settings.username is not None:
            client.username_pw_set(self.settings.username, self.settings.password)
        if self.settings.tls is not None:
            client.tls_set_context(self.settings.tls)
        client.on_connect = self._on_connect
        client.on_subscribe = self._on_subscribe
        client.on_message = self._on_message
        self.client = client
        self.failed = False
        self.deadline = monotonic() + 5
        return client.connect(self.settings.host, self.settings.port, keepalive=30)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOGGER.warning("%s rejected connection: %s", self.name, reason_code)
            self.failed = True
            return
        result, self.subscribe_mid = client.subscribe([(topic, 1) for topic in self.topics])
        self.failed = result != mqtt.MQTT_ERR_SUCCESS

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if mid != self.subscribe_mid or len(reason_codes) != len(self.topics) or any(
            reason.is_failure for reason in reason_codes
        ):
            LOGGER.warning("%s rejected subscription", self.name)
            self.failed = True
            return
        self.ready = True
        self.retry_delay = 1.0
        LOGGER.info("%s ready at %s:%s", self.name, self.settings.host, self.settings.port)
        for message in self.before_suback:
            self.handle_message(message)
        self.before_suback.clear()

    def _on_message(self, client, userdata, message):
        if self.ready:
            self.handle_message(message)
        elif self.subscribe_mid is not None and len(self.before_suback) < 64:
            # MQTT publications may arrive after SUBSCRIBE but before SUBACK.
            if len(message.payload) <= MAX_MQTT_PAYLOAD_BYTES:
                self.before_suback.append(message)

    def pump(self):
        try:
            if self.client is None:
                if monotonic() < self.retry_at:
                    return
                result = self._connect()
            else:
                result = self.client.loop(timeout=0.025)
            if result != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.warning("%s: %s", self.name, mqtt.error_string(result))
            elif not self.failed and (self.ready or monotonic() < self.deadline):
                return
        except OSError as exc:
            LOGGER.warning("%s connection error: %s", self.name, exc)
        self.close()
        self.retry_at = monotonic() + self.retry_delay
        self.retry_delay = min(2 * self.retry_delay, 8)

    def publish(self, publication: Publication) -> bool:
        if not self.ready:
            return False
        info = self.client.publish(publication.topic, json.dumps(publication.body, allow_nan=False), qos=1)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            return True
        LOGGER.warning("%s could not publish %s: %s", self.name, publication.topic, mqtt.error_string(info.rc))
        return False

    def close(self):
        self.ready = False
        self.subscribe_mid = None
        self.before_suback.clear()
        if self.client is not None:
            self.client.disconnect()
            if sock := self.client.socket():
                sock.close()
            self.client = None
        if self.on_close is not None:
            self.on_close()


class ClassroomGateway:
    def __init__(self, device_id: str, local: BrokerSettings, cloud: BrokerSettings, *, minimal: bool = True):
        self.rpc = RpcBridge(device_id, timeout=3.5)
        self.telemetry_topic = f"classroom/{device_id}/telemetry"
        self.minimal = minimal
        self.methods = ("setLamp",) if minimal else tuple(ACTUATORS)
        self.pending_telemetry = None
        self.local = MqttLink("Local MQTT", local, (self.telemetry_topic, self.rpc.ack_topic), self.on_local_message)
        self.cloud = MqttLink("CoreIOT", cloud, (RPC_REQUEST_PREFIX + "+",), self.on_rpc, self.rpc.clear_session)

    def on_local_message(self, message: mqtt.MQTTMessage):
        if message.retain:
            return
        try:
            body = json_object(message.payload)
            if message.topic == self.telemetry_topic:
                self.pending_telemetry = cloud_telemetry(
                    message.topic, body, self.rpc.device_id, time_ns() // 1_000_000, minimal=self.minimal,
                )
            elif self.cloud.ready:
                response = self.rpc.accept_ack(message.topic, body, monotonic())
                if response is not None:
                    self.reply(response)
        except ValueError as exc:
            LOGGER.warning("Ignored %s: %s", message.topic, exc)

    def on_rpc(self, message: mqtt.MQTTMessage):
        command = self.rpc.accept_rpc(
            message.topic, message.payload, monotonic(), retained=message.retain, supported_methods=self.methods,
        )
        if command is None:
            return
        if command.topic != self.rpc.command_topic:
            self.reply(command)
        elif self.local.publish(command):
            LOGGER.info("RPC %s -> %s (%s)", message.topic, command.body["method"], command.body["id"])
        else:
            self.reply(self.rpc.reject_command(command.body["id"], "local_broker_unavailable"))

    def reply(self, response: Publication):
        if self.cloud.publish(response):
            LOGGER.info("ACK %s %s", response.topic, json.dumps(response.body))

    def run(self):
        try:
            while True:
                self.cloud.pump()
                self.local.pump()
                for response in self.rpc.expire(monotonic()):
                    self.reply(response)
                if self.pending_telemetry is not None and self.cloud.publish(self.pending_telemetry):
                    LOGGER.info("Telemetry %s", json.dumps(self.pending_telemetry.body))
                    self.pending_telemetry = None
                sleep(0.01)
        finally:
            self.local.close()
            self.cloud.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Load connection settings from this file")
    parser.add_argument("--device-id", help="Override COREIOT_DEVICE_ID for the selected token")
    parser.add_argument("--extended", action="store_true", help="Use the full kit telemetry and actuator profile")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        values = read_environment(args.env_file)
        local = local_broker_settings(values)
        host, port, token, use_tls, ca_file = parse_connection(values)
        tls = ssl.create_default_context(cafile=ca_file) if use_tls else None
        cloud = BrokerSettings(host, port, username=token, tls=tls)
        device_id = args.device_id or values.get("COREIOT_DEVICE_ID") or "classroom-01"
        ClassroomGateway(device_id, local, cloud, minimal=not args.extended).run()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        LOGGER.info("Gateway stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
