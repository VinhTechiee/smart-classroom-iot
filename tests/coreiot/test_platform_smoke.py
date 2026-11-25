import time
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from coreiot.simulator.classroom import Simulator
from coreiot.simulator.gateway import RpcBridge
from platform_smoke import SandboxAPI, verify_sandbox, wait_for_state


class PlatformSmokeTests(unittest.TestCase):
    def test_telemetry_must_be_current_at_the_time_of_the_ack(self):
        api = Mock(spec=SandboxAPI)
        api.latest.side_effect = [
            {"fan": {"ts": 101, "value": "true"}},
            {"fan": {"ts": 103, "value": "true"}},
        ]
        with patch("platform_smoke.time.sleep"):
            self.assertEqual(wait_for_state(api, "fan", True, previous_ts=100, ack_ts=102), 103)
        self.assertEqual(api.latest.call_count, 2)

    def test_preflight_rejects_invalid_actuator_telemetry_before_sending_any_rpc(self):
        name = "classroom-01-sim"
        now = time.time_ns() // 1_000_000
        sample = Simulator(RpcBridge(name, 3.5)).sample(now).body
        latest = {key: {"ts": now, "value": value} for key, value in sample["values"].items()}
        latest["fan"]["value"] = "unknown"
        api = Mock(spec=SandboxAPI)
        api.entity_id = UUID(int=1)
        api.request.return_value = {"name": name}
        api.latest.return_value = latest

        with self.assertRaisesRegex(ValueError, "boolean telemetry value"):
            verify_sandbox(api, name, "1.0.0")
        api.rpc.assert_not_called()
