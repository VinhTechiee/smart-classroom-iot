"""Read local classroom telemetry and optionally send one lamp command."""

import argparse
import json
import math
import os
import sys
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt


def is_number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--device-id", default="classroom-01", help="Classroom to monitor")
    parser.add_argument("--set-lamp", choices=("on", "off"), help="Send a command and wait for its ACK")
    args = parser.parse_args()
    if not args.device_id.strip() or any(char in args.device_id for char in "/+#\0"):
        parser.error("--device-id must be a single MQTT topic level")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    base_topic = f"classroom/{args.device_id}"
    telemetry_topic = f"{base_topic}/telemetry"
    ack_topic = f"{base_topic}/ack"
    command_id = uuid4().hex if args.set_lamp else None
    requested_state = args.set_lamp == "on"
    command_sent = False
    command_succeeded = False
    finished = Event()

    def fail(message):
        print(message, file=sys.stderr, flush=True)
        finished.set()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            fail(f"Broker rejected connection: {reason_code}")
            client.disconnect()
            return
        client.subscribe([(telemetry_topic, 1), (ack_topic, 1)])

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        nonlocal command_sent
        if any(reason_code.is_failure for reason_code in reason_codes):
            fail("Broker rejected a gateway subscription")
            client.disconnect()
            return
        print(f"Listening for telemetry and ACKs from {args.device_id}", flush=True)
        if command_id is None or command_sent:
            return

        command_sent = True
        payload = {"id": command_id, "method": "setLamp", "value": requested_state, "source": "gateway"}
        publication = client.publish(f"{base_topic}/cmd", json.dumps(payload), qos=1)
        if publication.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Sent setLamp {args.set_lamp} (id={command_id})", flush=True)
        else:
            fail(f"Could not send command {command_id}: {mqtt.error_string(publication.rc)}")

    def on_message(client, userdata, message):
        nonlocal command_succeeded
        try:
            payload = json.loads(message.payload)
        except ValueError:
            print(f"Ignoring invalid JSON on {message.topic}", file=sys.stderr, flush=True)
            return
        if not isinstance(payload, dict):
            return

        if message.topic == telemetry_topic:
            if payload.get("deviceId") != args.device_id:
                return
            readings = [args.device_id]
            for key, unit in (("temperature", "C"), ("humidity", "% RH")):
                value = payload.get(key)
                if is_number(value) and (key != "humidity" or 0 <= value <= 100):
                    readings.append(f"{key}={value} {unit}")
            if isinstance(payload.get("lamp"), bool):
                readings.append(f"lamp={payload['lamp']}")
            if isinstance(payload.get("fwVersion"), str):
                readings.append(f"fwVersion={payload['fwVersion']}")
            if len(readings) > 1:
                print(" | ".join(readings), flush=True)
        elif message.topic == ack_topic:
            print(f"{args.device_id} | ACK {json.dumps(payload)}", flush=True)
            if command_id is not None and payload.get("id") == command_id and not finished.is_set():
                command_succeeded = (
                    payload.get("ok") is True and payload.get("actualState") is requested_state
                )
                finished.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=command_id is None)
    if username := os.environ.get("GATEWAY_MQTT_USERNAME"):
        client.username_pw_set(username, os.environ.get("GATEWAY_MQTT_PASSWORD"))
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        client.connect(args.host, args.port)
        if command_id is None:
            client.loop_forever()
            return 1 if finished.is_set() else 0

        client.loop_start()
        if not finished.wait(timeout=5):
            fail(f"Timed out waiting for ACK {command_id}")
        return 0 if command_succeeded else 1
    except OSError as error:
        fail(f"Could not reach MQTT broker at {args.host}:{args.port}: {error}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        client.disconnect()
        if command_id is not None:
            client.loop_stop()


if __name__ == "__main__":
    sys.exit(main())
