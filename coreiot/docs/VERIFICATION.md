# Verification record

| Element | Implementation | Local evidence | CoreIOT evidence | Physical evidence |
| --- | --- | --- | --- | --- |
| T11 | Implemented · Python simulator, profile and dashboard templates | Locally tested · command validation and correlation, MQTT loopback, telemetry and asset checks | Pending integration · import, bind and run telemetry plus all six RPC actions on the sandbox | Pending integration · A's device and B's gateway, with device ACK and observed state |
| T12 | Implemented · configurable motion/light and fan decisions, manual override gate, RuleChain setup | Locally tested · executable node bodies, threshold boundaries and failure cases | Pending integration · tenant trace, true/false RPC results and fresh reported states | Blocked · signed-off thresholds, override signaling and real-device priority tests |
| T13 | Implemented · high-temperature and sandbox door/proximity decisions and notification setup | Locally tested · open, hold and recovery classifications | Pending integration · alarm IDs, recovery and actual test recipient inbox receipt | Pending integration · physical alert rehearsal. Door/proximity enablement depends on the agreed event definition. |
| T14 | Implemented · `1.0.0` → `1.1.0` package and recovery workflow | Locally tested · synthetic `fwVersion` reporting | Pending integration · signed-in OTA capability and role check, package assignment and verified download | Blocked · A's firmware images, OTA client, lab YoloUNO and regression run |

Promote a row to **Verified on CoreIOT** when the course tenant evidence has been saved. Use **Verified with physical hardware** after the YoloUNO, the PC gateway and CoreIOT pass the corresponding real-device checks. Firmware package upload and checksum verification establish package delivery. T14 physical evidence includes the new version running after reboot.

## Run locally

The [installation instructions](../README.md#install-and-run-the-python-simulator) set up the simulator and its single MQTT dependency. Run these commands from the repository root with Node.js on the path.

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
node --test tests/coreiot/dashboard.test.cjs tests/coreiot/rules.test.js
git diff --check
```

The Python suite checks local protocol handling, the MQTT path on loopback, and the REST smoke runner's telemetry checks. The loopback test reports a skip if Paho is missing. Install the pinned dependency for a full run. The JavaScript suite runs the checked-in RuleChain node bodies and exercises dashboard and profile bindings. Label those results synthetic.

The final review reran the Python and Node.js suites. A separate local TLS broker check passed with a test CA, hostname validation, an RPC received before SUBACK, its application ACK, fresh telemetry and MQTT disconnect. The REST smoke runner exercised all six actions and both rejections against local simulated responses. The authenticated course-tenant run is pending because the workspace has no tenant endpoint or credentials configured.

## Run against the course tenant

1. Use the [profile and dashboard setup](../platform/README.md) to provision the dedicated simulation entity `classroom-01-sim`, bind the dashboard, and record the actual tenant version. Leave automation inactive during the control test. Start the [Python simulator](../simulator/README.md) with that entity's access token, matching device name, `--fw-version 1.0.0` and the default synchronized clock.
2. For automated connectivity verification, set `COREIOT_TENANT_URL` to the course tenant's HTTPS URL and `COREIOT_REST_AUTH` to the test account's `Bearer …` header value or `ApiKey …` when supported. Use a local shell and the permissions needed to read and control the simulator entity. `COREIOT_REST_AUTH` is separate from its MQTT access token. Set `$sandboxDeviceId` to the entity UUID from **Entities → Devices**, then run the command after the first samples arrive. Use the exact sandbox name.

```powershell
& .venv/coreiot/Scripts/python.exe tests/coreiot/platform_smoke.py --sandbox-device $sandboxDeviceId --device-name classroom-01-sim
```

3. Expect six JSON lines for successful commands with unique ACK IDs and advancing reported-state timestamps at or after each ACK, two JSON lines for application rejections, and a passing summary. The runner sends both states for each actuator and restores its initial state on a successful run. It exits nonzero when credentials, application responses, fresh telemetry, or permissions are missing. Save the output as synthetic connectivity evidence.
4. Exercise the [RuleChain and notification scenarios](../rules/README.md) using synthetic telemetry. Capture positive, override-gated and stale-input traces. Run alarm create, repeat, recovery, and reopen checks, then capture actual receipt from the intended recipient inbox. If the Web channel is absent, choose a supported delivery channel with C and verify actual receipt through that channel.
5. Check OTA support and permissions against the signed-in tenant following the [OTA handoff](../platform/OTA.md). After A provides the images, capture virtual-device package metadata and download digest before booking the lab install.

The tenant steps require a course device token, tenant access and recipient access. Capture the tenant version, UTC timestamps, device or command IDs, outcome, and source logs with credentials removed. Keep simulation and [physical demo evidence](DEMO.md) in separate records.

[ThingsBoard REST API](https://thingsboard.io/docs/reference/rest-api/)
