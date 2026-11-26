# Member C verification record

Follow the [platform deployment guide](PLATFORM_DEPLOYMENT.md) for setup and the [demo sequence](DEMO.md) for evidence capture. Record the checkout revision and dirty-tree diff, tenant version and permissions, entity IDs, board revision, sensor model, firmware build and gateway build. Label each record **Synthetic**, **Virtual OTA delivery**, or **Physical**.

| Task | PASS — Local implementation verified | PENDING — CoreIOT platform verification | BLOCKED — Physical or integration dependency |
| --- | --- | --- | --- |
| T11 Dashboard and RPC | Dashboard assets, minimal and extended transport tests, simulated telemetry, request correlation and REST smoke checks | Resolve the existing alias, verify rendering and both sandbox LED buttons, and capture ACK plus fresh state | A confirms board LED and measured fields. B supplies and verifies real gateway routing and ACKs. AI display depends on B's event mapping. |
| T12 RuleChain | Executable graph tests cover RH validation, freshness, threshold boundaries, override, duplicate suppression, ACK handling and alarm recovery | Import, verify equivalent queue and metadata handling, and trace dry-run, successful ON/OFF, failure and recovery | A and B must validate local override precedence and expiration at execution before enabling automatic LED control on hardware. |
| T13 Notifications | Local alarm lifecycle and notification request-body validation | Configure one approved recipient, template and rule, and verify one received message per alarm cycle | Physical notification acceptance requires a valid air-RH reading from the real sensor through A's and B's builds. |
| T14 OTA | Local OTA metadata, HTTPS delivery logic, size and digest checks | Check permissions and prove virtual device assignment and binary delivery | A's signed-off builds, device updater and recovery procedure, a lab Yolo UNO, and B's physical gateway and OTA status handoff are required. |

## Run locally

Use the [pinned simulator dependency](../README.md#install-and-run-the-python-simulator) and Node.js 22 or later. Run from the repository root.

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
node --test tests/coreiot/*.test.cjs tests/coreiot/*.test.js
git diff --check
```

The MQTT loopback test requires Paho and reports a skip if it is absent. Record passed, failed and skipped counts, and retain the test output. The Node suite includes minimal and extended dashboard and RuleChain tests. The auxiliary `coreiot/minimal/verify.cjs` entry runs the minimal tests already included above.

## Run against the course tenant

For the current hardware profile, follow the [deployment and scenario steps](PLATFORM_DEPLOYMENT.md). In step 6, run the authenticated smoke check only against `classroom-01-sim` with automation off. Expect both Boolean LED commands, two expected application rejections and a passing summary. Verify the dashboard button path separately. The [extended assets](../platform/README.md) support six RPC commands for the original kit when paired with the simulator's extended mode and the smoke runner without `--minimal`.

| Evidence | Record together |
| --- | --- |
| Real dashboard | Screenshot with `classroom-01`, fresh measured % RH, UTC sample time and firmware version. Adjacent real broker or gateway record with the same sample. |
| LED ON and OFF | Cloud request ID, requested Boolean, matching local command/ACK ID, `ok:true`, matching `actualState`, timestamped fresh `lamp`, and physical LED observation when supported. |
| RuleChain | Export or screenshots of the scoped storage branch, server attributes, queue, and debug trace for high, deadband, recovery, override, an invalid or stale sample, duplicate suppression, and a failure or timeout. |
| Alarm | Type, MAJOR severity, originator and alarm ID at creation, repeat/deadband, and clear timestamp on recovery. |
| Notification | Recipient-side Web inbox or configured channel receipt with time and matching alarm ID or event details. Record repeat suppression and delivery after a new alarm cycle. |
| Physical OTA | Reviewed size and SHA-256, tenant assignment, download/verify/apply status and failure if applicable, baseline and new serial boot versions, fresh cloud version, and telemetry/RPC/reconnect regression results. |

Restrict capture to the affected entities and remove credentials from traces and screenshots. Acknowledge missing evidence explicitly when a tenant or hardware gate has not been run.

## Measurement record

Synchronize clocks when timestamps come from different devices. Record the clock sources, estimated offset, operating conditions and timestamp resolution. A gateway receipt time is a proxy for sensor collection when the board clock is unsynchronized. Use a common recording clock or synchronized screen and log captures to measure dashboard presentation.

| Metric | Start | End | Planned trials |
| --- | --- | --- | --- |
| Sensor-to-dashboard (ms) | Sensor sample acquired, matched by identity and source timestamp | Matching point first visible on the dashboard | At least 10 |
| Command-to-ACK (ms) | Cloud command issued | Correlated application ACK received by the cloud or caller | At least 10 across ON and OFF |
| Notification response (ms) | Alarm created | Message actually received in the configured channel | One per repeatable create/clear cycle, target 3 |
| Physical OTA duration (s) | Target assignment saved | Board has rebooted into the target and the first fresh target-version telemetry is visible | Each completed physical install, including 1 successful lab install for acceptance |

Copy this row for each trial. Record any timeout or invalid measurement with its reason. Compute minimum, arithmetic mean and maximum across valid trials of the same metric and environment, and report failed or excluded trials separately.

| Environment | Metric | Trial | Start UTC or monotonic | End UTC or monotonic | Duration + unit | Correlation ID / artifact | Outcome or exclusion reason |
| --- | --- | ---: | --- | --- | ---: | --- | --- |
| | | | | | | | |

| Environment | Metric | Attempted | Valid trial count | Min | Mean | Max | Unit | Raw evidence path |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| | Sensor-to-dashboard | | | | | | ms | |
| | Command-to-ACK | | | | | | ms | |
| | Notification response | | | | | | ms | |
| | Physical OTA duration | | | | | | s | |
