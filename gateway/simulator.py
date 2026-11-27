"""Simulate a YoloUNO by publishing synthetic readings and handling MQTT commands."""

import argparse
import json
import math
import os
import sys
from threading import TIMEOUT_MAX, Event, Lock

import paho.mqtt.client as mqtt


ACTUATORS = {"setLamp": "lamp", "setDoor": "door", "setDoorAuto": "doorAuto"}
ACK_CACHE_SIZE = 128


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--device-id", default="classroom-01-sim", help="Simulated classroom identifier")
    parser.add_argument("--interval", type=float, default=5, help="Seconds between telemetry messages")
    parser.add_argument("--minimal", action="store_true", help="Only simulate humidity and the board LED")
    parser.add_argument("--humidity", type=float, default=65.0, help="Synthetic relative humidity in percent")
    parser.add_argument("--temperature", type=float, help="Include a synthetic temperature in Celsius")
    parser.add_argument("--drop-ack", action="store_true", help="Apply commands but omit the application ACK")
    args = parser.parse_args()
    if not args.device_id.strip() or any(char in args.device_id for char in "/+#\0"):
        parser.error("--device-id must be a single MQTT topic level")
    if args.device_id in ("classroom-01", "classroom-ota-board", "classroom-ota-virtual"):
        parser.error("Use a synthetic classroom identifier")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not 0 < args.interval <= TIMEOUT_MAX:
        parser.error(f"--interval must be greater than zero and at most {TIMEOUT_MAX:g} seconds")
    if not 0 <= args.humidity <= 100:
        parser.error("--humidity must be between 0 and 100 percent RH")
    if args.temperature is not None and not math.isfinite(args.temperature):
        parser.error("--temperature must be a finite number in Celsius")

    base_topic = f"classroom/{args.device_id}"
    sample = {
        "deviceId": args.device_id,
        "ts": None,
        "humidity": args.humidity,
        "lamp": False,
        "fwVersion": "1.0.0",
    }
    if not args.minimal:
        sample.update(temperature=28.5, light=320, motion=True, distance=42.0, door=False, doorAuto=False)
    if args.temperature is not None:
        sample["temperature"] = args.temperature
    sample_lock = Lock()
    failed = Event()
    recent_acks = {}

    def publish_telemetry(client):
        client.publish(f"{base_topic}/telemetry", json.dumps(sample), qos=1)

    def fail(message):
        print(message, file=sys.stderr, flush=True)
        failed.set()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            fail(f"Broker rejected connection: {reason_code}")
            return
        client.subscribe(f"{base_topic}/cmd", qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(reason_code.is_failure for reason_code in reason_codes):
            fail("Broker rejected the simulator's command subscription")
            return
        print(f"Simulating {args.device_id}; sending synthetic telemetry every {args.interval:g}s", flush=True)
        with sample_lock:
            publish_telemetry(client)

    def on_command(client, userdata, message):
        if message.retain:
            return
        try:
            command = json.loads(message.payload)
        except ValueError:
            print(f"Ignoring invalid JSON on {message.topic}", file=sys.stderr, flush=True)
            return
        command_id = command.get("id") if isinstance(command, dict) else None
        if not isinstance(command_id, str) or not command_id.strip():
            print("Ignoring command without a valid id", file=sys.stderr, flush=True)
            return

        if command_id in recent_acks:
            if not args.drop_ack:
                client.publish(f"{base_topic}/ack", recent_acks[command_id], qos=1)
            return

        method = command.get("method")
        actuator = ACTUATORS.get(method) if isinstance(method, str) else None
        value = command.get("value")
        ack = {"id": command_id, "ok": False, "actualState": None, "ts": None}
        with sample_lock:
            if actuator not in sample:
                ack["error"] = "unsupported_method"
            elif not isinstance(value, bool):
                ack["error"] = "invalid_value"
            else:
                sample[actuator] = value
                if actuator == "door":
                    sample["doorAuto"] = False
                ack.update(ok=True, actualState=value)

            encoded_ack = json.dumps(ack)
            recent_acks[command_id] = encoded_ack
            if len(recent_acks) > ACK_CACHE_SIZE:
                del recent_acks[next(iter(recent_acks))]
            if args.drop_ack:
                print(f"Suppressed ACK {encoded_ack}", flush=True)
            else:
                client.publish(f"{base_topic}/ack", encoded_ack, qos=1)
                print(f"ACK {encoded_ack}", flush=True)
            if ack["ok"]:
                publish_telemetry(client)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username := os.environ.get("GATEWAY_MQTT_USERNAME"):
        client.username_pw_set(username, os.environ.get("GATEWAY_MQTT_PASSWORD"))
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_command
    try:
        client.connect(args.host, args.port)
        client.loop_start()
        while not failed.wait(timeout=args.interval):
            if client.is_connected():
                with sample_lock:
                    publish_telemetry(client)
        return 1
    except OSError as error:
        fail(f"Could not reach MQTT broker at {args.host}:{args.port}: {error}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    sys.exit(main())
