# Interface Contract (Draft v0.1)

Agree on this contract before implementation. Changes require review by all module owners.

Local MQTT broker: PC gateway host, port 1883 on an isolated development network. Use configurable host and credentials. CoreIOT topics and authentication are configured separately by members B and C.

| Topic | Direction | Purpose |
| --- | --- | --- |
| `classroom/{deviceId}/telemetry` | Device to gateway | Measurements and reported actuator state |
| `classroom/{deviceId}/cmd` | Gateway to device | Control requests |
| `classroom/{deviceId}/ack` | Device to gateway | Command execution result |

Suggested QoS 1, non-retained commands; deduplicate by command ID. Telemetry timestamps are Unix milliseconds when synchronized; otherwise use null and record gateway receipt time. Light is a raw reading until calibrated; distance is cm, temperature is Celsius, humidity is percent. Door true means open; lamp/fan true means on. Reported state represents firmware state unless independent physical feedback is available.

### Telemetry example (synthetic)

```json
{"deviceId":"classroom-01","ts":null,"temperature":28.5,"humidity":65.0,"light":320,"motion":true,"distance":42.0,"lamp":false,"fan":false,"door":false,"fwVersion":"1.0.0"}
```

### Command example

```json
{"id":"cmd-001","method":"setLamp","value":true,"source":"coreiot"}
```

### Acknowledgement example

```json
{"id":"cmd-001","ok":true,"actualState":true,"ts":null}
```

Allowed methods: `setLamp`, `setFan`, `setDoor`. Reject unsupported methods and invalid values. On failure include `error` and use null for unknown state. Publish fresh telemetry after applying commands. Gateway correlates ACKs with CoreIOT RPC requests and handles timeouts.

Automation policy: CoreIOT RuleChain owns automatic lamp/fan decisions; manual override suppresses automatic commands until explicitly released. C owns remote override policy; A and B must propagate local manual actions and override state. Agree the override message fields and thresholds before automation implementation. Do not run competing automatic rules in multiple layers.
