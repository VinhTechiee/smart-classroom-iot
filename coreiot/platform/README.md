# CoreIOT device profile and dashboard

## Create the profile and device

1. Sign in to the course tenant as a user who can manage devices and dashboards. Create a dedicated test device named `classroom-01-sim` with its own access token for synthetic runs. Use a separate entity for the hardware.
2. In **Profiles → Device profiles**, add `Smart Classroom`. Set **Transport type** to **Default** for the standard MQTT topics and leave automatic provisioning disabled. Leave the default RuleChain in place for the initial monitoring and control smoke test. Keep profile firmware assignment empty.
3. In **Entities → Devices**, add the classroom device with profile `Smart Classroom`. Leave **Is gateway** off because the PC gateway uses the standard MQTT Device API for each classroom. Read the device's access token in **Manage credentials** and supply it to the simulator or gateway via local configuration. Each classroom has its own CoreIOT device and token. Use the endpoint and TLS settings shown by the tenant.

The CoreIOT UI documents device creation and dashboard setup. The profile and built-in widget settings below use its upstream ThingsBoard model, so menu labels and available widgets may vary by tenant version. [CoreIOT UI](https://coreiot.io/docs/tong-quan-giao-dien/) · [ThingsBoard device profiles](https://thingsboard.io/docs/user-guide/device-profiles/)

Use the [device profile template](smart-classroom.device-profile.json) and [device template](smart-classroom.device.json) for reproducible setup. They describe the UI settings and follow the upstream entity REST payload schema. To use them with a compatible tenant's REST API, create or look up the profile first, then replace `${deviceProfile.id}` in the device template with its returned UUID and `${deviceName}` with the agreed classroom name. Check the tenant's Swagger before creating the entities. Both templates leave credential generation to the tenant. [ThingsBoard entity templates](https://thingsboard.io/docs/iot-hub/contribution-guides/device/#entity-templates) · [REST API](https://thingsboard.io/docs/reference/rest-api/)

The `deviceId` in telemetry matches the agreed local MQTT topic ID and this CoreIOT device name. Monitoring and manual control use the existing telemetry keys and require zero custom shared attributes. Automation setup uses server attributes documented in the [RuleChain setup](../rules/README.md). CoreIOT supplies native shared attributes when an [OTA package](OTA.md) is assigned.

## Import the dashboard template

For the physical demonstration, import the [expanded dashboard](smart-classroom-expanded.dashboard.json) for `classroom-01`. Import the [public monitoring dashboard](smart-classroom-public.dashboard.json) separately and bind it only to the approved public telemetry entity. The sections below describe the generic sandbox template.

1. Open **Dashboards → Add dashboard → Import dashboard** and upload [smart-classroom.dashboard.json](smart-classroom.dashboard.json). The template contains built-in widget references and has been checked locally. Import and rendering still require a CoreIOT tenant check.
2. Open the imported **Smart Classroom** dashboard in edit mode. Edit its `Classroom` entity alias, choose **Single entity → Device**, and select the intended test device. The template starts with an unresolved name filter so it can be reused in different tenants without an entity ID or a live RPC target. Save the alias and dashboard before leaving edit mode.
3. Start the simulated gateway from the [Member C setup](../README.md). Confirm the widgets populate and verify that each button targets the alias you selected. Keep the dashboard private and assign it only to operators who should control that device.

[CoreIOT dashboard guide](https://coreiot.io/docs/tong-quan-ve-dashboard/) · [Dashboard import](https://thingsboard.io/docs/user-guide/dashboards/#import-dashboard) · [Entity aliases](https://thingsboard.io/docs/user-guide/aliases/)

### Manual setup for a different tenant version

Create a dashboard called `Smart Classroom`, add the `Classroom` single-device alias, then add the built-in widgets below and choose `Classroom` as the data source. Add telemetry as **Time series** for both latest values and history. Set the dashboard history widgets to a live 30-minute window with aggregation disabled. Give the recent chart its own 30-second realtime window with aggregation disabled.

| Widget | Keys and display |
| --- | --- |
| Entities table, system monitoring | `deviceId`, `fwVersion`, `active` as a platform attribute, and last sample time derived from the `temperature` telemetry point's timestamp |
| Entities table, environmental monitoring | `temperature` (°C), `humidity` (%), `light` (raw), `motion` (detected or clear), `distance` (cm) |
| Entities table, actuator monitoring | `lamp` (on or off), and `door` (open or closed) from the last reported telemetry |
| Recent temperature samples | `temperature` as points in a 30-second rolling time window |
| Time series line charts, environmental history | Individual series for `temperature` (°C), `humidity` (%), and `light` (raw) |
| Time series table, actuator history | Timestamp and reported `lamp` and `door` for each stored sample |

CoreIOT's sample timestamp is the source `ts` when synchronized and gateway receipt time otherwise. To display **Last telemetry update (UTC)** in the system table, configure a `temperature` data key with a post-processing function that returns `new Date(time).toISOString()` for a valid sample. The export includes that formatting and the boolean labels. [Data key post-processing](https://thingsboard.io/docs/user-guide/advanced-data-key-configuration/#data-post-processing-function) · [Time series table](https://thingsboard.io/docs/reference/widgets/tables/timeseries-table/)

Platform `active` indicates activity on the cloud-facing entity and follows the tenant's inactivity policy. A gateway can stay connected when YoloUNO has stopped reporting. Check the recent samples and last telemetry timestamp before interpreting the last reported actuator state. Treat a blank value as unknown and an update older than 30 seconds as stale for the sandbox's five-second report interval. If the tenant stores device state in time series, change the `active` column source accordingly. If widget post-processing or realtime chart updates are unavailable, use the device's **Latest telemetry** update time and the **Attributes** or **Latest telemetry** device state fields. Set a suitable freshness window with Members A and B if the hardware cadence differs. [Device State connectivity semantics](https://thingsboard.io/docs/user-guide/connectivity-status/)

When Member B supplies the accepted AI event payload, add an **AI events** time series table with timestamp and the agreed event fields. Source it from the classroom alias if B publishes classroom telemetry, or an alias for the separately agreed AI entity. Confirm the event type, timestamp, confidence or other fields supplied by B, and compare a live event with the gateway log before including it in the demo.

Under **Control widgets**, add an **RPC Button** per action below. Choose the `Classroom` alias as the target. Turn **Is one way command** and **RPC request persistent** off, turn **Show RPC command execution error** on, and set the timeout to 10,000 ms. Enter each parameter as a bare JSON boolean in **RPC method params**. The buttons issue an explicit action and the reported state table shows the result.

| Button | RPC method | RPC params |
| --- | --- | --- |
| Lamp on | `setLamp` | `true` |
| Lamp off | `setLamp` | `false` |
| Door open | `setDoor` | `true` |
| Door close | `setDoor` | `false` |

The button can show RPC execution errors on supported tenant versions. A two-way transport success can carry a device ACK with `ok: false`, so read the ACK body or gateway log to verify `ok` and `actualState`. If the built-in RPC Button is unavailable, use the tenant's two-way RPC tool or `POST /api/rpc/twoway/{deviceEntityId}` with the same method and boolean `params`. A change in reported state comes from fresh telemetry. The shared fields represent the firmware's state unless the kit has independent feedback. [CoreIOT widget library](https://coreiot.io/docs/widgets-library/) · [RPC Button settings](https://thingsboard.io/iot-hub/widgets/rpc-button/) · [Two-way RPC](https://thingsboard.io/docs/pe/user-guide/command-and-control/)

## Dashboard acceptance with simulated telemetry

1. Open the dashboard before connecting the simulator. Verify missing readings are blank or unknown. Start the simulator and compare the latest fields and timestamps with the device's **Latest telemetry** tab. Check that activity and firmware version are visible and the temperature, humidity, and light charts advance.
2. With automatic commands inactive, use each of the six buttons. Check that the simulator logs a correlated ACK with `ok: true` and the requested `actualState`. Check that fresh telemetry updates the displayed value and time-stamped actuator history.
3. Stop the simulator and issue one command. Record the offline/timeout result and verify that the latest sample time stops advancing and no fresh reading appears after 30 seconds. Observe the platform activity indicator after the tenant inactivity period. Restart and check that telemetry resumes with fresh timestamps and the timed-out command is absent from the new session.
4. Save evidence with the tenant version, device name, MQTT/RPC logs with timestamps, and dashboard screenshots. Label simulator evidence synthetic. Export the dashboard from the tenant after successful verification for a version-specific backup.

[CoreIOT dashboard overview](https://coreiot.io/docs/tong-quan-ve-dashboard/) · [Dashboard export](https://thingsboard.io/docs/user-guide/dashboards/#export-and-import-dashboard)

Run `node --test tests/coreiot/dashboard.test.cjs` from the repository root to check template placeholders, layout, telemetry bindings, formatting, and the exact RPC configuration. Use the sandbox checks above to verify dashboard import and runtime behavior on the tenant.
