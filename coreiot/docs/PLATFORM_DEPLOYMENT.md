# CoreIOT platform deployment

The current kit uses one Yolo UNO ESP32-S3, one humidity sensor, a PC gateway, and CoreIOT. HTTP connectivity and MQTT telemetry have already been verified on `classroom-01-sim`. The humidity dashboard has been imported. Alias resolution, dashboard RPC, RuleChain execution, notification delivery, and OTA still need the checks below. The public CoreIOT API identifies itself as ThingsBoard 4.2.0PE. Record the signed-in tenant version and role before changing configuration. [CoreIOT public OpenAPI](https://app.coreiot.io/v3/api-docs)

## 1. Verify the existing profile and sandbox device

1. Open **Profiles → Device profiles → Smart Classroom**. Verify the default device transport and record the existing RuleChain assignment. Keep the existing profile.
2. Open **Entities → Devices → classroom-01-sim**. Confirm the exact device name, the **Smart Classroom** profile, **Is gateway** disabled, and access-token credentials. Record the device UUID for the optional REST smoke check. Keep the device credential in local configuration.
3. Label screenshots and logs from this entity **Synthetic**. Reserve `classroom-01` and a separate dashboard and token for hardware.

## 2. Configure the endpoint and local credentials

From the repository root in PowerShell, use the existing Python environment or follow the setup guide to install the pinned Paho dependency first. Create the ignored config file only if it is absent. [Python environment setup](../README.md#install-and-run-the-python-simulator)

```powershell
if (-not (Test-Path coreiot/.env)) { Copy-Item coreiot/.env.example coreiot/.env }
git check-ignore coreiot/.env
```

In your local editor, set `COREIOT_MQTT_URL=mqtt://app.coreiot.io:1883`, `COREIOT_DEVICE_ID=classroom-01-sim`, and the sandbox credential in `COREIOT_DEVICE_TOKEN`. Keep the token out of logs, screenshots, terminal commands, and Git. Environment variables in the launch shell override the file. Leave the CA setting unset for this connection. Port 8883 was unreachable on the demo network. Port 1883 carries MQTT and the device credential without transport encryption. Use it for the dedicated sandbox on the approved demo network, and use the tenant's verified `mqtts://` endpoint with certificate validation when reachable. [CoreIOT connection guide](https://coreiot.io/docs/ket-noi-va-gui-du-lieu/) · [MQTT Device API](https://thingsboard.io/docs/reference/mqtt-api/getting-connected/)

## 3. Start the synthetic baseline

Use the same PowerShell window for the later scenarios. Run one instance at a time with the sandbox credential.

```powershell
$python = (Resolve-Path .venv/coreiot/Scripts/python.exe).Path
$sim = @('-m', 'coreiot.simulator', '--minimal', '--env-file', 'coreiot/.env', '--device-id', 'classroom-01-sim', '--fw-version', '1.0.0')
& $python @sim --humidity 65 --lamp false
```

Expect `mqtt_connected`, `rpc_subscription_ready`, `telemetry_queued`, and `mqtt_puback`. The timestamped telemetry envelope carries `deviceId`, `humidity`, `lamp`, `fwVersion`, and the synchronized source `ts`. A new sample arrives every five seconds by default and after each applied command.

## 4. Bind the existing dashboard

Open the imported humidity dashboard. If a new copy is needed, use **Dashboards → Add dashboard → Import dashboard** and select [smart-classroom-humidity.dashboard.json](../minimal/smart-classroom-humidity.dashboard.json). Name the sandbox dashboard **Smart Classroom — Synthetic**. Use [smart-classroom-temp-humidity.dashboard.json](../minimal/smart-classroom-temp-humidity.dashboard.json) for a separate synthetic temperature test or a device with measured temperature.

1. Open the dashboard, enter **Edit mode**, choose **Entity aliases** in the toolbar, and edit **Classroom** with its pencil icon.
2. For a deterministic binding, select **Filter type → Single entity**, **Type → Device**, and pick the exact `classroom-01-sim` result. For a portable binding, select **Filter type → Entity name**, **Type → Device**, and set **Name expression** (the entity name filter) to `classroom-01-sim`. Keep **Resolve as multiple entities** off. The name filter matches a prefix. If any other device begins with the same string, use **Single entity**.
3. Save the alias, save the alias dialog, and save the dashboard editor. Confirm the Device row resolves to `classroom-01-sim` and both LED buttons have the **Classroom** RPC target before actuating. Re-export the verified tenant dashboard with credentials removed. [Entity alias settings](https://thingsboard.io/docs/pe/user-guide/aliases/) · [Dashboard bindings](../minimal/DASHBOARD.md)

## 5. Verify live telemetry and freshness

1. Under **Entities → Devices → classroom-01-sim → Latest telemetry**, confirm `humidity` is 65% RH, `lamp` is Boolean `false`, `fwVersion` is `1.0.0`, and `deviceId` is `classroom-01-sim`. Check that new point timestamps match the simulator envelope. Compare with the dashboard's current value and **Humidity history**.
2. Check **CoreIOT activity** and the **Recent humidity (30 s)** chart independently. Activity reflects the platform's inactivity policy. The recent chart and humidity timestamp tell you whether the sensor has supplied a current value. An old latest value can remain visible when publishing stops.
3. Check the **Active alarms** table after the alarm test. The **Gateway AI events** table needs B's actual device alias and telemetry key if events are available. Leave its empty state or remove it from the demo copy if no integration exists. The simulator supplies neither AI events nor temperature by default. [Device activity behavior](https://thingsboard.io/docs/user-guide/connectivity-status/) · [Widget details](../minimal/DASHBOARD.md)

## 6. Verify two-way LED ON and OFF

Keep automation disabled or the RPC branch detached. Press **LED ON**, wait for evidence, then **LED OFF**. Each button sends a two-way non-persistent `setLamp` with JSON Boolean `true` or `false` and a 10-second timeout.

For each action, capture the cloud request ID and correlated acknowledgement with a command ID, `ok:true`, and matching Boolean `actualState`. Open the browser's **Network** response for `POST /api/rpc/twoway/{device UUID}` or correlate the simulator or gateway RPC logs. Verify a separate new `lamp` point with that value and a timestamp newer than the preceding state and at or after the ACK timestamp when clocks are synchronized. On hardware, also observe the physical LED. The widget success message and MQTT `mqtt_puback` establish transport progress. Use the application ACK and fresh telemetry together for acceptance.

For the automated equivalent, set the HTTPS `COREIOT_TENANT_URL` and separate `COREIOT_REST_AUTH` header value (`Bearer` or tenant-supported `ApiKey`) in a local process using the approved credential store. Run this in a second PowerShell window while the synchronized simulator is publishing.

```powershell
$env:COREIOT_TENANT_URL = 'https://app.coreiot.io'
$sandboxDeviceId = Read-Host 'UUID of classroom-01-sim'
& .venv/coreiot/Scripts/python.exe tests/coreiot/platform_smoke.py --minimal --sandbox-device $sandboxDeviceId --device-name classroom-01-sim
```

Expect two successful commands with distinct ACK IDs and advancing state timestamps, followed by expected rejections for an unsupported method and a non-Boolean parameter. A successful run restores the starting LED state. Use `--expect-temperature` only during the separate synthetic temperature test. [REST API](https://thingsboard.io/docs/reference/rest-api/)

## 7. Import the humidity RuleChain

1. Export the current Root RuleChain for rollback. Open **Rule chains → Add rule chain → Import rule chain**, and import [smart-classroom-humidity.rulechain.json](../minimal/smart-classroom-humidity.rulechain.json) as **Smart Classroom - Humidity**.
2. Open the new chain and confirm its LED RPC node has no incoming edge. Keep the existing Root designation and profile routing. Apply the attributes in step 8 before attaching the branch.

## 8. Add server attributes and attach after storage

Open **Entities → Devices → classroom-01-sim → Attributes → Server attributes**. Use the following types and values. The [example JSON](../minimal/server-attributes.example.json) is a key-value body for tenants that configure attributes through REST. The numeric values are demonstration thresholds for air relative humidity.

| Attribute | Platform type | Initial value |
| --- | --- | --- |
| `classroomHumidityMeasurement` | String | `relative_air_humidity` |
| `classroomHumidityHigh` | Number (integer is sufficient) | `80` |
| `classroomHumidityRecovery` | Number (integer is sufficient) | `75` |
| `classroomAutomationEnabled` | Boolean | `false` |
| `classroomManualOverride` | Boolean | `true` |

Configure the threshold pair together, with `0 <= recovery < high <= 100`. CoreIOT manages `active`. The chain writes `classroomLastLedAttempt` as an internal String, so leave it unset on initial deployment.

Check that the existing **Save time series** path writes latest values at the incoming `metadata.ts`. For key-value messages with a metadata timestamp, this means **Use server timestamp** is off or an equivalent path preserves the sample time. If latest points have a different timestamp, leave the new branch detached until the tenant administrator confirms a matching storage path. [Save time series settings](https://thingsboard.io/docs/reference/rule-engine/nodes/action/save-timeseries/)

On that path, add a **Rule chain** node targeting **Smart Classroom - Humidity** from **Save time series → Success** in parallel with the existing edges. Save the graph and confirm ordinary **Latest telemetry** still advances. Use debug to verify the incoming `metadata.ts` and that **Latest humidity and controls** enriches the message data with `humidity` and `lamp` objects containing `ts` and `value`, plus typed `ss_` server attributes. The chain keeps the incoming reading as `sample` for comparison. Confirm **Order by device** uses the sequential-by-originator queue and that the save-attempt attributes node uses server scope with notifications disabled. If the required queue or result handling is unavailable, follow the alarm-only wiring in the node guide and leave actuation disconnected. [Exact node configuration and rollback](../minimal/AUTOMATION.md)

## 9. Enable automation in stages on the simulator

1. With automation off and override on, use the normal sample first. Confirm there is no LED attempt and that the alarm branch can still run. The chain rejects invalid, missing, superseded, or stale readings, including RH samples older than 30 seconds or over five seconds into the future.
2. Leave the RPC node disconnected. Set `classroomAutomationEnabled` to Boolean `true` and `classroomManualOverride` to Boolean `false` on the simulator. Start an out-of-band sample with a mismatched LED state. Confirm the dry-run candidate has Boolean parameters, the server attempt write succeeds, and repeat samples are suppressed during cooldown. Set override `true` and confirm it suppresses candidates. Recheck the configured queue and the save result.
3. Wait through the 12-second cooldown before starting the live test. If ordering, dry-run suppression and result handling are verified, add **Valid LED command → True → RPC LED - connect in simulator**, alongside the candidate log. Release override for automatic trials. Turn on override before manual RPC and wait for any in-flight request to resolve. Disable automation, set override `true`, and remove the extra RPC edge after the sandbox trial if the shared tenant needs to return to its starting configuration.

Keep automation disabled and override set on the hardware entity until A and B agree and verify how local actions, manual priority, and expiration are enforced at execution time. Changing an attribute cannot recall a command already sent. [RuleChain behavior and fault cases](../minimal/AUTOMATION.md) · [Shared contract](../../shared/PROTOCOL.md)

## 10. Run the synthetic scenarios

Run the commands below from the same PowerShell window as step 3. Use Ctrl+C between processes. Keep the same CoreIOT device, RuleChain, attribute values, and alarm records throughout. For the deadband and recovery restarts, carry forward the last confirmed LED state with `--lamp`. Restarting initializes that synthetic state. Start 77% and 70% with `true` only after the 85% stage has a valid automatic ON ACK and a fresh `lamp:true` point. Use the absence of an RPC candidate and the unchanged active alarm at 77% as hysteresis evidence.

| Scenario | PowerShell command or action | Expected result |
| --- | --- | --- |
| Normal | `& $python @sim --humidity 65 --lamp false` | Fresh 65% and LED OFF. No active high-humidity alarm. |
| High | `& $python @sim --humidity 85 --lamp false` | One active MAJOR alarm. With automatic RPC enabled, one successful LED ON and fresh `lamp:true`. |
| Hysteresis | `& $python @sim --humidity 77 --lamp true` | Alarm stays active with the same ID. No LED command and the LED report stays ON. |
| Recovery | `& $python @sim --humidity 70 --lamp true` | The existing alarm clears. With automatic RPC enabled, one LED OFF with valid ACK and fresh `lamp:false`. Wait through the preceding attempt's cooldown if needed. |
| Manual ON/OFF | `& $python @sim --humidity 65 --lamp false`, set override Boolean `true`, then use **LED ON** and **LED OFF** or the command in step 6 | Both manual requests pass step 6. With automation enabled, holding at 65% with LED ON under override produces no automatic OFF. Explicitly release override after the test. |
| RPC timeout | Set override `true` and run `& $python @sim --humidity 65 --lamp false --drop-ack --timeout-ms 1000`. Press **LED ON**. | Device task applies and fresh `lamp:true` may appear. The gateway returns `ok:false`, `error:"device_timeout"` because the application ACK was dropped. For a cloud-level 10-second timeout, use `& $python @sim --humidity 65 --lamp false --ack-delay-ms 11000 --timeout-ms 15000` and capture the timeout before any later state report. |
| Disconnect/reconnect | Ctrl+C, then restart with `& $python @sim --humidity 65 --lamp false` or the last confirmed `--lamp true` if it was ON | Stop gives `mqtt_disconnected`, and the humidity timestamp stops. Wait over 30 seconds for the recent chart to empty. Cloud inactivity depends on tenant policy. Restart gives connect, resubscribe, and fresh telemetry. For an in-process reconnect, interrupt and restore the demo network while leaving the process running. |
| Optional temperature | `& $python @sim --humidity 65 --lamp false --temperature 28.5` | Synthetic 28.5 °C appears on the separate temperature dashboard. Return to humidity-only with the baseline command. Prior temperature points remain in the sandbox history. |
| Missing humidity | `& $python @sim --omit-humidity --lamp false` | Other telemetry advances. No new humidity decision or alarm recovery is triggered. The last stored humidity ages out of the recent chart. |

Record the **LED ACK accepted**, **LED ACK rejected**, and transport failure relations when testing automatic fault paths. Keep automatic retries observable: the cooldown suppresses duplicate attempts, and any later attempt requires a newer fresh sample and a current mismatch. [Simulator flags](../simulator/README.md) · [RuleChain fault test flags and trace](../minimal/AUTOMATION.md)

## 11. Configure notifications and verify delivery

1. Confirm that the RuleChain is the single producer of `Classroom High Humidity` on this device. The alarm severity is **MAJOR**. With default thresholds and fresh relative humidity, 80% or above opens or updates one active alarm, 77% keeps it active, and 75% or below clears it. This runs independently of LED automation.
2. In **Notification Center → Recipients**, add **Smart Classroom Demo Recipient** for the approved platform user. In **Templates**, create the **Alarm** template **Smart Classroom - High Humidity** with **Web** enabled. In **Rules**, choose the Alarm trigger, the exact alarm type, **MAJOR**, and **Alarm created** only. Select the template and a single immediate delivery stage for that recipient. Check any catch-all rule with the same recipient and channel for overlapping delivery.
3. Set up the tenant-specific recipient and rule relationships in the UI, or use the REST body assets and substitution steps if the signed-in tenant exposes those endpoints and permissions. Re-run the synthetic 65 → 85 → 77 → 70 sequence with automatic actuation disabled if desired. At 85%, verify the named recipient actually receives one item in their Web inbox. Hold the same high readings and verify no second item. Capture the clear at 70% and reopen with a new high cycle to verify one new item. Save recipient-side receipt time and alarm ID, as well as the device alarm trace. If Web is unavailable, use an approved, configured delivery channel and verify receipt there. [Notification assets and UI/API setup](../minimal/NOTIFICATIONS.md)

## 12. Switch to the real gateway and sensor

1. Get A's validated build, board revision, humidity sensor part number and LED mapping. Confirm the sensor measures air % RH. Use the temperature variant only if the same hardware reports measured °C. For another humidity quantity, agree its key, unit and threshold policy with A and B before enabling the air-RH chain on the hardware.
2. Get B's startup steps and per-device mapping. Stop the simulator for the demo switch. Create or verify `classroom-01` as a separate standard device and use its own cloud credential on B's gateway. Keep the local contract topics `classroom/classroom-01/{telemetry,cmd,ack}` and cloud per-device MQTT routing. Forward the validated keys and omit unavailable readings. Use gateway receipt time when the Yolo UNO clock is unsynchronized. [Gateway topic and ACK mapping](../INTEGRATION.md) · [Team protocol](../../shared/PROTOCOL.md)
3. Import or duplicate the humidity dashboard as **Smart Classroom — Physical** and set its alias to **Single entity → Device → classroom-01**. Remove the LED controls and state display from this physical copy if support is unconfirmed. Apply the initial automation flags and set the RH measurement attribute only after confirming the sensor. Compare a real local sample with the dashboard and test manual ACK, fresh state and visible LED where supported. Verify physical disconnect/reconnect separately from the gateway cloud connection. Save real and synthetic evidence under distinct names. [Physical demo](DEMO.md)

## 13. Perform physical OTA

1. Verify tenant OTA permissions and that A has supplied validated `1.0.0` and `1.1.0` application images, reviewed digests and sizes, and a USB recovery path. Prepare **Smart Classroom OTA Lab** with the profile firmware assignment empty. In **OTA updates → Add package**, upload the approved **Firmware** builds with SHA-256 and bind them to that lab profile.
2. Under **Entities → Devices**, assign `1.1.0` in the **Firmware** field on `classroom-ota-virtual`, then run the commands below. Load `COREIOT_OTA_DEVICE_TOKEN` for the virtual entity through the local credential store before running them. Repeat after assigning `1.0.0`, with its reviewed inputs and `--version 1.0.0`. A successful run returns a JSON record with version, size, and SHA-256. Clear the virtual assignment and process credential after testing. [Virtual delivery verification](../platform/OTA.md#check-package-delivery-without-hardware)

   ```powershell
   $env:COREIOT_TENANT_URL = 'https://app.coreiot.io'
   $reviewedSize = Read-Host 'Reviewed 1.1.0 size in bytes'
   $reviewedSha256 = Read-Host 'Reviewed 1.1.0 SHA-256'
   & .venv/coreiot/Scripts/python.exe tests/coreiot/ota_delivery.py --version 1.1.0 --size $reviewedSize --sha256 $reviewedSha256
   ```

3. With A and B, bind the lab board and gateway session to `classroom-ota-board`. Record the running `1.0.0` from boot logs and fresh telemetry. Assign `1.1.0` on the device, observe download, integrity verification, installation and reboot, and verify `1.1.0` in boot and fresh telemetry. Repeat humidity, any supported temperature, both supported LED states, and reconnect. The Yolo UNO can fetch firmware bytes directly over HTTPS if that path and its coexistence with gateway MQTT are verified. Gateway-assisted transfer requires A and B's agreed interface and implementation. [Physical acceptance checklist](../platform/OTA.md#physical-ota-acceptance-checklist) · [Evidence record](VERIFICATION.md)

## Troubleshooting

| Symptom | Check |
| --- | --- |
| MQTT does not reach `rpc_subscription_ready` | Run `Test-NetConnection app.coreiot.io -Port 1883`. Check sandbox device credentials locally, environment override, broker URL, and whether another client is using the same credential. |
| Device has telemetry and dashboard is blank | Inspect the saved `Classroom` filter, selected entity, latest keys and widget time range. For a widget missing in this tenant, add its built-in equivalent and recreate the binding. |
| Endpoint receives telemetry and RPC times out | Confirm the simulator or gateway subscribed to the RPC request topic. Check the request ID, local ACK deadline and matching response topic. Compare the last and current `lamp` timestamps before retrying. |
| Alarm or LED attempt never appears | Verify exact `deviceId`, typed RH attributes, the latest-value fields and timestamps in the enriched message data, queue availability, and RuleChain debug relations. For LED attempts also check `ss_active`, override, enable flag, attempt cooldown, and the same-sample Boolean `lamp`. |
| Alarm appears and recipient receives nothing | Confirm the recipient, enabled channel, matching template and created trigger. Start a new create cycle after a valid recovery. |
| OTA delivery or reboot fails | Save sanitized status, stop retries and clear only the affected lab assignment. Follow A's rollback or USB recipe and verify the restored version and regressions. |
