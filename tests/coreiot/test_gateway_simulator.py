import json
import unittest

from shared.cloud_config import parse_connection
from coreiot.simulator.classroom import DEFAULT_READINGS, Simulator
from shared.coreiot import (
    RPC_REQUEST_PREFIX,
    RPC_RESPONSE_PREFIX,
    TELEMETRY_TOPIC,
    RpcBridge,
    cloud_telemetry,
)

DEVICE = "classroom-01"
SOURCE_TS = 1780000000000


def request(method: str, value: object) -> bytes:
    return json.dumps({"method": method, "params": value}).encode()


def ack(command_id: str, state: bool) -> dict:
    return {"id": command_id, "ok": True, "actualState": state, "ts": None}


class RpcBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = RpcBridge(DEVICE, 1)

    def command(self, request_id: str, method: str = "setLamp", value: bool = True, **flags):
        return self.bridge.accept_rpc(RPC_REQUEST_PREFIX + request_id, request(method, value), 0, **flags)

    def test_concurrent_acks_are_paired_by_classroom_and_unique_command_id(self):
        lamp = self.command("10", "setLamp", True)
        door = self.command("11", "setDoor", False)
        self.assertEqual(lamp.topic, f"classroom/{DEVICE}/cmd")
        self.assertEqual(lamp.body, {"id": lamp.body["id"], "method": "setLamp", "value": True, "source": "coreiot"})
        self.assertNotEqual(lamp.body["id"], door.body["id"])
        self.assertIsNone(self.bridge.accept_ack("classroom/other/ack", ack(lamp.body["id"], True), 0.1))
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, ack("unrelated-command", True), 0.1))
        self.assertEqual(self.bridge.pending_count, 2)
        second = self.bridge.accept_ack(self.bridge.ack_topic, ack(door.body["id"], False), 0.2)
        first = self.bridge.accept_ack(self.bridge.ack_topic, ack(lamp.body["id"], True), 0.3)
        self.assertEqual((second.topic, second.body["actualState"]), (RPC_RESPONSE_PREFIX + "11", False))
        self.assertEqual((first.topic, first.body["actualState"]), (RPC_RESPONSE_PREFIX + "10", True))
        self.assertEqual(self.bridge.pending_count, 0)

    def test_invalid_rpc_and_unknown_device_fail_without_local_command(self):
        cases = (
            (b"{", True, "invalid_json"),
            (b'{"method":"setFan","params":NaN}', True, "invalid_json"),
            (request("setWindow", True), True, "unsupported_method"),
            (request("constructor", True), True, "unsupported_method"),
            (request("setDoor", 1), True, "invalid_value"),
            (request("setLamp", "true"), True, "invalid_value"),
            (request("setDoor", {"value": True}), True, "invalid_value"),
            (request("setLamp", True), False, "unknown_device"),
        )
        for index, (body, present, error) in enumerate(cases):
            with self.subTest(error=error, payload=body):
                result = self.bridge.accept_rpc(RPC_REQUEST_PREFIX + str(index), body, 0, device_available=present)
                self.assertEqual(result.topic, RPC_RESPONSE_PREFIX + str(index))
                self.assertFalse(result.body["ok"])
                self.assertIsNone(result.body["actualState"])
                self.assertEqual(result.body["error"], error)
        self.assertEqual(self.bridge.pending_count, 0)

    def test_pending_duplicates_are_suppressed_and_completed_response_replayed(self):
        command = self.command("7")
        self.assertIsNone(self.command("7"))
        self.assertIsNone(self.command("7", value=False))
        response = self.bridge.accept_ack(self.bridge.ack_topic, ack(command.body["id"], True), 0.1)
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, response.body, 0.2))
        self.assertEqual(self.command("7"), response)
        self.assertEqual(self.command("7", value=False), response)

    def test_pending_and_recent_stores_are_bounded(self):
        self.bridge = RpcBridge(DEVICE, 1, max_pending=1, max_completed=1)
        command = self.command("1")
        rejected = self.command("2")
        self.assertEqual(rejected.body["error"], "gateway_busy")
        self.assertEqual(self.bridge.pending_count, 1)
        self.bridge.accept_ack(self.bridge.ack_topic, ack(command.body["id"], True), 0.1)
        next_command = self.command("2")
        self.assertEqual(next_command.topic, self.bridge.command_topic)
        self.assertNotEqual(next_command.body["id"], rejected.body["id"])

    def test_expired_ack_does_not_resolve_timeout_or_next_session(self):
        command = self.command("8")
        old_ack = ack(command.body["id"], True)
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, old_ack, 1.0))
        self.assertEqual(self.bridge.expire(1.0)[0].body["error"], "device_timeout")
        self.assertEqual(self.bridge.expire(2.0), [])
        self.bridge.clear_session()
        new_command = self.command("8", value=False)
        self.assertNotEqual(new_command.body["id"], command.body["id"])
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, old_ack, 0.1))
        self.assertEqual(self.bridge.pending_count, 1)

    def test_ack_validation_and_known_failure_preserve_actual_state(self):
        command = self.command("1")
        body = ack(command.body["id"], False)
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, {**body, "ok": 1}, 0.1))
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, {**body, "actualState": None}, 0.1))
        self.assertIsNone(self.bridge.accept_ack(self.bridge.ack_topic, {**body, "ok": False}, 0.1))
        failed = {**body, "ok": False, "error": "device_rejected"}
        self.assertEqual(self.bridge.accept_ack(self.bridge.ack_topic, failed, 0.2).body, failed)

    def test_retained_and_unrecognized_topics_do_not_dispatch(self):
        self.assertIsNone(self.command("1", retained=True))
        self.assertIsNone(self.command("nested/id"))
        self.assertIsNone(self.bridge.accept_rpc(TELEMETRY_TOPIC, request("setFan", True), 0))
        self.assertEqual(self.bridge.pending_count, 0)


