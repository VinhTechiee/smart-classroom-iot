import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch
from uuid import UUID

from coreiot.simulator.classroom import Simulator
from shared.coreiot import RpcBridge
from platform_smoke import SandboxAPI, verify_sandbox, wait_for_state


class PlatformSmokeTests(unittest.TestCase):
    def test_minimal_smoke_verifies_only_led_commands_and_restores_initial_state(self):
        name = "classroom-01-sim"
        now = time.time_ns() // 1_000_000
        api = Mock(spec=SandboxAPI)
        api.entity_id = UUID(int=1)
        api.request.return_value = {"name": name}
        sample = Simulator(RpcBridge(name, 3.5), minimal=True).sample(now).body
        api.latest.side_effect = [
            {key: {"ts": now, "value": value} for key, value in sample["values"].items()},
            {"lamp": {"ts": now + 1, "value": "true"}},
            {"lamp": {"ts": now + 2, "value": "false"}},
        ]
        api.rpc.side_effect = [
            {"id": "on", "ok": True, "actualState": True, "ts": now + 1},
            {"id": "off", "ok": True, "actualState": False, "ts": now + 2},
            {"ok": False, "actualState": None, "error": "unsupported_method"},
            {"ok": False, "actualState": None, "error": "invalid_value"},
        ]

        with redirect_stdout(StringIO()):
            verify_sandbox(api, name, "1.0.0", minimal=True)
        self.assertEqual([call.args for call in api.rpc.call_args_list], [
            ("setLamp", True), ("setLamp", False), ("unsupportedMethod", True), ("setLamp", 1),
        ])

    def test_minimal_smoke_requires_temperature_only_when_requested(self):
        name = "classroom-01-sim"
        now = time.time_ns() // 1_000_000
        api = Mock(spec=SandboxAPI)
        api.entity_id = UUID(int=1)
        api.request.return_value = {"name": name}
        sample = Simulator(RpcBridge(name, 3.5), minimal=True).sample(now).body
        api.latest.return_value = {key: {"ts": now, "value": value} for key, value in sample["values"].items()}

        with self.assertRaisesRegex(ValueError, "Missing telemetry keys .*temperature"):
            verify_sandbox(api, name, "1.0.0", minimal=True, expect_temperature=True)
        api.rpc.assert_not_called()

    def test_telemetry_must_be_current_at_the_time_of_the_ack(self):
        now = time.time_ns() // 1_000_000
        api = Mock(spec=SandboxAPI)
        api.latest.side_effect = [
            {"door": {"ts": now - 1, "value": "true"}},
            {"door": {"ts": now + 60_000, "value": "true"}},
            {"door": {"ts": now + 1, "value": "true"}},
        ]
        with patch("platform_smoke.time.sleep"):
            self.assertEqual(wait_for_state(api, "door", True, previous_ts=now - 2, ack_ts=now), now + 1)
        self.assertEqual(api.latest.call_count, 3)

    def test_stale_ack_cannot_verify_a_new_command(self):
        name = "classroom-01-sim"
        now = time.time_ns() // 1_000_000
        sample_time = now - 10_000
        sample = Simulator(RpcBridge(name, 3.5), minimal=True).sample(sample_time).body
        api = Mock(spec=SandboxAPI)
        api.entity_id = UUID(int=1)
        api.request.return_value = {"name": name}
        api.latest.return_value = {
            key: {"ts": sample_time, "value": value} for key, value in sample["values"].items()
        }
        api.rpc.return_value = {"id": "old", "ok": True, "actualState": True, "ts": sample_time + 1}

        with self.assertRaisesRegex(ValueError, "rejected, mismatched or duplicate ACK"):
            verify_sandbox(api, name, "1.0.0", minimal=True)
        api.rpc.assert_called_once_with("setLamp", True)
        api.latest.assert_called_once()

    def test_preflight_rejects_invalid_actuator_telemetry_before_sending_any_rpc(self):
        name = "classroom-01-sim"
        now = time.time_ns() // 1_000_000
        sample = Simulator(RpcBridge(name, 3.5)).sample(now).body
        latest = {key: {"ts": now, "value": value} for key, value in sample["values"].items()}
        latest["door"]["value"] = "unknown"
        api = Mock(spec=SandboxAPI)
        api.entity_id = UUID(int=1)
        api.request.return_value = {"name": name}
        api.latest.return_value = latest

        with self.assertRaisesRegex(ValueError, "boolean telemetry value"):
            verify_sandbox(api, name, "1.0.0")
        api.rpc.assert_not_called()
