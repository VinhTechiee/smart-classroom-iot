"""Exercise the Paho adapter against a minimal local MQTT 3.1.1 peer."""

import json
import os
import socket
import subprocess
import sys
import unittest
from collections import Counter
from threading import Event, Thread
from time import monotonic

from coreiot.simulator.classroom import Simulator
from shared.coreiot import RPC_REQUEST_PREFIX, RPC_RESPONSE_PREFIX, TELEMETRY_TOPIC, RpcBridge

try:
    from coreiot.simulator.mqtt_client import MqttSettings, run
except ModuleNotFoundError as exc:
    if exc.name != "paho":
        raise
    run = None


def wire_field(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def take_field(body: bytes) -> tuple[bytes, bytes]:
    count = int.from_bytes(body[:2], "big")
    return body[2:2 + count], body[2 + count:]


def send_packet(connection: socket.socket, header: int, payload: bytes = b"") -> None:
    remaining = len(payload)
    encoded = bytearray([header])
    while remaining >= 128:
        encoded.append((remaining % 128) | 0x80)
        remaining //= 128
    encoded.append(remaining)
    connection.sendall(encoded + payload)


def read_exact(connection: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        part = connection.recv(count - len(data))
        if not part:
            raise EOFError("MQTT stream closed")
        data.extend(part)
    return bytes(data)


def read_packet(connection: socket.socket) -> tuple[int, bytes]:
    header = read_exact(connection, 1)[0]
    remaining = 0
    for shift in range(0, 22, 7):
        byte = read_exact(connection, 1)[0]
        remaining |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return header, read_exact(connection, remaining)
    raise AssertionError("Invalid MQTT packet length")


@unittest.skipIf(run is None, "install coreiot/simulator/requirements.txt for MQTT loopback")
class MqttLoopbackTests(unittest.TestCase):
    def read_subscription(self, connection: socket.socket) -> tuple[bytes, bytes]:
        connection.settimeout(5)
        header, body = read_packet(connection)
        self.assertEqual(header, 0x10)
        self.assertEqual(body[:7], b"\x00\x04MQTT\x04")
        self.assertEqual(body[7], 0x82)  # Username and clean session.
        client_id, remaining = take_field(body[10:])
        self.assertEqual(take_field(remaining), (b"loopback-token", b""))
        send_packet(connection, 0x20, b"\x00\x00")
        header, body = read_packet(connection)
        self.assertEqual(header, 0x82)
        self.assertEqual(body[2:], wire_field(RPC_REQUEST_PREFIX + "+") + b"\x01")
        return client_id, body[:2]

    def connect_peer(self, connection: socket.socket) -> bytes:
        client_id, subscription_id = self.read_subscription(connection)
        send_packet(connection, 0x90, subscription_id + b"\x01")
        return client_id

    def command(self, connection, request_id, packet_id, method, value, *, duplicate=False, retained=False):
        payload = json.dumps({"method": method, "params": value}).encode("utf-8")
        message = wire_field(RPC_REQUEST_PREFIX + request_id) + packet_id.to_bytes(2, "big") + payload
        header = (0x3A if duplicate else 0x32) | int(retained)
        send_packet(connection, header, message)

    def publications(
        self, connection: socket.socket, count: int, *, defer_pubacks: list[bytes] | None = None,
    ) -> tuple[list[tuple[str, dict]], Counter]:
        messages = []
        acknowledgements = Counter()
        while len(messages) < count:
            header, body = read_packet(connection)
            if header == 0x40:
                acknowledgements[int.from_bytes(body, "big")] += 1
                continue
            self.assertEqual(header, 0x32)  # QoS 1 without retain.
            topic, payload = take_field(body)
            if defer_pubacks is not None:
                defer_pubacks.append(payload[:2])
            else:
                send_packet(connection, 0x40, payload[:2])
            messages.append((topic.decode("utf-8"), json.loads(payload[2:])))
        return messages, acknowledgements

    def test_minimal_cli_publishes_available_values_and_led_ack(self):
        with socket.socket() as broker:
            broker.bind(("127.0.0.1", 0))
            broker.listen()
            broker.settimeout(5)
            env = {
                **os.environ,
                "COREIOT_MQTT_URL": f"mqtt://127.0.0.1:{broker.getsockname()[1]}",
                "COREIOT_DEVICE_TOKEN": "loopback-token",
                "COREIOT_MQTT_CA_FILE": "",
            }
            args = [sys.executable, "-m", "coreiot.simulator", "--minimal", "--device-id", "classroom-01-sim",
                    "--omit-humidity", "--temperature", "27", "--interval-ms", "60000"]
            with subprocess.Popen(args, env=env, stderr=subprocess.DEVNULL) as client:
                try:
                    peer, _ = broker.accept()
                    with peer:
                        self.connect_peer(peer)
                        [(topic, sample)], _ = self.publications(peer, 1)
                        self.assertEqual(topic, TELEMETRY_TOPIC)
                        self.assertEqual(sample["values"], {
                            "deviceId": "classroom-01-sim", "ts": sample["ts"],
                            "temperature": 27, "lamp": False, "fwVersion": "1.0.0",
                        })
                        self.command(peer, "42", 10, "setLamp", True)
                        [(response_topic, ack), (report_topic, report)], _ = self.publications(peer, 2)
                        self.assertEqual((response_topic, report_topic), (RPC_RESPONSE_PREFIX + "42", TELEMETRY_TOPIC))
                        self.assertIs(ack["ok"], True)
                        self.assertIs(ack["actualState"], True)
                        self.assertIs(report["values"]["lamp"], True)
                        self.assertGreater(report["ts"], sample["ts"])
                        self.assertNotIn("humidity", report["values"])
                finally:
                    client.terminate()

    def test_auth_subscription_rpc_state_qos_retransmission_and_reconnect(self):
        with socket.socket() as broker:
            broker.bind(("127.0.0.1", 0))
            broker.listen()
            broker.settimeout(5)
            connect = MqttSettings("127.0.0.1", broker.getsockname()[1], "loopback-token", use_tls=False)
            simulator = Simulator(RpcBridge("classroom-01", 2), readings={"fwVersion": "1.1.0"}, interval=60)
            stop = Event()
            client = Thread(target=run, args=(connect, simulator, stop), daemon=True)
            client.start()
            try:
                first, _ = broker.accept()
                with first:
                    first_id = self.connect_peer(first)
                    initial, _ = self.publications(first, 1)
                    self.assertEqual(initial[0][0], TELEMETRY_TOPIC)
                    self.assertEqual(initial[0][1]["values"]["fwVersion"], "1.1.0")

                    self.command(first, "retained", 9, "setLamp", True, retained=True)
                    self.assertEqual(read_packet(first), (0x40, b"\x00\x09"))
                    self.command(first, "42", 10, "setDoor", True)
                    messages, pubacks = self.publications(first, 2)
                    self.assertEqual(pubacks, {10: 1})
                    self.assertEqual([topic for topic, _ in messages], [RPC_RESPONSE_PREFIX + "42", TELEMETRY_TOPIC])
                    first_ack = messages[0][1]
                    self.assertTrue(first_ack["ok"] and first_ack["actualState"])
                    self.assertTrue(messages[1][1]["values"]["door"])
                    self.assertIs(messages[1][1]["values"]["lamp"], False)
                    self.assertEqual(first_ack["ts"], messages[1][1]["ts"])

                    self.command(first, "42", 10, "setDoor", True, duplicate=True)
                    self.command(first, "43", 11, "setDoor", 1)
                    replies, _ = self.publications(first, 2)
                    self.assertEqual(replies[0], (RPC_RESPONSE_PREFIX + "42", first_ack))
                    self.assertEqual(replies[1][0], RPC_RESPONSE_PREFIX + "43")
                    self.assertEqual(replies[1][1]["error"], "invalid_value")
                    self.assertIs(simulator.sample(0).body["values"]["door"], True)

                second, _ = broker.accept()
                with second:
                    self.assertNotEqual(self.connect_peer(second), first_id)
                    resumed, _ = self.publications(second, 1)
                    self.assertEqual(resumed[0][0], TELEMETRY_TOPIC)
                    self.assertTrue(resumed[0][1]["values"]["door"])
                    self.command(second, "42", 12, "setDoor", False)
                    deferred = []
                    messages, _ = self.publications(second, 2, defer_pubacks=deferred)
                    next_ack = messages[0][1]
                    self.assertEqual(messages[0][0], RPC_RESPONSE_PREFIX + "42")
                    self.assertNotEqual(next_ack["id"], first_ack["id"])
                    self.assertTrue(next_ack["ok"])
                    self.assertFalse(next_ack["actualState"])
                    self.assertFalse(messages[1][1]["values"]["door"])
                    stop.set()
                    self.command(second, "44", 13, "setLamp", True)
                    self.assertEqual(read_packet(second), (0x40, b"\x00\x0d"))
                    for message_id in deferred:
                        send_packet(second, 0x40, message_id)
                    self.assertEqual(read_packet(second), (0xE0, b""))
            finally:
                stop.set()
                client.join(6)
            self.assertFalse(client.is_alive())
            self.assertFalse(simulator.sample(0).body["values"]["lamp"])

    def test_shutdown_is_bounded_when_broker_never_acknowledges_publish(self):
        with socket.socket() as broker:
            broker.bind(("127.0.0.1", 0))
            broker.listen()
            broker.settimeout(5)
            connect = MqttSettings("127.0.0.1", broker.getsockname()[1], "loopback-token", use_tls=False)
            stop = Event()
            simulator = Simulator(RpcBridge("classroom-01", 2))
            client = Thread(target=run, args=(connect, simulator, stop), daemon=True)
            client.start()
            try:
                peer, _ = broker.accept()
                with peer:
                    self.connect_peer(peer)
                    self.publications(peer, 1, defer_pubacks=[])
                    started_at = monotonic()
                    stop.set()
                    self.assertEqual(read_packet(peer), (0xE0, b""))
                    self.assertLess(monotonic() - started_at, 2)
            finally:
                stop.set()
                client.join(6)
            self.assertFalse(client.is_alive())

    def test_rpc_received_before_suback_executes_after_subscription_is_granted(self):
        with socket.socket() as broker:
            broker.bind(("127.0.0.1", 0))
            broker.listen()
            broker.settimeout(5)
            settings = MqttSettings("127.0.0.1", broker.getsockname()[1], "loopback-token", use_tls=False)
            simulator = Simulator(RpcBridge("classroom-01", 2), interval=60, ack_delay=0)
            stop = Event()
            client = Thread(target=run, args=(settings, simulator, stop), daemon=True)
            client.start()
            try:
                peer, _ = broker.accept()
                with peer:
                    _, subscription_id = self.read_subscription(peer)
                    self.command(peer, "42", 10, "setDoor", True)
                    self.assertEqual(read_packet(peer), (0x40, b"\x00\x0a"))
                    self.assertFalse(simulator.sample(0).body["values"]["door"])
                    send_packet(peer, 0x90, subscription_id + b"\x01")
                    messages, _ = self.publications(peer, 2)
                    self.assertEqual([topic for topic, _ in messages], [RPC_RESPONSE_PREFIX + "42", TELEMETRY_TOPIC])
                    self.assertTrue(messages[0][1]["actualState"])
                    self.assertTrue(messages[1][1]["values"]["door"])
            finally:
                stop.set()
                client.join(6)
            self.assertFalse(client.is_alive())


if __name__ == "__main__":
    unittest.main()
