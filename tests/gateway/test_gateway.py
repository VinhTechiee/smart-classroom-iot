"""Exercise the gateway and the device simulator on MQTT 3.1.1 TCP connections."""

import json
import os
import socket
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep, time_ns
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.coreiot.test_mqtt_loopback import read_packet, send_packet, take_field, wire_field


DEVICE = "classroom-01-sim"
LOCAL = f"classroom/{DEVICE}/"
RPC_REQUEST = "v1/devices/me/rpc/request/"
RPC_RESPONSE = "v1/devices/me/rpc/response/"
CLOUD_TELEMETRY = "v1/devices/me/telemetry"


class GatewayLoopbackTests(unittest.TestCase):
    def broker(self):
        listener = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(listener.close)
        listener.settimeout(8)
        return listener

    def launch(self, arguments, **environment):
        process = subprocess.Popen(
            [sys.executable, "-B", *arguments], env={**os.environ, **environment},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        def finish():
            exited = process.poll() is not None
            if not exited:
                process.terminate()
            output, _ = process.communicate(timeout=5)
            if exited:
                self.fail(f"{arguments} exited unexpectedly ({process.returncode}):\n{output}")

        self.addCleanup(finish)
        return process

    def connect(self, broker, topics, *, username=None):
        connection, _ = broker.accept()
        self.addCleanup(connection.close)
        connection.settimeout(7)
        header, body = read_packet(connection)
        self.assertEqual(header, 0x10)
        self.assertEqual(body[:7], b"\x00\x04MQTT\x04")
        client_id, credentials = take_field(body[10:])
        if username is not None:
            self.assertEqual(take_field(credentials), (username.encode(), b""))
        send_packet(connection, 0x20, b"\x00\x00")
        header, body = read_packet(connection)
        self.assertEqual(header, 0x82)
        self.assertEqual(body[2:], b"".join(wire_field(topic) + b"\x01" for topic in topics))
        send_packet(connection, 0x90, body[:2] + b"\x01" * len(topics))
        return connection, client_id

    def publish(self, connection, topic, body, *, retained=False):
        send_packet(connection, 0x32 | retained, wire_field(topic) + b"\x00\x01" + json.dumps(body).encode())

    def receive(self, connection):
        while True:
            header, body = read_packet(connection)
            if header != 0x40:  # The client can ACK our inbound publications separately.
                break
        self.assertEqual(header, 0x32)
        topic, remaining = take_field(body)
        send_packet(connection, 0x40, remaining[:2])
        return topic.decode(), json.loads(remaining[2:])

    def start_gateway(self, device=DEVICE):
        local = self.broker()
        self.local_listener = local
        cloud = self.broker()
        self.launch(
            ["-m", "gateway.bridge"], GATEWAY_COREIOT_DEVICE_ID=device,
            COREIOT_MQTT_URL=f"mqtt://127.0.0.1:{cloud.getsockname()[1]}",
            GATEWAY_COREIOT_DEVICE_TOKEN="gateway-test-token", COREIOT_DEVICE_TOKEN="simulator-only-token",
            COREIOT_MQTT_CA_FILE="", GATEWAY_MQTT_HOST="127.0.0.1", GATEWAY_MQTT_PORT=str(local.getsockname()[1]),
            GATEWAY_MQTT_USERNAME="", GATEWAY_MQTT_PASSWORD="",
        )
        local_prefix = f"classroom/{device}/"
        local_peer, _ = self.connect(local, (local_prefix + "telemetry", local_prefix + "ack"))
        cloud_peer, client_id = self.connect(cloud, (RPC_REQUEST + "+",), username="gateway-test-token")
        return local_peer, cloud_peer, cloud, client_id

    def test_minimal_telemetry_led_round_trip_and_timeout(self):
        local, cloud, _, _ = self.start_gateway()
        sample = {"deviceId": DEVICE, "humidity": 65, "lamp": False, "fwVersion": "1.0.0", "ts": None}
        earliest_ms = time_ns() // 1_000_000
        self.publish(local, LOCAL + "telemetry", sample)
        topic, telemetry = self.receive(cloud)
        self.assertEqual(topic, CLOUD_TELEMETRY)
        self.assertGreaterEqual(telemetry["ts"], earliest_ms)
        self.assertEqual(telemetry["values"], {key: value for key, value in sample.items() if key != "ts"})

        for request, state in (("on", True), ("off", False)):
            rpc = {"method": "setLamp", "params": state}
            self.publish(cloud, RPC_REQUEST + "retained", rpc, retained=True)
            self.publish(cloud, RPC_REQUEST + request, rpc)
            topic, command = self.receive(local)
            self.assertEqual(topic, LOCAL + "cmd")
            expires = command.pop("expiresAt")
            self.assertGreater(expires, time_ns() // 1_000_000)
            self.assertLessEqual(expires, time_ns() // 1_000_000 + 3500)
            self.assertEqual(command, {"id": command["id"], "method": "setLamp", "value": state, "source": "coreiot"})
            self.publish(cloud, RPC_REQUEST + request, rpc)
            ack = {"id": command["id"], "ok": True, "actualState": state, "ts": None}
            self.publish(local, LOCAL + "ack", {**ack, "id": "unrelated"})
            self.publish(local, LOCAL + "ack", ack)
            self.assertEqual(self.receive(cloud), (RPC_RESPONSE + request, ack))
            self.publish(local, LOCAL + "telemetry", {**sample, "lamp": state})
            topic, telemetry = self.receive(cloud)
            self.assertEqual(topic, CLOUD_TELEMETRY)
            self.assertIs(telemetry["values"]["lamp"], state)
            self.publish(cloud, RPC_REQUEST + request, rpc)
            self.assertEqual(self.receive(cloud), (RPC_RESPONSE + request, ack))

        self.publish(cloud, RPC_REQUEST + "invalid", {"method": "setFan", "params": True})
        topic, rejection = self.receive(cloud)
        self.assertEqual(topic, RPC_RESPONSE + "invalid")
        self.assertEqual(rejection["error"], "unsupported_method")
        self.publish(cloud, RPC_REQUEST + "missing", {"method": "setLamp", "params": True})
        _, command = self.receive(local)
        topic, timeout = self.receive(cloud)
        self.assertEqual(topic, RPC_RESPONSE + "missing")
        self.assertEqual((timeout["id"], timeout["error"]), (command["id"], "device_timeout"))

    def test_cloud_reconnect_drops_previous_session_mappings(self):
        local, cloud, listener, client_id = self.start_gateway()
        rpc = {"method": "setLamp", "params": True}
        self.publish(cloud, RPC_REQUEST + "1", rpc)
        _, old_command = self.receive(local)
        cloud.shutdown(socket.SHUT_RDWR)
        cloud.close()

        cloud, new_client_id = self.connect(listener, (RPC_REQUEST + "+",), username="gateway-test-token")
        self.assertNotEqual(client_id, new_client_id)
        self.publish(cloud, RPC_REQUEST + "1", rpc)
        _, new_command = self.receive(local)
        self.assertNotEqual(old_command["id"], new_command["id"])
        ack = {"ok": True, "actualState": True, "ts": None}
        self.publish(local, LOCAL + "ack", {**ack, "id": old_command["id"]})
        self.publish(local, LOCAL + "ack", {**ack, "id": new_command["id"]})
        self.assertEqual(self.receive(cloud), (RPC_RESPONSE + "1", {**ack, "id": new_command["id"]}))

    def test_firmware_payload_filters_mock_and_stale_readings_and_keeps_unknowns(self):
        device = "classroom-01"
        local, cloud, _, _ = self.start_gateway(device)
        prefix = f"classroom/{device}/"
        sample = {
            "deviceId": device, "ts": None, "temperature": None, "humidity": None,
            "light": None, "motion": None, "distance": None, "lamp": False,
            "door": None, "fwVersion": "1.0.0", "mockMode": False,
        }
        for invalid in (
            {**sample, "mockMode": True, "humidity": 86},
            {**sample, "ts": 15200, "humidity": 87},
            {**sample, "ts": time_ns() // 1_000_000 - 31000, "humidity": 88},
            {**sample, "humidity": 101},
            {**sample, "light": 4096},
            {**sample, "light": 300.5},
            {**sample, "motion": 0},
            {**sample, "distance": 401},
            {**sample, "deviceId": "classroom-01-sim"},
        ):
            self.publish(local, prefix + "telemetry", invalid)
        self.publish(local, prefix + "telemetry", sample)
        topic, report = self.receive(cloud)
        self.assertEqual(topic, CLOUD_TELEMETRY)
        self.assertEqual(report["values"], {"deviceId": device, "lamp": False, "fwVersion": "1.0.0"})

        self.publish(cloud, RPC_REQUEST + "physical", {"method": "setLamp", "params": True})
        topic, command = self.receive(local)
        self.assertEqual(topic, prefix + "cmd")
        self.assertGreater(command["expiresAt"], time_ns() // 1_000_000)
        ack = {"id": command["id"], "ok": True, "actualState": False, "ts": None}
        self.publish(local, prefix + "ack", ack)
        self.assertEqual(self.receive(cloud), (
            RPC_RESPONSE + "physical", {**ack, "ok": False, "error": "unexpected_state"},
        ))

        expanded = {**sample, "temperature": 28.5, "humidity": 65, "light": 850, "motion": True,
                    "distance": 12.5, "door": False, "doorAuto": True, "fan": True}
        self.publish(local, prefix + "telemetry", expanded)
        _, report = self.receive(cloud)
        expected = {key: value for key, value in expanded.items() if key not in ("ts", "mockMode", "doorAuto", "fan")}
        self.assertEqual(report["values"], expected)

        for request, desired in (("open", True), ("close", False)):
            self.publish(cloud, RPC_REQUEST + request, {"method": "setDoor", "params": desired})
            topic, command = self.receive(local)
            self.assertEqual((topic, command["method"], command["value"]), (prefix + "cmd", "setDoor", desired))
            ack = {"id": command["id"], "ok": True, "actualState": desired, "ts": None}
            self.publish(local, prefix + "ack", {**ack, "id": "previous-door-command"})
            self.publish(local, prefix + "ack", ack)
            self.assertEqual(self.receive(cloud), (RPC_RESPONSE + request, ack))
            before = time_ns() // 1_000_000
            self.publish(local, prefix + "telemetry", {**expanded, "door": desired, "doorAuto": False})
            topic, report = self.receive(cloud)
            self.assertEqual(topic, CLOUD_TELEMETRY)
            self.assertEqual(report["values"], {**expected, "door": desired})
            self.assertGreaterEqual(report["ts"], before)

        for method in ("setFan", "setDoorAuto"):
            self.publish(cloud, RPC_REQUEST + method, {"method": method, "params": True})
            topic, rejection = self.receive(cloud)
            self.assertEqual((topic, rejection["error"]), (RPC_RESPONSE + method, "unsupported_method"))

    def test_local_broker_disconnect_fails_inflight_and_allows_fresh_command(self):
        local, cloud, _, _ = self.start_gateway()
        self.publish(cloud, RPC_REQUEST + "before-loss", {"method": "setLamp", "params": False})
        _, command = self.receive(local)
        local.shutdown(socket.SHUT_RDWR)
        local.close()
        self.assertEqual(self.receive(cloud), (RPC_RESPONSE + "before-loss", {
            "id": command["id"], "ok": False, "actualState": None,
            "ts": None, "error": "local_broker_unavailable",
        }))
        local, _ = self.connect(self.local_listener, (LOCAL + "telemetry", LOCAL + "ack"))
        self.publish(local, LOCAL + "telemetry", {
            "deviceId": DEVICE, "ts": None, "humidity": 65, "lamp": False, "fwVersion": "1.0.0",
        })
        self.assertEqual(self.receive(cloud)[0], CLOUD_TELEMETRY)
        self.publish(cloud, RPC_REQUEST + "after-loss", {"method": "setLamp", "params": True})
        _, fresh = self.receive(local)
        self.assertNotEqual(command["id"], fresh["id"])
        ack = {"id": fresh["id"], "ok": True, "actualState": True, "ts": None}
        self.publish(local, LOCAL + "ack", ack)
        self.assertEqual(self.receive(cloud), (RPC_RESPONSE + "after-loss", ack))

    def test_minimal_device_simulator_publishes_new_lamp_state(self):
        broker = self.broker()
        self.launch(
            ["gateway/simulator.py", "--minimal", "--device-id", DEVICE, "--port", str(broker.getsockname()[1])],
            GATEWAY_MQTT_USERNAME="", GATEWAY_MQTT_PASSWORD="",
        )
        device, _ = self.connect(broker, (LOCAL + "cmd",))
        topic, sample = self.receive(device)
        self.assertEqual(topic, LOCAL + "telemetry")
        self.assertEqual(sample, {"deviceId": DEVICE, "ts": None, "humidity": 65, "lamp": False, "fwVersion": "1.0.0"})
        self.publish(device, LOCAL + "cmd", {"id": "lamp-on", "method": "setLamp", "value": True})
        self.assertEqual(self.receive(device), (LOCAL + "ack", {"id": "lamp-on", "ok": True, "actualState": True, "ts": None}))
        self.assertEqual(self.receive(device), (LOCAL + "telemetry", {**sample, "lamp": True}))

    def test_web_reads_telemetry_and_waits_for_matching_led_ack(self):
        broker = self.broker()
        process = self.launch(
            ["-m", "gateway.web", "--port", "0", "--device-id", DEVICE], GATEWAY_MQTT_HOST="127.0.0.1",
            GATEWAY_MQTT_PORT=str(broker.getsockname()[1]), GATEWAY_MQTT_USERNAME="", GATEWAY_MQTT_PASSWORD="",
        )
        startup = process.stdout.readline().strip()
        self.assertTrue(startup.startswith("Dashboard: http://127.0.0.1:"), startup)
        url = startup.removeprefix("Dashboard: ")
        peer, _ = self.connect(broker, (LOCAL + "telemetry", LOCAL + "ack"))
        with urlopen(url, timeout=5) as response:
            self.assertIn(b'fetch("/sensors"', response.read())

        def request(path, value=None):
            data = json.dumps({"value": value}).encode() if value is not None else None
            request = Request(url + path, data=data, headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=6) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                with error:
                    return error.code, json.load(error)

        def wait_state(key, expected):
            deadline = monotonic() + 4
            while monotonic() < deadline:
                status, body = request("/sensors")
                if body[key] is expected:
                    self.assertEqual(status, 200)
                    return body
                sleep(0.05)
            self.fail(f"Dashboard did not show {key}={expected}")

        sample = {"deviceId": DEVICE, "ts": None, "humidity": 65, "lamp": False, "fwVersion": "1.0.0",
                  "distance": 12.5, "motion": True, "light": 850, "door": False, "doorAuto": True}
        self.publish(peer, LOCAL + "telemetry", sample)
        readings = wait_state("lamp", False)
        self.assertEqual(readings["humidity"], 65)
        for key in ("fwVersion", "distance", "motion", "light", "door", "doorAuto"):
            self.assertEqual(readings[key], sample[key])
        self.assertIsNone(readings["temperature"])
        self.assertIsNotNone(readings["receivedAt"])
        self.assertEqual(request("/led", 1), (400, {"error": "invalid_value"}))

        with ThreadPoolExecutor() as executor:
            result = executor.submit(request, "/led", True)
            topic, command = self.receive(peer)
            self.assertEqual(topic, LOCAL + "cmd")
            self.assertGreater(command.pop("expiresAt"), time_ns() // 1_000_000)
            self.assertEqual(command, {"id": command["id"], "method": "setLamp", "value": True, "source": "gateway"})
            ack = {"id": command["id"], "ok": True, "actualState": True, "ts": None}
            self.publish(peer, LOCAL + "ack", {**ack, "id": "different-command"})
            self.publish(peer, LOCAL + "ack", ack)
            self.assertEqual(result.result(timeout=6), (200, ack))
            self.assertIs(request("/sensors")[1]["lamp"], False)

            self.publish(peer, LOCAL + "telemetry", {**sample, "lamp": True})
            wait_state("lamp", True)
            for path, method, status_key, report in (
                ("/door", "setDoor", "door", {"door": True, "doorAuto": False}),
                ("/door-auto", "setDoorAuto", "doorAuto", {"door": True, "doorAuto": True}),
            ):
                result = executor.submit(request, path, True)
                topic, command = self.receive(peer)
                self.assertEqual((topic, command["method"], command["value"]), (LOCAL + "cmd", method, True))
                ack = {"id": command["id"], "ok": True, "actualState": True, "ts": None}
                self.publish(peer, LOCAL + "ack", ack)
                self.assertEqual(result.result(timeout=6), (200, ack))
                self.publish(peer, LOCAL + "telemetry", {**sample, **report, "lamp": True})
                self.assertEqual(wait_state(status_key, True)["doorAuto"], report["doorAuto"])
            result = executor.submit(request, "/led", False)
            _, command = self.receive(peer)
            status, timeout = result.result(timeout=6)
            self.assertEqual(status, 504)
            self.assertEqual((timeout["id"], timeout["error"]), (command["id"], "device_timeout"))


if __name__ == "__main__":
    unittest.main()
