# Interface Contract (Draft v0.1)

Agree on this contract before implementation. Changes require review by all module owners.

Local MQTT broker: PC gateway host, port 1883 on an isolated development network. Use configurable host and credentials. CoreIOT topics and authentication are configured separately by members B and C.

| Topic | Direction | Purpose |
| --- | --- | --- |
| `classroom/{deviceId}/telemetry` | Device to gateway | Measurements and reported actuator state |
| `classroom/{deviceId}/cmd` | Gateway to device | Control requests |
| `classroom/{deviceId}/ack` | Device to gateway | Command execution result |

Suggested QoS 1, non-retained commands; deduplicate by command ID. Telemetry timestamps are Unix milliseconds when synchronized; otherwise use null and record gateway receipt time. Light is a raw reading until calibrated; distance is cm, temperature is Celsius, humidity is percent. Door true means open; lamp true means on. Reported state represents firmware state unless independent physical feedback is available.

### Telemetry example (synthetic)

```json
{"deviceId":"classroom-01","ts":null,"temperature":28.5,"humidity":65.0,"light":850,"motion":true,"distance":12.5,"lamp":false,"door":true,"fwVersion":"1.0.0","mockMode":false}
```

### Command example

```json
{"id":"cmd-001","method":"setLamp","value":true,"source":"coreiot","expiresAt":1760000003500}
```

### Acknowledgement example

```json
{"id":"cmd-001","ok":true,"actualState":true,"ts":null}
```

Allowed cloud methods are Boolean `setLamp` and `setDoor`. The gateway UI also uses local-only Boolean `setDoorAuto`. For this method, ACK `actualState` is the resulting mode and optional local telemetry `doorAuto` reports it. Reject unsupported methods and invalid values. On failure include `error` and use null for unknown state. Publish fresh telemetry after applying commands. Gateway correlates ACKs with CoreIOT RPC requests and handles timeouts.

The default LED owner is the CoreIOT humidity RuleChain. A separately calibrated local light/PIR build rejects cloud LED commands. Manual door open/close disables local distance automation until explicitly restored or the board reboots. The CoreIOT LED manual override uses the server-side procedure.

### Proposed integration changes for member review

- The physical builds require an integer `expiresAt` in Unix milliseconds on local commands. The PC generates a 3.5-second deadline, the board requires a synchronized clock and rejects deadlines more than five seconds ahead. Repeated IDs replay the cached ACK within the deadline. Commands use QoS 1 and the demo broker disables retained messages. Firmware ACK and telemetry publications use QoS 0 with the current library.
- Firmware sends `ts:null` for classroom telemetry and ACKs. The bridge stamps unsynchronized telemetry on receipt and rejects supplied timestamps older than 30 seconds or more than 5 seconds ahead. Unsupported values use null locally and are omitted when forwarding. Physical routes require `mockMode:false`.
- Distinguish automatic intent from manual commands and propagate local override changes before enabling physical automation. The integration currently leaves physical automatic RPC disabled and uses the server-side override procedure for sandbox tests.
