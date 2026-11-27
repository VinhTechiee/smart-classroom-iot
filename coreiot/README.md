# Smart Classroom on CoreIOT

CoreIOT displays classroom telemetry, sends two-way actuator commands, evaluates automation and alarms, and manages firmware releases. The PC gateway represents the classroom in CoreIOT. The hardware and local MQTT interface are defined in [the team protocol](../shared/PROTOCOL.md).

Start with the [platform deployment guide](docs/PLATFORM_DEPLOYMENT.md) for the current Yolo UNO, humidity sensor and PC gateway. It includes the dashboard imports, detached automation, notification and OTA workflows, and acceptance tests. The [minimal asset index](minimal/README.md) lists the files used in those steps.

## Install and run the Python simulator

Use Python 3.10 or later. The simulator needs one third-party package, `paho-mqtt==2.1.0`. From the repository root in PowerShell, create the environment and install it.

```powershell
python -m venv .venv/coreiot
& .venv/coreiot/Scripts/python.exe -m pip install -r coreiot/simulator/requirements.txt
```

If this workspace uses `uv`, use these commands to create the environment when needed and install the same pinned dependency.

```powershell
if (-not (Test-Path .venv/coreiot/Scripts/python.exe)) { uv venv --python 3.12 .venv/coreiot }
uv pip install --python .venv/coreiot/Scripts/python.exe --cache-dir .venv/uv-cache -r coreiot/simulator/requirements.txt
```

Create the ignored local config once. Fill it with the sandbox MQTT endpoint and device access token following the [connection steps](docs/PLATFORM_DEPLOYMENT.md#2-configure-the-endpoint-and-local-credentials). Then start the minimal simulator with synthetic humidity and the simulated LED off.

```powershell
if (-not (Test-Path coreiot/.env)) { Copy-Item coreiot/.env.example coreiot/.env }
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --minimal --env-file coreiot/.env --fw-version 1.0.0
```

The simulator logs connection and subscription events, synthetic telemetry, commands, and acknowledgements as JSON. It publishes its first sample after subscribing to RPC. See the [simulator instructions](simulator/README.md) for how to reproduce timeouts, late ACKs, and reconnects.

## Extended hardware configuration

The following setup is for a kit that supplies the original sensors and actuators. Start the simulator without `--minimal` to rehearse that configuration.

1. Create a dedicated sandbox device, for example `classroom-01-sim`, with its own access token and the `Smart Classroom` profile. Set `COREIOT_DEVICE_ID` to that exact name. Use the [device and dashboard setup](platform/README.md) to configure telemetry, reported actuator states, and remote controls. Bind the sandbox dashboard alias and both device names in the RuleChain routing filter to the same entity.
2. Start the simulator with that token and confirm fresh telemetry in the device view. Check the dashboard controls with the simulator or run the authenticated [platform smoke test](docs/VERIFICATION.md#run-against-the-course-tenant).
3. Configure the [RuleChain and notifications](rules/README.md) on the sandbox entity. Keep physical automation disabled until A and B approve thresholds and manual override. Check alarm recovery and receipt in the test recipient’s inbox.
4. Review the [OTA handoff](platform/OTA.md) with A and B. The lab rollout starts with `1.0.0` and targets `1.1.0`.

### Extended integration and evidence

[Gateway mapping and acceptance checks](INTEGRATION.md) describe the CoreIOT topics and request correlation. Use the [verification matrix](docs/VERIFICATION.md) to record tenant and hardware evidence and the [physical integration and live demo procedure](docs/DEMO.md) to rehearse the presentation.

| Requirement | Repository deliverable | Tenant or device evidence |
| --- | --- | --- |
| T11 | Device profile and dashboard templates, two-way controls, and telemetry history | Dashboard record and all three RPCs with matching ACK and fresh state |
| T12 | Humidity-based LED RuleChain with a sandbox override gate | RuleChain trace and RPC results, then approved manual override exercised with A and B |
| T13 | Temperature and sandbox door/proximity rules with notification setup | Alarm lifecycle and a notification received by the configured recipient |
| T14 | OTA package handoff and recovery procedure | Package checksum, physical rebooted version, and regression checks |

Run the Python tests and the JavaScript RuleChain and asset tests from the repository root. The JavaScript tests use built-in modules in Node.js 22 or later.

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
node --test tests/coreiot/*.test.cjs tests/coreiot/*.test.js
```