class SimulatorTests(unittest.TestCase):
    def test_minimal_rpc_reports_both_led_states_without_extended_actuators(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), minimal=True, ack_delay=0)
        simulator.connected(0)
        initial = simulator.step(0, SOURCE_TS)[0]
        self.assertIs(initial.body["values"]["lamp"], False)
        for method in ("setFan", "setDoor"):
            rejected, = simulator.receive_rpc(RPC_REQUEST_PREFIX + method, request(method, True), 0.1)
            self.assertEqual(rejected.body["error"], "unsupported_method")

        for index, state in enumerate((True, False), 1):
            request_id = str(index)
            outputs = simulator.receive_rpc(RPC_REQUEST_PREFIX + request_id, request("setLamp", state), index)
            self.assertEqual(outputs, [])
            response, reported = simulator.step(index, SOURCE_TS + index * 1000)
            self.assertEqual(response.topic, RPC_RESPONSE_PREFIX + request_id)
            self.assertIs(response.body["ok"], True)
            self.assertIs(response.body["actualState"], state)
            self.assertIs(reported.body["values"]["lamp"], state)
            self.assertEqual(response.body["ts"], reported.body["ts"])

    def test_minimal_can_run_before_led_support_is_confirmed(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), readings={"lamp": None}, minimal=True)
        simulator.connected(0)
        sample, = simulator.step(0, SOURCE_TS)
        self.assertNotIn("lamp", sample.body["values"])
        rejected, = simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.1)
        self.assertEqual(rejected.body["error"], "unsupported_method")

    def test_first_seen_qos_duplicate_and_conflicting_requests_publish_each_state(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), ack_delay=0.1)
        simulator.connected(0)
        simulator.step(0, SOURCE_TS)
        simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.1, duplicate=True)
        simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.11, duplicate=True)
        simulator.receive_rpc(RPC_REQUEST_PREFIX + "2", request("setLamp", False), 0.12)
        first, on, second, off = simulator.step(0.3, SOURCE_TS + 300)
        self.assertEqual((first.topic, second.topic), (RPC_RESPONSE_PREFIX + "1", RPC_RESPONSE_PREFIX + "2"))
        self.assertEqual((on.topic, off.topic), (TELEMETRY_TOPIC, TELEMETRY_TOPIC))
        self.assertTrue(on.body["values"]["lamp"])
        self.assertFalse(off.body["values"]["lamp"])
        self.assertLess(on.body["ts"], off.body["ts"])
        replay = simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.4, duplicate=True)
        self.assertEqual(replay, [first])
        self.assertEqual(simulator.step(0.5, SOURCE_TS + 500), [])
        self.assertIs(simulator.sample(SOURCE_TS + 500).body["values"]["lamp"], False)

    def test_two_actuators_report_fresh_state_after_execution(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), ack_delay=0, synchronized=False)
        simulator.connected(0)
        initial = simulator.step(0, SOURCE_TS)[0]
        self.assertEqual(initial.topic, TELEMETRY_TOPIC)
        self.assertEqual(initial.body, {"ts": SOURCE_TS, "values": {**DEFAULT_READINGS, "deviceId": DEVICE}})
        for index, (method, state) in enumerate((("setLamp", "lamp"), ("setDoor", "door"))):
            for value in (True, False):
                now = index + 1 + int(not value) / 2
                wall = SOURCE_TS + int(now * 1000)
                topic = RPC_REQUEST_PREFIX + str(wall)
                self.assertEqual(simulator.receive_rpc(topic, request(method, value), now), [])
                response, telemetry = simulator.step(now, wall)
                self.assertTrue(response.body["ok"])
                self.assertIs(response.body["actualState"], value)
                self.assertIs(telemetry.body["values"][state], value)
                self.assertIsNone(response.body["ts"])
                self.assertEqual(telemetry.body["ts"], wall)

    def test_late_ack_does_not_replace_timeout_but_telemetry_reports_execution(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), ack_delay=2)
        simulator.connected(0)
        simulator.step(0, SOURCE_TS)
        simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setDoor", True), 0.1)
        expired = simulator.step(1.1, SOURCE_TS + 1100)
        self.assertEqual(expired[0].body["error"], "device_timeout")
        late = simulator.step(2.1, SOURCE_TS + 2100)
        self.assertEqual([message.topic for message in late], [TELEMETRY_TOPIC])
        self.assertTrue(late[0].body["values"]["door"])
        self.assertEqual(simulator.bridge.pending_count, 0)

    def test_dropped_ack_still_executes_and_offline_device_does_not(self):
        for fault, telemetry in (({"drop_ack": True}, True), ({"device_online": False}, False)):
            with self.subTest(fault=fault):
                simulator = Simulator(RpcBridge(DEVICE, 1), ack_delay=0, **fault)
                simulator.connected(0)
                simulator.step(0, SOURCE_TS)
                simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.1)
                messages = simulator.step(0.2, SOURCE_TS + 200)
                self.assertEqual([message.topic for message in messages], [TELEMETRY_TOPIC] if telemetry else [])
                self.assertEqual(simulator.sample(SOURCE_TS).body["values"]["lamp"], telemetry)
                self.assertEqual(simulator.step(1.1, SOURCE_TS + 1100)[0].body["error"], "device_timeout")

    def test_disconnected_commands_are_cleaned_and_do_not_run_after_reconnect(self):
        simulator = Simulator(RpcBridge(DEVICE, 1), ack_delay=0.5)
        simulator.connected(0)
        simulator.receive_rpc(RPC_REQUEST_PREFIX + "1", request("setLamp", True), 0.1)
        self.assertEqual(simulator.disconnected(), 1)
        self.assertEqual(simulator.step(0.7, SOURCE_TS), [])
        simulator.connected(0.8)
        messages = simulator.step(0.9, SOURCE_TS)
        self.assertEqual([message.topic for message in messages], [TELEMETRY_TOPIC])
        self.assertFalse(messages[0].body["values"]["lamp"])
        self.assertEqual(simulator.bridge.pending_count, 0)


