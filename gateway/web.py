"""Serve the local classroom dashboard and route its LED commands over MQTT."""

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from coreiot.simulator.__main__ import read_environment
from coreiot.simulator.gateway import Publication, cloud_telemetry, failure, json_object, valid_ack
from gateway.bridge import BrokerSettings, MqttLink, local_broker_settings


ACK_TIMEOUT = 3.5
LOGGER = logging.getLogger(__name__)


class LocalDashboard:
    """Keep the most recent reported readings and wait for one local ACK at a time."""

    def __init__(self, device_id: str, broker: BrokerSettings):
        if not device_id.strip() or any(char in device_id for char in "/+#\0"):
            raise ValueError("Device ID must be a single MQTT topic segment")
        self.device_id = device_id
        self.telemetry_topic = f"classroom/{device_id}/telemetry"
        self.ack_topic = f"classroom/{device_id}/ack"
        self.command_topic = f"classroom/{device_id}/cmd"
        self.readings = {}
        self.received_at = None
        self.pending_id = None
        self.ack = None
        self.mqtt = MqttLink("Local MQTT", broker, (self.telemetry_topic, self.ack_topic), self.on_message)

    def on_message(self, message):
        if message.retain:
            return
        try:
            body = json_object(message.payload)
            if message.topic == self.telemetry_topic:
                received_at = time_ns() // 1_000_000
                sample = cloud_telemetry(message.topic, body, self.device_id, received_at, minimal=True)
                self.readings = sample.body["values"]
                self.received_at = received_at
            elif message.topic == self.ack_topic and self.pending_id is not None:
                if self.ack is None and body.get("id") == self.pending_id and valid_ack(body):
                    self.ack = body
        except ValueError as exc:
            LOGGER.warning("Ignored %s: %s", message.topic, exc)

    def sensors(self) -> dict:
        return {
            "deviceId": self.device_id,
            "humidity": self.readings.get("humidity"),
            "temperature": self.readings.get("temperature"),
            "lamp": self.readings.get("lamp"),
            "receivedAt": self.received_at,
            "brokerConnected": self.mqtt.ready,
        }

    def set_lamp(self, value: bool) -> tuple[HTTPStatus, dict]:
        command_id = f"web-{uuid4().hex}"
        command = Publication(self.command_topic, {
            "id": command_id, "method": "setLamp", "value": value, "source": "gateway",
        })
        self.pending_id = command_id
        self.ack = None
        try:
            if not self.mqtt.publish(command):
                return HTTPStatus.SERVICE_UNAVAILABLE, failure(command_id, "local_broker_unavailable")

            deadline = monotonic() + ACK_TIMEOUT
            while self.mqtt.ready and self.ack is None and monotonic() < deadline:
                self.mqtt.pump()
            if self.ack is None:
                if not self.mqtt.ready:
                    return HTTPStatus.SERVICE_UNAVAILABLE, failure(command_id, "local_broker_unavailable")
                return HTTPStatus.GATEWAY_TIMEOUT, failure(command_id, "device_timeout")

            if not self.ack["ok"]:
                return HTTPStatus.BAD_GATEWAY, self.ack
            if self.ack["actualState"] is not value:
                return HTTPStatus.BAD_GATEWAY, {**self.ack, "ok": False, "error": "unexpected_state"}
            return HTTPStatus.OK, self.ack
        finally:
            self.pending_id = None
            self.ack = None


class DashboardHandler(BaseHTTPRequestHandler):
    timeout = 5

    def do_GET(self):
        if self.path == "/":
            self.send_body(HTTPStatus.OK, "text/html; charset=utf-8", self.server.page)
        elif self.path == "/sensors":
            self.send_json(HTTPStatus.OK, self.server.dashboard.sensors())
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/led":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "expected_json"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 128:
                raise ValueError("Invalid request size")
            body = json_object(self.rfile.read(size))
            value = body.get("value")
            if type(value) is not bool:
                raise ValueError("LED value must be a JSON boolean")
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_value"})
            return
        status, ack = self.server.dashboard.set_lamp(value)
        self.send_json(status, ack)

    def send_json(self, status, body):
        self.send_body(status, "application/json", json.dumps(body).encode("utf-8"))

    def send_body(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code="-", size="-"):
        if self.command != "GET" or self.path != "/sensors" or code != HTTPStatus.OK:
            super().log_request(code, size)


class DashboardServer(HTTPServer):
    timeout = 0.05

    def __init__(self, port: int, dashboard: LocalDashboard):
        self.dashboard = dashboard
        self.page = Path(__file__).with_name("index.html").read_bytes()
        super().__init__(("127.0.0.1", port), DashboardHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080, help="Local HTTP port")
    parser.add_argument("--env-file", type=Path, help="Load the same local MQTT settings used by the bridge")
    parser.add_argument("--device-id", help="Classroom to monitor and control")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        values = read_environment(args.env_file)
        device_id = args.device_id or values.get("COREIOT_DEVICE_ID") or "classroom-01"
        dashboard = LocalDashboard(device_id, local_broker_settings(values))
        with DashboardServer(args.port, dashboard) as server:
            print(f"Dashboard: http://127.0.0.1:{server.server_port}", flush=True)
            try:
                while True:
                    dashboard.mqtt.pump()
                    server.handle_request()
            finally:
                dashboard.mqtt.close()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
