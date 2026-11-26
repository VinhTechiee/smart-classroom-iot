# CoreIOT firmware package management

Use a dedicated `Smart Classroom OTA Lab` profile with `classroom-ota-virtual` for the package delivery check and `classroom-ota-board` for the single physical rollout. Keep the profile's default firmware assignment empty. Bind a copy of the [minimal dashboard](../minimal/README.md) to `classroom-ota-board` for the physical run.

The public CoreIOT OpenAPI reports `4.2.0PE` and exposes OTA package registration, binary upload and device firmware download. The course tenant's version, account permissions, individual firmware assignment and live package delivery require a signed-in check. [CoreIOT OpenAPI](https://app.coreiot.io/v3/api-docs)

| Release | Role in the lab rollout |
| --- | --- |
| `1.0.0` | Starting version and known-good recovery artifact |
| `1.1.0` | Target firmware package and expected post-reboot `fwVersion` |

## A, B and C handoff

| Owner | Input or responsibility |
| --- | --- |
| A | Supply `1.0.0` and `1.1.0` YoloUNO ESP32-S3 application `.bin` files, board revision, build commits, SHA-256 digests, image sizes, partition layout and USB recovery steps. Verify that the `1.1.0` app fits the OTA slots and describe post-boot diagnostics and rollback behavior. |
| B | Confirm that the classroom's PC gateway session can coexist with the board's HTTPS requests to the same lab entity. Configure the normal telemetry and RPC mapping. If the board cannot fetch packages via HTTPS, agree with A and C on package transfer and status before implementing a gateway-assisted path. |
| C | Verify OTA permissions and behavior on the tenant, register and assign the Member A package, capture platform state, and compare the post-reboot `fwVersion` against the assigned version. |

The candidate keeps MQTT ownership with the PC gateway for classroom monitoring and RPC. Member A's OTA client polls assigned metadata, downloads the application image and posts native update status directly over authenticated, certificate-validated HTTPS. This route requires HTTPS reachability from the board and no package forwarding by Member B. Verify HTTPS and MQTT coexistence on the physical lab entity, including whether HTTPS activity affects its active status. Use fresh `fwVersion` and the local broker trace to confirm the board's return. A gateway-assisted transfer needs an agreed delivery, retry and status interface. [ESP32-S3 OTA and rollback](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html)

Have A set the lab board's local `deviceId` to `classroom-ota-board` and B bind its per-device gateway mapping and local topics to the matching CoreIOT lab entity. Use the lab board's own device credential for both of its approved transport paths. The virtual delivery device has a separate credential. The humidity RuleChain scopes its inputs to the monitoring and simulator entities, so run the OTA telemetry and RPC checks manually on the lab dashboard. [Gateway mapping](../INTEGRATION.md)

For the HTTPS candidate, confirm the lab device can read `fw_title`, `fw_version`, `fw_checksum` and `fw_checksum_algorithm` using `GET /api/v1/{deviceToken}/attributes?sharedKeys=...`. The firmware endpoint is `GET /api/v1/{deviceToken}/firmware?title={title}&version={version}` with the assigned title and version. A's client verifies SHA-256, image applicability and any configured signature policy before marking the inactive slot for boot. It posts status via `POST /api/v1/{deviceToken}/telemetry` on the same lab entity. Keep authenticated device URLs out of logs and evidence. [HTTP shared attributes](https://thingsboard.io/docs/reference/http-api/attributes/#request-attribute-values) · [Upstream firmware endpoint](https://github.com/thingsboard/thingsboard/blob/master/common/transport/http/src/main/java/org/thingsboard/server/transport/http/DeviceApiController.java) · [HTTP telemetry](https://thingsboard.io/docs/reference/http-api/telemetry/)

## Prepare a package in the tenant

1. In the signed-in course tenant, record the version and account role. Check that the account can open **OTA updates**, create a **Firmware** package, upload its binary, and edit the lab device's firmware assignment. Have a tenant administrator handle steps outside the test account's permissions. Create `Smart Classroom OTA Lab` with default transport and disabled provisioning. Check the upload limit against Member A's build.
2. Compare each artifact's size and SHA-256 with Member A's release record. Use an ESP32-S3 application image built for the board and its OTA partition sizes. Keep A's USB recovery artifacts available separately.

   ```powershell
   $firmwarePath = Read-Host 'Path to the reviewed 1.1.0 app image'
   (Get-Item -LiteralPath $firmwarePath).Length
   Get-FileHash -Algorithm SHA256 -LiteralPath $firmwarePath
   ```

3. Under **OTA updates → Add package** register the baseline `1.0.0` and target `1.1.0` binaries. Use title `smart-classroom-yolouno`, type **Firmware**, profile `Smart Classroom OTA Lab`, and **Version** `1.0.0` or `1.1.0`. If the form has a separate version tag, set it to the same release for clarity. Upload each application `.bin` with SHA-256 and compare the stored checksum with the reviewed image. The title and version combination is unique per tenant. If it already exists, verify the stored package's profile and checksum before reuse. Record title, version, image digest, build commit and size. Leave assignment empty while preparing both packages.