class TelemetryTests(unittest.TestCase):
    def test_minimal_telemetry_only_contains_available_measurements(self):
        required = {"deviceId": DEVICE, "ts": SOURCE_TS, "humidity": 65.0, "lamp": False, "fwVersion": "1.0.0"}
        for readings, expected in (
            ({}, required),
            ({"temperature": 27.5}, {**required, "temperature": 27.5}),
            ({"humidity": None, "temperature": None}, {key: val for key, val in required.items() if key != "humidity"}),
        ):
            with self.subTest(readings=readings):
                simulator = Simulator(RpcBridge(DEVICE, 1), readings=readings, minimal=True)
                self.assertEqual(simulator.sample(SOURCE_TS).body, {"ts": SOURCE_TS, "values": expected})

        lamp_only = {"deviceId": DEVICE, "ts": None, "lamp": True, "fwVersion": "1.1.0"}
        result = cloud_telemetry(f"classroom/{DEVICE}/telemetry", lamp_only, DEVICE, SOURCE_TS, minimal=True)
        self.assertEqual(result.body, {"ts": SOURCE_TS, "values": {k: v for k, v in lamp_only.items() if k != "ts"}})

    def test_minimal_rejects_invalid_humidity_and_optional_values(self):
        for readings in ({"humidity": -1}, {"humidity": 101}, {"humidity": True}, {"temperature": "28"},
                         {"temperature": float("inf")}, {"lamp": 1}, {"light": 0}):
            with self.subTest(readings=readings), self.assertRaises(ValueError):
                Simulator(RpcBridge(DEVICE, 1), readings=readings, minimal=True)

    def test_shared_telemetry_preserves_values_and_timestamp(self):
        sample = {**DEFAULT_READINGS, "deviceId": DEVICE, "ts": SOURCE_TS, "fwVersion": "1.1.0"}
        local_topic = f"classroom/{DEVICE}/telemetry"
        result = cloud_telemetry(local_topic, sample, DEVICE, SOURCE_TS + 100)
        self.assertEqual(result.body, {"ts": SOURCE_TS, "values": sample})
        unsynchronized = cloud_telemetry(local_topic, {**sample, "ts": None}, DEVICE, SOURCE_TS + 100)
        self.assertEqual(unsynchronized.body["ts"], SOURCE_TS + 100)
        self.assertNotIn("ts", unsynchronized.body["values"])

    def test_bad_telemetry_types_and_identity_are_rejected(self):
        sample = {**DEFAULT_READINGS, "deviceId": DEVICE, "ts": None}
        cases = (
            {"deviceId": "other"}, {"ts": True}, {"motion": 1}, {"distance": float("inf")},
            {"temperature": False}, {"light": float("nan")}, {"fwVersion": " "},
        )
        for override in cases:
            with self.subTest(override=override), self.assertRaises(ValueError):
                cloud_telemetry(f"classroom/{DEVICE}/telemetry", {**sample, **override}, DEVICE, SOURCE_TS)

    def test_connection_defaults_tls_and_keeps_credentials_out_of_url(self):
        config = {"COREIOT_MQTT_URL": "mqtts://mqtt.example", "COREIOT_DEVICE_TOKEN": "unit-test"}
        self.assertEqual(parse_connection(config), ("mqtt.example", 8883, "unit-test", True, None))
        with self.assertRaises(ValueError):
            parse_connection({**config, "COREIOT_MQTT_URL": "mqtts://user:secret@mqtt.example"})
        with self.assertRaises(ValueError):
            parse_connection({**config, "COREIOT_MQTT_URL": "mqtt://mqtt.example", "COREIOT_MQTT_CA_FILE": "ca.pem"})


if __name__ == "__main__":
    unittest.main()
