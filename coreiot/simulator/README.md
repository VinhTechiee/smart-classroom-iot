# Python CoreIOT simulator

The simulator opens one CoreIOT MQTT device session for a sandbox classroom. Its gateway maps cloud RPCs to the shared local command topic and models execution and ACKs in memory. Its cloud-facing topics are the same ones Member B can use from the PC gateway. All measurements, actuator actions, and version reports from the simulator are synthetic.

## Install and connect

Set up the [Python environment and pinned Paho MQTT client](../README.md#install-and-run-the-python-simulator) from the repository root. [Paho MQTT 2.1.0](https://pypi.org/project/paho-mqtt/2.1.0/)

Create `coreiot/.env` from the example if you do not already have one. Enter the tenant's sandbox MQTT endpoint, device token, and device name. The MQTT username is the device token. Use `mqtts://` and the tenant's TLS port for an encrypted connection. The simulator checks certificates and hostnames against the system trust store or the PEM CA bundle configured by `COREIOT_MQTT_CA_FILE`. Use plain `mqtt://` for an isolated endpoint such as a local test broker. Environment variables in the current shell take precedence over entries in the local file. Keep the device name and dashboard alias aligned with `COREIOT_DEVICE_ID`. [Example configuration](../.env.example)

```powershell
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env
```

Expected startup events are `mqtt_connecting`, `mqtt_connected`, `rpc_subscription_ready`, `telemetry_queued`, and `mqtt_puback`. The first sample is queued after the RPC subscription is accepted. Subsequent samples are sent every five seconds, with fresh telemetry after every applied command. Ctrl+C pauses RPC intake and allows up to 350 ms for queued QoS 1 publish acknowledgements before disconnecting. A broker delay beyond that window produces a `mqtt_shutdown_pending` log. Use one simulator or gateway at a time with a given token. [Paho MQTT client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)

## Send readings and simulate faults

Run one example at a time. Stopping and restarting resets the simulated actuator state to the selected initial values. Firmware versions `1.0.0` and `1.1.0` exercise the version display before the physical OTA test.

```powershell
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env --temperature 35 --light 100 --motion true --fw-version 1.0.0
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env --temperature 27 --light 400 --motion false --lamp true --fan true --fw-version 1.1.0
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env --unsynchronized --interval-ms 1000
```

| Scenario | Settings or request | Expected result |
| --- | --- | --- |
| Lamp, fan, door | Send `setLamp`, `setFan`, and `setDoor` with JSON `true` or `false` | `simulated_command`, `rpc_response_queued` with `ok:true` and matching `actualState`, and `telemetry_queued` with the changed state |
| Unsupported method or invalid value | Send `setWindow` or use `1` for `params` | `ok:false` with `unsupported_method` or `invalid_value` and the simulator leaves the existing state in place |
| Unknown target | `--missing-device` | `ok:false`, `error:"unknown_device"` |
| Device unreachable | `--offline-device --timeout-ms 1000` | `ok:false`, `error:"device_timeout"` and no fresh telemetry |
| ACK lost after execution | `--drop-ack --timeout-ms 1000` | Reported state changes and RPC times out |
| ACK reaches gateway late | `--timeout-ms 1000 --ack-delay-ms 2000` | Timeout response, then `late_or_unmatched_ack` and fresh telemetry when the delayed simulated action runs |
| Device clock unsynchronized | `--unsynchronized` | ACK `ts:null` and a cloud telemetry envelope timestamped at gateway receipt |
| Broker interruption | Disconnect and restore access to the test broker | `mqtt_disconnected`, reconnect attempts, a new subscription and a fresh snapshot of the state |

The `mqtt_puback` log event means the broker accepted an MQTT publish. Read `rpc_response_queued.response.ok` and `actualState` for the simulated command outcome. The dashboard uses reported telemetry for its state. Simultaneous actions produce individual, ordered telemetry samples. The simulator uses adjacent milliseconds when actions share one clock tick.

The gateway keeps up to 64 pending requests and 256 recent results for its active session. Pending duplicates reuse the same command and completed duplicates replay the prior response while cached. The MQTT `DUP` flag alone is insufficient to identify an application duplicate. After cache eviction, a repeating request ID can be treated as new. Use two-way, non-persistent CoreIOT requests and avoid reusing request IDs within a session. An RPC received before SUBACK queues device work until the broker grants the subscription. Disconnect clears request tracking and cancels scheduled simulated commands. Already applied simulated state is reported after reconnect. The new connection starts with an empty publish queue.

## Test

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
```

The unit suite verifies validation, concurrent independent ACKs, request timeouts, late ACKs, and state updates. The MQTT loopback test runs Paho against a local protocol fixture and verifies the MQTT username, QoS 1, resubscription, and graceful disconnect. Use the tenant acceptance checks to verify the actual CoreIOT instance. [Tenant acceptance checks](../INTEGRATION.md#acceptance-checks)
