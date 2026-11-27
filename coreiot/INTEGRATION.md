# Gateway integration and acceptance

For current hardware, the [physical commissioning checklist](docs/PLATFORM_DEPLOYMENT.md#12-switch-to-the-real-gateway-and-sensor) specifies the proposed telemetry subset and LED acceptance check. Keep the per-device topic mapping below. Agree on omitted sensor and actuator fields with A and B before physical commissioning. The extended examples below cover the original kit.

## Cloud MQTT mapping for Member B

The PC gateway uses one MQTT Device API session per CoreIOT classroom entity for the project sandbox. The access token is the MQTT username and identifies that classroom. Bind it to the matching local `deviceId` in gateway configuration. Use the tenant-provided host and port, with certificate validation when TLS is available. Keep the local broker on the isolated development network. The cloud binding is based on the Core IoT connection guide and the upstream MQTT Device API. [Core IoT connection guide](https://coreiot.io/docs/ket-noi-va-gui-du-lieu/) · [ThingsBoard MQTT connection](https://thingsboard.io/docs/reference/mqtt-api/getting-connected/)

| Direction | MQTT topic | Mapping |
| --- | --- | --- |
| Device → PC gateway | `classroom/{deviceId}/telemetry` | Read the shared telemetry JSON and record when the gateway received it. |
| PC gateway → CoreIOT | `v1/devices/me/telemetry` | Publish a `{ "ts": <timestamp>, "values": { ... } }` envelope using the classroom session. |
| CoreIOT → PC gateway | `v1/devices/me/rpc/request/+` | Read the request ID from the topic and map a valid `method` and boolean `params` to the shared command. |
| PC gateway → device | `classroom/{deviceId}/cmd` | Publish `{ "id": "<local-command-id>", "method": "setLamp", "value": true, "source": "coreiot" }` for a lamp-on example. |
| Device → PC gateway | `classroom/{deviceId}/ack` | Match `deviceId` and `id` to a pending cloud request. |
| PC gateway → CoreIOT | `v1/devices/me/rpc/response/{requestId}` | Return the matched application ACK as JSON on the same session, using the cloud request ID in the topic. |

Publish at QoS 1 with retain off. Subscribe to RPC after each cloud reconnect and keep the response on that device session. The dashboard uses two-way, non-persistent requests. [ThingsBoard telemetry API](https://thingsboard.io/docs/reference/mqtt-api/telemetry/) · [ThingsBoard RPC API](https://thingsboard.io/docs/reference/mqtt-api/rpc/)

### Telemetry

For the current kit, forward `deviceId`, `fwVersion`, measured `humidity`, measured `temperature` when supported, and `lamp` when reported. The extended example includes the full set of hardware values. Use the device timestamp for the cloud envelope when it has synchronized Unix milliseconds and retain it as a numeric `values.ts`. When the shared `ts` is null, record gateway receipt time in the envelope and omit the null from `values` for cloud compatibility. The shared record retains `ts: null`. The JSON keys in `values` become CoreIOT telemetry keys, with the envelope timestamp attached to each reading. [ThingsBoard timestamped telemetry](https://thingsboard.io/docs/reference/mqtt-api/telemetry/) · [Upstream null handling report](https://github.com/thingsboard/thingsboard/issues/13614)

```json
{
  "ts": 1780000000000,
  "values": {
    "deviceId": "classroom-01",
    "ts": 1780000000000,
    "temperature": 28.5,
    "humidity": 65,
    "light": 320,
    "motion": true,
    "distance": 42,
    "lamp": false,
    "door": false,
    "fwVersion": "1.0.0"
  }
}
```

Temperature is in °C, humidity is percent, light is raw, and distance is in cm. A true `lamp` means on, and a true `door` means open. These are reported firmware states. The dashboard displays them from telemetry. `fwVersion` is the firmware version reported by YoloUNO.

### RPC and acknowledgements

The gateway copies the CoreIOT RPC `method` into the local MQTT `method` and the JSON boolean `params` into the local `value`. For a CoreIOT request, it sets `source` to `coreiot`. Forward only the methods and values in this table.

| CoreIOT and local `method` | `params` → `value` | Device ACK `actualState` when applied | Telemetry key |
| --- | --- | --- | --- |
| `setLamp` | `true` on, `false` off | `true` on, `false` off | `lamp` |
| `setDoor` | `true` open, `false` closed | `true` open, `false` closed | `door` |

Allocate a unique local command ID for each new request. Keep the pending mapping from the classroom, active cloud session and cloud request ID to the local command and deadline. Match an incoming ACK using the classroom ID in the local ACK topic and the command `id` in its payload. Return the ACK body on the CoreIOT response topic with the original cloud request ID. Only commands with a live CoreIOT mapping produce a cloud RPC response. Local actions still reach CoreIOT through ordinary telemetry.

For example, closing the door in `classroom-01` can produce this exchange.

| Step | MQTT topic | Example payload |
| --- | --- | --- |
| CoreIOT sends RPC | `v1/devices/me/rpc/request/42` | `{"method":"setDoor","params":false}` |
| Gateway sends local command | `classroom/classroom-01/cmd` | `{"id":"cmd-001","method":"setDoor","value":false,"source":"coreiot","expiresAt":1760000003500}` |
| Device acknowledges | `classroom/classroom-01/ack` | `{"id":"cmd-001","ok":true,"actualState":false,"ts":null}` |
| Gateway completes RPC | `v1/devices/me/rpc/response/42` | `{"id":"cmd-001","ok":true,"actualState":false,"ts":null}` |
| Device reports fresh state | `classroom/classroom-01/telemetry` | Full shared telemetry with `"door":false` |
| Gateway forwards reported state | `v1/devices/me/telemetry` | Full timestamped envelope with `"door":false` in `values` |

The ACK confirms the application result for one command. Check that `ok` is `true` and `actualState` matches the requested boolean. The dashboard reads `lamp` and `door` from the latest reported telemetry, including updates from local control.

Reject unsupported methods or values other than JSON booleans before publishing a local command. Forward device failures with `ok:false`, an `error`, and `actualState:null` when the state is unknown. Set the gateway ACK deadline below the CoreIOT RPC timeout so the gateway can report a missing ACK with `ok:false`, an `error`, and `actualState:null` while the cloud request is still open. Deduplicate by CoreIOT request ID within the active classroom session and reuse the existing result or pending mapping. The MQTT `DUP` flag can appear on the first receipt. Ignore unmatched, expired, or duplicate completed ACKs when routing cloud responses, remove timed-out mappings, and avoid replaying stale commands after reconnecting.

The [Python simulator](simulator/README.md) exercises this mapping with a synthetic local device and a real cloud-side MQTT client. It caps the pending requests and cached responses, routes ACKs by the originating classroom and unique command ID, and starts a new request scope on reconnect. Its default local ACK deadline is 3.5 seconds, within the dashboard's 10-second RPC timeout. It can exercise a missing device, a device that accepts no commands, a missing ACK after execution, and an ACK that arrives after timeout. A timeout can still be followed by a real state change if the device executes a command that already reached it. Check latest telemetry and the actuator before retrying in hardware.

Before the hardware test, B must verify these behaviors in the production gateway on its per-classroom sessions. The simulator's local transport is in-process and publishes only on the cloud MQTT connection. Use the [physical integration checklist](docs/DEMO.md#handoff-checklist) to capture broker and hardware traces.

### Team decisions before hardware automation and OTA

- Agree the thresholds, server attributes, manual action signaling and priority rules in the [humidity automation guide](minimal/AUTOMATION.md). Both dashboard and local manual actions need to set the override before a conflicting automatic command can apply. Local execution must honor an override even if a prior automatic command is already in flight. The existing shared command has one CoreIOT source value for both manual and automatic requests, so the team needs to approve the execution policy before enabling hardware automation.
- Agree how CoreIOT package data reaches the OTA client. The dashboard MQTT binding represents the gateway session for normal operation. Choose and validate the firmware download path with Members A and B, then exercise the lab rollout in the [OTA handoff](platform/OTA.md).

## Acceptance checks

Follow the [platform deployment sequence](docs/PLATFORM_DEPLOYMENT.md) for the current kit and the [evidence record](docs/VERIFICATION.md) for measurements. This table also covers the original extended kit.

| Requirement | Procedure | Evidence to capture |
| --- | --- | --- |
| T11 monitoring | Start the simulator and confirm all measurement and actuator keys, identity and firmware version on the expected entity. Compare a sample's platform timestamp with the source timestamp and repeat with a null device timestamp. | Latest telemetry, chart screenshot, and source and receive timestamps. |
| T11 control | With automation disabled, send both boolean values for each of the three methods. Check the ACK ID, success and matching `actualState`. Check fresh telemetry after each success. Try an unsupported method or numeric value in the sandbox and confirm failure with state unchanged. Stop the simulator, issue a request and record the timeout. Restart and confirm telemetry and new requests resume. | RPC/ACK logs, dashboard states, negative cases and reconnect trace. |
| T12 automation | With simulator telemetry, leave the enable flag absent or false and verify no automatic RPC. In the sandbox only, enable the chain and test the humidity thresholds in both directions, readings in the hysteresis band and an explicit manual override. On hardware, repeat after approval and test a manual action while an automatic request is in flight. | RuleChain inputs and traces, RPC results, reported state, and the result of each override test. |
| T13 alerts | Send readings below the create threshold, at or above it, between create and clear, and at or below clear. Repeat the high reading while active. Confirm the alarm opens once, stays active in the band, and clears. Check the configured recipient actually receives the test alert. | Alarm lifecycle, notification delivery time, and recipient confirmation with personal data removed. |
| T14 OTA | Verify package assignment and checksum on a virtual lab-profile device first. On the designated lab unit, record the starting version, assign the reviewed package, verify download and update statuses, then check `fwVersion` after reboot and repeat the telemetry and RPC checks. | Package title, version and checksum, status transitions, post-boot `fwVersion`, and recovery result if exercised. |

Label simulator records as synthetic. For hardware integration, record at least ten sensor-to-dashboard trials and ten command-to-ACK trials with sample or command IDs, start and end times, and outcome. Use synchronized clocks or one observation clock, report the minimum, mean and maximum for each successful set, and record timeouts separately. Keep raw logs and screenshots with credentials removed. [Project evidence plan](../docs/DEVELOPMENT.md#evidence)
