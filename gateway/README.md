# PC gateway

The gateway forwards telemetry from a classroom on the local MQTT broker to its CoreIOT device. CoreIOT RPCs go to the same classroom, and the matching application ACK completes each request. The default profile covers relative humidity and the board LED. Measured temperature is optional. The [interface contract](../shared/PROTOCOL.md) defines local topics and [CoreIOT integration](../coreiot/INTEGRATION.md) defines cloud topics.

## Run locally

From the repository root in PowerShell, install the dependency and start Mosquitto on `127.0.0.1:1883`. If Mosquitto is already running as a service, use that instance.

```powershell
python -m pip install -r gateway/requirements.txt
& "$env:ProgramFiles\mosquitto\mosquitto.exe" -v
```

In separate PowerShell windows, start the synthetic device, monitor reported readings and send one LED command.

```powershell
python gateway/simulator.py --minimal --humidity 65
python gateway/main.py
python gateway/main.py --set-lamp on
```

The monitor prints `humidity=65.0 % RH` and `lamp=False` at startup. After the command arrives it prints an ACK with `ok:true` and a new `lamp=True` reading. Send `--set-lamp off` to restore the original state. Use `--host`, `--port` and `--device-id` in the two scripts to select another local route. For a local broker that requires credentials, set `GATEWAY_MQTT_USERNAME` and `GATEWAY_MQTT_PASSWORD` in their launch environments.

## Local dashboard (T10)

Keep the broker and simulator running, then start the dashboard from the repository root and open the printed address, normally `http://127.0.0.1:8080`.

```powershell
python -m gateway.web
```

Use `--env-file gateway/.env` to share the bridge's broker and classroom settings, and match the simulator's `--device-id` to the selected classroom. The dashboard uses local MQTT settings and works independently of the CoreIOT connection.

The structure follows Lab 4. `GET /` serves the HTML and `GET /sensors` returns the latest JSON. The browser calls `/sensors` every 3 seconds using `fetch()`. The LED buttons send `POST /led` with a requested boolean, which becomes a `setLamp` command on the same local MQTT topics as the gateway bridge. The handler matches the ACK by command ID. It returns a timeout after 3.5 seconds if the ACK is missing. The displayed LED state comes from reported telemetry. Restart the simulator with `--drop-ack` to reproduce a timeout.

See *ESP32 WebServer*, slides 12, 33, 36 and 39, and the Lab 4 `mainserver.cpp` handlers for the HTTP pattern. In Lab 4 the web server runs on the board, which maps to T07 in the project announcement. This dashboard runs on the PC gateway, which maps to T10. *IoT Gateway and Rule Chain*, slides 4 and 8–10, covers the local broker and Python MQTT client. Its `v1/gateway/*` API in slides 13–18 belongs to the separate CoreIOT Gateway integration described under [T15](../coreiot/minimal/GATEWAY.md).

## Connect to the CoreIOT sandbox

Copy `gateway/.env.example` to `gateway/.env` if the latter does not exist. In your local editor, set the MQTT endpoint and device access token provided by Member C. Use the approved sandbox endpoint and its TLS settings. Use a single client with the sandbox token and keep automation disabled for the initial LED test. See the [sandbox setup](../coreiot/docs/PLATFORM_DEPLOYMENT.md#2-configure-the-endpoint-and-local-credentials).

```powershell
if (-not (Test-Path gateway/.env)) { Copy-Item gateway/.env.example gateway/.env }
```

Run each command in a separate PowerShell window.

```powershell
python gateway/simulator.py --minimal --device-id classroom-01-sim --humidity 65
python -m gateway.bridge --env-file gateway/.env
```

In CoreIOT, confirm that the dashboard for `classroom-01-sim` shows 65% RH. Press **LED ON** and **LED OFF**. Compare the cloud request ID, the gateway's local command ID, the ACK Boolean, and fresh `lamp` telemetry. To exercise the local ACK timeout, restart the simulator with `--drop-ack`. The gateway reports `device_timeout` after about 3.5 seconds, and the device can still report an updated `lamp` if the command was applied.

For changing readings, stop the fixed simulator and start it in random mode. Each publication includes random humidity from 0 to 100% RH and temperature from 20 to 40 °C, including in minimal mode. The default interval is 5 seconds.

```powershell
python gateway/simulator.py --minimal --device-id classroom-01-sim --random
```

Add `--ai-model ai/humidity_model.json` to the bridge command to publish the humidity classification as `aiEvent` and `aiModel`. See [T09 training and demo](../ai/README.md) for the model, metrics and expected classes.

Run one gateway process per configured classroom and token. For the physical classroom, configure `classroom-01` and its own token. The firmware must publish and subscribe to `classroom/classroom-01/{telemetry,cmd,ack}` and identify itself as `classroom-01`. Use Unix milliseconds for a synchronized device or `ts:null` for an unsynchronized device. For the original full kit profile, omit `--minimal` on the simulator and use `--extended` on the bridge.

## Verification

```powershell
python -m unittest discover -s tests/coreiot -p 'test_*.py'
python -m unittest discover -s tests/gateway -p 'test_*.py'
```

Local MQTT test records use synthetic readings. Follow the [verification record](../coreiot/docs/VERIFICATION.md) for signed-in sandbox and hardware evidence.