[ThingsBoard OTA packages and assignment](https://thingsboard.io/docs/user-guide/ota-updates/)

## Check package delivery without hardware

1. Create `classroom-ota-virtual` on `Smart Classroom OTA Lab` with its own token. In **Entities → Devices**, edit that device and select `1.1.0` under **Firmware**. Check **Shared attributes** for the title, version and checksum. Expect platform state `INITIATED` once CoreIOT posts the assignment. If metadata is missing, verify the device assignment and that CoreIOT has processed it.
2. Set `COREIOT_TENANT_URL` to the course tenant's HTTPS origin. Load the virtual lab device credential into `COREIOT_OTA_DEVICE_TOKEN` in the local process before running the read-only [download verification script](../../tests/coreiot/ota_delivery.py) from the repository root. Use the independently reviewed size and SHA-256 from A. The verifier checks both the assigned metadata and the streamed bytes.

   ```powershell
   $reviewedSize = Read-Host 'Reviewed 1.1.0 size in bytes'
   $reviewedSha256 = Read-Host 'Reviewed 1.1.0 SHA-256'
   $env:COREIOT_TENANT_URL = 'https://app.coreiot.io'
   & .venv/coreiot/Scripts/python.exe tests/coreiot/ota_delivery.py --version 1.1.0 --size $reviewedSize --sha256 $reviewedSha256
   ```

3. Repeat for `1.0.0` by assigning it to the same virtual lab entity, updating the two reviewed inputs and setting `--version 1.0.0`. Expect exit code 0 and a JSON record with `evidence` equal to `package delivery`, the matching version, size and SHA-256. On HTTP 401/403, verify the credential belongs to this lab device and the endpoint is reachable. On 404 or mismatched metadata, verify the selected firmware, profile and processed assignment. On a digest or size mismatch, stop and reconcile against A's reviewed artifacts.
4. Record both virtual assignments, metadata, digests and outcomes. Clear the virtual device's assignment and run `Remove-Item Env:COREIOT_OTA_DEVICE_TOKEN -ErrorAction SilentlyContinue`. The physical board supplies the installation and post-boot evidence below.

[ThingsBoard shared attributes API](https://thingsboard.io/docs/reference/http-api/attributes/) · [ThingsBoard firmware download endpoint](https://github.com/thingsboard/thingsboard/blob/master/common/transport/http/src/main/java/org/thingsboard/server/transport/http/DeviceApiController.java) · [ThingsBoard OTA states](https://thingsboard.io/docs/user-guide/ota-updates/#update-states)

## Physical OTA acceptance checklist

- [ ] A has reviewed both actual application images, confirmed OTA slot capacity and a working baseline, and prepared the USB recovery artifacts and exact board-specific recovery steps. Both virtual delivery checks pass. B has verified the lab gateway mapping and A has confirmed board HTTPS access.
- [ ] Run `1.0.0` on the physical board with automation disabled. Capture A's serial boot record, fresh classroom `fwVersion: "1.0.0"`, native `current_fw_title` and `current_fw_version`, live humidity and the LED/RPC baseline on `classroom-ota-board`. Stop the simulator before connecting the lab gateway.
- [ ] Under **Entities → Devices**, edit `classroom-ota-board` and assign `1.1.0` in **Firmware**. Record assignment time in UTC, package title/version, SHA-256 and size. Verify the profile-level assignment remains empty.
- [ ] Capture CoreIOT's `QUEUED` and `INITIATED` states when available. Match the physical client's `DOWNLOADING`, `DOWNLOADED`, `VERIFIED` and `UPDATING` reports (`fw_state`) to serial or OTA logs. On failure record `fw_state: "FAILED"` and `fw_error` if emitted.
- [ ] After reboot and application self-test, confirm the physical serial log identifies `1.1.0` and the board reports `fw_state: "UPDATED"`, `current_fw_title: "smart-classroom-yolouno"` and `current_fw_version: "1.1.0"`. Match this with fresh `fwVersion: "1.1.0"` from the classroom telemetry flow. Record UTC time and calculate duration from assignment to the first corroborated success.
- [ ] Verify fresh humidity, temperature if hardware supports it, both supported LED states using matched two-way RPC ACKs and subsequent fresh `lamp` reports, and disconnect/reconnect with the production gateway. Confirm the running version after reconnect. Record evidence from the board, gateway and CoreIOT. [Built-in firmware dashboard fields](https://github.com/thingsboard/thingsboard/blob/master/application/src/main/data/json/demo/dashboards/firmware.json) · [OTA states](https://thingsboard.io/docs/user-guide/ota-updates/#update-states)

### Recover an unsuccessful rollout

1. Record the failure time, `fw_state` and `fw_error` where available, serial logs and assignment details. Clear the lab device's target assignment and stop automatic retry using A's procedure. Verify that the client will no longer apply or retry the failed target before rebooting it.
2. Apply A's rollback procedure when the previous slot is bootable and rollback is enabled. Otherwise use A's USB recovery procedure for the board and known-good `1.0.0` release. Verify the recovered version against the physical serial log and fresh CoreIOT telemetry, then repeat the post-update checks. [ESP32-S3 boot validation and rollback](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html)

Package upload, assignment, and verified HTTPS delivery in the course tenant are pending. T14 acceptance requires a physical Yolo UNO to install `1.1.0` from `1.0.0` and pass the regression checks. The repository contains the rollout and verification path. Member A owns the versioned firmware and recovery artifacts.

## If the tenant cannot support this path

Record where verification stopped, including the account role, missing menu or permission response, or unsupported download transport. Ask C to confirm access with the course tenant administrator. If the feature is unavailable on that instance, propose a PC-gateway-mediated rollout to A and B. C would maintain the release manifest and approval record, B would expose the verified artifact to the lab unit over an agreed authenticated transport, and A would validate and install it with the firmware OTA client. The team must approve assignment signaling, status reporting, integrity checks and recovery before implementing that path. This fallback would demonstrate a gateway-delivered update. Native CoreIOT OTA verification would remain pending.
