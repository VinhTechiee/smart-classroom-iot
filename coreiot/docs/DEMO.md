# Physical integration and live demo

## Handoff checklist

Use a separate CoreIOT entity for simulation. Record the exact hardware entity, gateway build, firmware build, tenant version, and operator accounts on the day of the demo.

| Owner | Verify before using hardware | Evidence |
| --- | --- | --- |
| A · YoloUNO | Confirm the final `deviceId`, Wi-Fi settings, running `fwVersion`, `classroom/{deviceId}/telemetry` payload, all six boolean command outcomes, matching ACK IDs and fields, and post-command telemetry. Reconnect after dropping Wi-Fi. Confirm whether reported states have physical feedback. | Serial logs, local MQTT capture, actual actuator observations, reconnect trace |
| A · firmware OTA | Provide both application images and recovery instructions. Confirm OTA partitions, integrity verification, first-boot validation and rollback. Test `1.0.0` → `1.1.0` on the lab unit before deciding whether to include an update in the demo. | Package digests, known-good recovery image, post-boot version and regression record |
| B · gateway | Confirm local broker endpoint and credentials, CoreIOT token binding by device, telemetry timestamp handling, both RPC directions, device and command ID correlation, failure and timeout response, session cleanup, and reconnect. | Gateway log with both IDs, local MQTT trace, CoreIOT RPC result, latest device telemetry |
| B · AI | Provide the agreed event definition, provenance, cloud entity and payload keys. Confirm one reproducible inference action and its latency. | Gateway inference log and corresponding CoreIOT record |
| A, B, C · automation | Approve thresholds, light polarity, command intent, override propagation, and application-time priority. Rehearse setting and releasing override with an RPC in flight. Approve a physical door or proximity event definition before enabling its alarm. | Recorded policy decision and trace from the real setup |
| C · CoreIOT | Import and bind the dashboard. Check tenant RPC, telemetry and alarm behavior with the simulator first, then bind to the hardware entity. Verify the test recipient can open the Notification Center inbox. | Sandbox results, version-specific dashboard export, RuleChain traces, notification receipt |

### Where to run each check

| Check | Simulator rehearsal | Physical verification |
| --- | --- | --- |
| Telemetry, history, connectivity and `fwVersion` display | Synthetic samples, changing values, disconnect and reconnect | Sensor response, real firmware version, and recovery after Wi-Fi loss |
| RPC and reported state | All six boolean actions, malformed inputs, concurrency, timeout, late ACK and reconnect | Gateway routing through local MQTT, matching device ACK and visible actuator response |
| RuleChain | Low light with motion, fan hysteresis, stale telemetry, manual override and explicit release on a sandbox device | Real sensor polarity and thresholds, and local action priority during a conflicting automatic request |
| Notifications | The sandbox tenant receives synthetic alarm trigger and recovery samples. Check the recipient inbox. | Repeat a permitted real sensor event and check recipient delivery. |
| AI | Prepare the event widget after B supplies the agreed keys. | Reproduce a real inference and trace it from gateway to dashboard. |
| OTA | Probe assignment metadata and download checksum on a virtual device after A supplies the package. | Validate the actual install, reboot, `fwVersion`, and regression tests on YoloUNO. |

## Rehearse with the simulator

