# CoreIOT firmware package management

The cloud rollout uses a dedicated `Smart Classroom OTA Lab` profile and a single lab device. `Smart Classroom` is the monitoring and control profile. Keep OTA assignment to the lab device until the integrated upgrade and recovery have been demonstrated on a YoloUNO.

| Release | Role in the lab rollout |
| --- | --- |
| `1.0.0` | Starting version and known-good recovery artifact |
| `1.1.0` | Target firmware package and expected post-reboot `fwVersion` |

## A, B and C handoff

| Owner | Input or responsibility |
| --- | --- |
| A | Supply `1.0.0` and `1.1.0` YoloUNO ESP32-S3 application `.bin` files, board revision, build commits, SHA-256 digests, image sizes, partition layout and USB recovery steps. Verify that the `1.1.0` app fits the OTA slots and describe post-boot diagnostics and rollback behavior. |
| B | Confirm the lab network and PC gateway path. If the board cannot fetch packages via HTTPS, agree with A and C how the gateway receives CoreIOT OTA metadata/data, transfers the verified image, and relays status before implementing that path. |
| C | Verify OTA permissions and behavior on the tenant, register and assign the Member A package, capture platform state, and compare the post-reboot `fwVersion` against the assigned version. |

The PC gateway is the MQTT Device API client for integrated classroom monitoring and RPC. One candidate OTA path is for the lab board to poll OTA metadata and retrieve the package over HTTPS if the board can reach CoreIOT and the tenant supports the native HTTP OTA API. Keep MQTT ownership with the gateway and verify that device-token HTTP access can coexist with the MQTT session. A gateway-assisted transfer would need its own agreement on delivery, retry and status reporting. The local MQTT draft defines telemetry, commands and acknowledgements, so an OTA relay requires a separate team-reviewed proposal. [ESP32-S3 OTA and rollback](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html)

For the HTTPS candidate, confirm the lab device can read `fw_title`, `fw_version`, `fw_checksum` and `fw_checksum_algorithm` using `GET /api/v1/{deviceToken}/attributes?sharedKeys=...`. The upstream firmware endpoint is `GET /api/v1/{deviceToken}/firmware?title={title}&version={version}` with the assigned title and version. A's client verifies the integrity and applicability of the downloaded image before marking the new slot for boot. [HTTP shared attributes](https://thingsboard.io/docs/reference/http-api/attributes/#request-attribute-values) · [Upstream firmware endpoint](https://github.com/thingsboard/thingsboard/blob/master/common/transport/http/src/main/java/org/thingsboard/server/transport/http/DeviceApiController.java#L323-L346)

## Prepare a package in the tenant

1. Record the tenant URL and version, the test account role, and whether the account can open **OTA updates**, add a **Firmware** package, and edit the lab device's firmware assignment. Confirm these capabilities in the signed-in course tenant. If testing as an operator, have the tenant administrator confirm package upload permissions. Create `Smart Classroom OTA Lab` and set it on the lab device. Check the artifact type, upload limit and OTA transport against Member A's build.
2. Compare the artifact's size and SHA-256 with Member A's release record. Run the following from the repository root using the [Python simulator environment](../README.md#install-and-run-the-python-simulator).

   ```powershell
   $firmwarePath = Read-Host 'Path to the reviewed 1.1.0 app image'
   & .venv/coreiot/Scripts/python.exe -c 'from hashlib import sha256; from pathlib import Path; import sys; image = Path(sys.argv[1]).read_bytes(); print(len(image), sha256(image).hexdigest())' $firmwarePath
   ```

3. Add a package in **OTA updates → Add package**. Use title `smart-classroom-yolouno`, type `Firmware`, device profile `Smart Classroom OTA Lab`, and version `1.1.0`. Upload A's application image and use SHA-256 for the checksum. If the title and version already exist, compare the existing package's checksum with the reviewed image before reusing it. Record the package title, version, image digest, build commit, size, and target lab device. Leave firmware assignment empty while preparing the package.

[ThingsBoard OTA packages and assignment](https://thingsboard.io/docs/user-guide/ota-updates/)

## Check package delivery without hardware

1. Create a virtual device on `Smart Classroom OTA Lab` with its own token. In **Entities → Devices**, edit that device and select `1.1.0` under **Firmware**. Check **Shared attributes** for the title, version and checksum. Expect platform state `INITIATED` once CoreIOT posts the assignment.
2. For the proposed HTTPS path, use the virtual device token to read the four `fw_` keys through `GET /api/v1/{token}/attributes?sharedKeys=fw_title,fw_version,fw_checksum,fw_checksum_algorithm`. Download `GET /api/v1/{token}/firmware?title={title}&version={version}` with both query values URL-encoded. If the team approved a different download path, use that path for the delivery check. Save the response under ignored `build/` and repeat the size and SHA-256 check above against A's original.
3. Record the virtual assignment, metadata and digest with credentials removed. Clear the virtual device's assignment. A matching download establishes package delivery evidence. The real board supplies the install and post-boot evidence described below.

[ThingsBoard shared attributes API](https://thingsboard.io/docs/reference/http-api/attributes/) · [ThingsBoard firmware download endpoint](https://github.com/thingsboard/thingsboard/blob/master/common/transport/http/src/main/java/org/thingsboard/server/transport/http/DeviceApiController.java) · [ThingsBoard OTA states](https://thingsboard.io/docs/user-guide/ota-updates/#update-states)

## Observe, verify and recover

1. After the delivery check passes and A confirms the board can fetch and apply the package, record `fwVersion: "1.0.0"` and A's serial boot log. Edit the physical lab device under **Entities → Devices** and select `1.1.0` in **Firmware**. Keep the profile-level assignment empty.
2. Record the assignment and available native firmware update states. `fw_title`, `fw_version` and checksum describe the assigned target. After reboot, compare the reported `fwVersion` with A's serial boot log, then rerun telemetry, remote RPC/ACK, reconnect and applicable rule checks. Capture pre- and post-update versions, UTC timestamps, platform update states, and serial logs.
3. On download, integrity, or boot failure, record the failure and clear the lab assignment. Follow A's procedure to stop pending retries and verify the client no longer sees the failed package as its target before resuming downloads. If the board still boots, check A's boot validation and rollback status against the recovery build before retrying. If USB recovery is needed, follow A's recovery instructions and verify the recovered `fwVersion` and RPC/telemetry again.

The simulator can exercise the dashboard's `fwVersion` display. Package upload and assignment need the target tenant, and hardware OTA acceptance needs A's versioned artifacts and a real YoloUNO run. [ThingsBoard OTA status](https://thingsboard.io/docs/user-guide/ota-updates/#update-states)

## If the tenant cannot support this path

Record where verification stopped, including the account role, missing menu or permission response, or unsupported download transport. Ask C to confirm access with the course tenant administrator. If the feature is unavailable on that instance, propose a PC-gateway-mediated rollout to A and B. C would maintain the release manifest and approval record, B would expose the verified artifact to the lab unit over an agreed authenticated transport, and A would validate and install it with the firmware OTA client. The team must approve assignment signaling, status reporting, integrity checks and recovery before implementing that path. This fallback would demonstrate a gateway-delivered update. Native CoreIOT OTA verification would remain pending.