From the repository root, complete the [Python simulator installation](../README.md#install-and-run-the-python-simulator) and use Node.js 22 or later to generate the detached RuleChain import. Save generated assets and evidence under the ignored `build/` directory. Use a fresh evidence directory for each review or demo.

```powershell
$demoDir = 'build/coreiot-demo'
$demoRun = "$demoDir/$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ'))"
New-Item -ItemType Directory -Force -Path $demoRun | Out-Null
& .venv/coreiot/Scripts/python.exe -c 'import paho.mqtt.client'
node coreiot/rules/export-sandbox-chain.cjs "$demoDir/smart-classroom-sandbox.rulechain.json"
if (-not (Test-Path coreiot/.env.demo)) { Copy-Item coreiot/.env.example coreiot/.env.demo }
```

1. In **Profiles → Device profiles**, create or select `Smart Classroom` with **Default** transport and the existing default RuleChain. In **Entities → Devices**, create `classroom-01-sim` with that profile and leave **Is gateway** off. Use its access token and the sandbox TLS endpoint in the ignored `coreiot/.env.demo` file. Match `COREIOT_DEVICE_ID` to `classroom-01-sim`. Check that any `COREIOT_MQTT_*` or `COREIOT_DEVICE_TOKEN` variables in the current shell also point to the sandbox, since shell values take precedence. [Device setup](../platform/README.md#create-the-profile-and-device)
2. In **Dashboards → Add dashboard → Import dashboard**, import `coreiot/platform/smart-classroom.dashboard.json`. Name the import **Smart Classroom — Simulation** and bind its `Classroom` alias to `classroom-01-sim`. [Dashboard setup](../platform/README.md#import-the-dashboard-template)
3. Import `build/coreiot-demo/smart-classroom-sandbox.rulechain.json` as a detached chain. Set `classroomAutomationEnabled` to Boolean `false`, `classroomManualOverride` to Boolean `true`, and `classroomDoorProximityAlertEnabled` to Boolean `false`. Set String `classroomRuleSettings` from `coreiot/rules/sandbox-settings.json`. Scope the chain's entry from the existing **Save Timeseries** success path to `classroom-01-sim` and keep the default save and RPC routes. Follow the rule guide to verify tenant node settings, rehearse automation in logging mode and configure one test recipient. [RuleChain setup](../rules/README.md#add-the-sandbox-chain) · [Recipient setup](../rules/README.md#configure-recipient-notifications)

Start a baseline simulator run from the repository root. This streams synthetic logs and keeps a copy in the evidence directory. Run one simulator at a time per device token and use Ctrl+C to stop it before changing inputs.

```powershell
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env.demo --device-id classroom-01-sim --fw-version 1.0.0 --temperature 28.5 --light 320 --motion false 2>&1 |
    ForEach-Object { [string]$_ } | Tee-Object -FilePath "$demoRun/simulator-baseline.log"
```

| Rehearsal | Prerequisite and action | Expected result and evidence |
| --- | --- | --- |
| Connect and control | Wait for `rpc_subscription_ready` and `mqtt_puback`. With automation disabled, test lamp on/off, fan on/off, and door open/close in that order. Check each ACK before continuing. | Capture the dashboard device ID, updated sample times, and lamp, fan and door state. Save `rpc_response_queued` with command ID, `ok` and `actualState`, followed by fresh telemetry. |
| Automation | Keep the automation route in logging mode. Enable the sandbox gate and release its override. Stop the baseline, then run the first command below. | After any configured buffer interval, expect lamp and fan on candidates in the RuleChain trace. Re-enable override and capture that candidates stop. Restore the disabled gate before notification rehearsal. |
| Notifications | Open the test recipient inbox and start at or below 33 °C until any previous alarm clears. Run the second command below. After receipt, restart with `--temperature 33` to recover. | Capture the alarm ID, inbox receipt with timestamp, and cleared alarm. Verify repeated high samples update the same alarm without a second creation notification. |

```powershell
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env.demo --device-id classroom-01-sim --temperature 31 --light 100 --motion true
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env.demo --device-id classroom-01-sim --temperature 35 --motion false
```

For the authenticated RPC smoke test, use `--device-name classroom-01-sim` and the UUID of this sandbox device. Store sandbox screenshots and logs as synthetic evidence. [Course tenant verification](VERIFICATION.md#run-against-the-course-tenant)

## Before the audience arrives

1. Collect A's firmware image, target board ID, flash and serial-log steps, Wi-Fi provisioning and safe stop procedure. Collect B's broker and gateway startup commands, working directory, environment file requirements, log location and shutdown steps. This checkout has firmware and gateway scaffolds. Run the physical sequence from A's and B's validated builds when available.
2. Import a separate copy of the dashboard as **Smart Classroom — Physical** and bind its `Classroom` alias to the hardware entity. Open the physical device's latest telemetry, dashboard, RuleChain debug view, recipient inbox, and local logs. Confirm the simulation dashboard still points to its separate entity.
3. Rehearse with the same network, gateway, firmware, tenant account, and physical kit. Synchronize capture clocks and filter local MQTT trace to the hardware `deviceId`. With automation inactive, set actuators to known states. Record temperature, light and motion. Prepare repeatable sensor stimuli and approved thresholds with A.
4. Use the actual approved alarm threshold and a dedicated recipient. Clear any existing test alarm through its recovery condition and confirm the recipient can distinguish the next delivery. Keep physical automation disabled until the handoff checklist passes.
5. Leave the OTA target assignment empty unless the upgrade and recovery have already passed rehearsal. Prepare the recorded successful upgrade as supporting evidence if a second physical update is impractical.

## Live sequence

| Step | Initial conditions | Action | Expected result | Evidence | Responsible subsystem |
| --- | --- | --- | --- | --- | --- |
| 1. Broker and gateway | Course network, validated B build, startup commands and local credentials available | Start the local MQTT broker and B's gateway with the reviewed commands from their recorded working directory. | Broker accepts the gateway and gateway connects to the assigned CoreIOT device. | Startup log and connection timestamps | B · MQTT and gateway |
| 2. Connect YoloUNO | Broker running, correct Wi-Fi and device ID loaded | Power on or join YoloUNO to the network. | Fresh telemetry appears on `classroom/{deviceId}/telemetry`. | Serial boot/version log and one local MQTT sample | A · firmware, B · broker |
| 3. Open dashboard | Gateway forwarding real packets, hardware alias selected | Open **Smart Classroom — Physical** and check identity, connectivity and latest timestamp. | The hardware entity is selected and samples are arriving. | Dashboard view with device ID and timestamp | B · gateway, C · dashboard |
| 4. Show live readings | Physical readings visible on both sides | Compare temperature, humidity and raw light to the corresponding local sample. | Values and sample time match the forwarded record. | Local sample and dashboard screenshot | A · sensors, B · forwarding, C · dashboard |
| 5. Trigger motion | Baseline motion is false, automation still inactive | Move through the sensor's detection area. | Motion becomes true on a fresh sample, then returns false after the sensor resets. | Timestamped telemetry and dashboard view | A · motion, C · dashboard |
| 6. Send lamp RPC | Lamp visibly off, fresh telemetry shows off, and gateway and device capture already running | Press **Lamp on**. | CoreIOT issues the boolean `setLamp` RPC. | Command timestamp and cloud request ID | C · dashboard and RPC |
| 7. Follow command and ACK | The step 6 command is in the trace | Read B's local command trace and A's device ACK. | Command and ACK use the same local ID, gateway maps it to the original cloud request, and `ok:true` accompanies `actualState:true`. | Cloud response and local command/ACK IDs | A · actuator and ACK, B · routing |
| 8. Confirm reported lamp state | Command result recorded | Observe the lamp and wait for new telemetry. | Lamp is on and a new `lamp:true` sample updates the dashboard. | Physical observation and later dashboard sample | A · device, C · dashboard |
| 9. Show fan automation | Approved override tests passed, automation now enabled and override explicitly released, fan off | Raise measured temperature above the configured fan upper threshold with A's rehearsed method. Once demonstrated, cool below the lower threshold. | RuleChain requests fan on and later off. ACKs and fresh `fan` telemetry follow. | Sensor samples, rule traces, RPC/ACK and physical observations | A · temperature and fan, B · bridge, C · RuleChain |
| 10. Show lighting automation | Approved rules active and override released. Use bright light to establish a reported lamp-off state after the manual test. | Lower measured light below the on threshold and show motion. Hold both conditions through the evaluation window, then restore bright light or let motion reset. | Lamp turns on with both conditions and turns off when a configured off condition is met. | Light and motion samples, rule traces, ACK, state and visible lamp | A · sensors and lamp, B · bridge, C · RuleChain |
| 11. Receive an alert | Recipient inbox open and no active demo alarm | Cross the agreed temperature alert threshold, hold it for a second sample, then recover below the clear threshold. | One new alarm and recipient notification, repeat sample updates the same alarm, recovery clears it. | Alarm ID plus recipient inbox timestamp, followed by clear evidence | A · sensor, C · RuleChain and Notification Center |
| 12. Show AI event | B's inference and cloud event mapping have passed rehearsal | Trigger B's agreed event and open its event widget. | Same event and timestamp appear in the gateway log and CoreIOT. | Inference log and dashboard sample | B · AI, C · dashboard |
| 13. Show OTA | Lab update and recovery have already passed, `1.0.0` is running, A has the recovery build | Assign the `1.1.0` package to the lab unit and follow the OTA runbook. | Board installs and reboots into `1.1.0`. Sensor telemetry, command ACK and reconnect pass again. | Checksum, platform status, serial boot log, post-boot version and regression record | A · OTA client, B · transport where applicable, C · package assignment |

If steps 1–3 fail, use the recovery procedure before showing live values or sending an RPC. For steps 4–13, skip a blocked check and continue with the next section whose prerequisites are met. Record the actual physical observation separately from the firmware’s reported state. Run the project’s ten sensor-to-dashboard and ten command-to-ACK trials under the same configuration and retain the raw evidence.

## Recover during the demo

1. Pause cloud controls. If the tenant is reachable and the approved automation is active, set `classroomAutomationEnabled=false` and `classroomManualOverride=true` on the hardware device under **Attributes → Server attributes**. Keep the device in the agreed safe state using its local control. Record the interruption and last sample timestamp. If a command timed out, observe the actuator or wait for a new report before retrying.
2. Check in order from YoloUNO Wi-Fi and its serial log to local broker, B's gateway and its CoreIOT connection, then the dashboard alias. If cloud access alone fails, continue the live local demonstration via the device or gateway UI. State that the CoreIOT view is delayed until the connection returns.
3. Verify a fresh hardware sample, then issue one new manual command and check its ACK and new reported state. Re-enable approved automation only after A and B confirm override and queues are in the expected state.
4. If hardware stays offline and the tenant is reachable, switch to **Smart Classroom — Simulation** and label its output synthetic. If the tenant is also unavailable, show labeled footage from the most recent verified rehearsal. Keep the two evidence sets separate. For an OTA failure, stop the rollout and follow the recovery procedure before any further actuation demo.

[Gateway mapping and acceptance](../INTEGRATION.md) · [Dashboard setup](../platform/README.md) · [RuleChain and notification setup](../rules/README.md) · [OTA handoff](../platform/OTA.md)
