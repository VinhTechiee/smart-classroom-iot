# Classroom RuleChain and notifications

The JavaScript files are rule node bodies for a sandbox CoreIOT tenant, with the `Smart Classroom` profile and simulated `classroom-01-sim` device. Automation starts in dry run. Review the thresholds, light sensor polarity and placement, PIR hold behavior, and manual override with Members A and B before enabling physical automation.

| Decision | Turn on or open | Turn off or clear | Staging gate |
| --- | --- | --- | --- |
| Lamp | `motion = true` and `light < 250` raw | `motion = false` or `light >= 350` raw | Explicit automation enable and explicit override release |
| `Classroom High Temperature` | `temperature >= 35` °C | `temperature <= 33` °C | Fresh valid temperature |
| `Classroom Door Proximity` | `door = true` and `distance <= 15` cm | `door = false` or `distance >= 25` cm | Explicit sandbox proximity opt-in with valid `door` and `distance` |

Set both sandbox lamp thresholds using [sandbox-settings.json](sandbox-settings.json). The gap between thresholds keeps the reported state or existing alarm status. For the lamp, a valid inactive sample can turn it off even if it is dark. Keep actual PIR retention and the lamp's effect on the light sensor in mind when approving the physical thresholds. Lamp changes require valid input fields and a reported Boolean actuator state that differs from the desired state. The proximity rule uses the reported door state and a distance reading as a staging event definition. Any physical proximity alert depends on the sensor facing the door and the team approving what the readings mean. This sandbox chain never moves the door. Use the deployed humidity RuleChain for the physical classroom. [Shared protocol](../../shared/PROTOCOL.md)

## Add the sandbox chain

Generate a detached ThingsBoard-format import from the checked-in scripts using Node.js.

```powershell
New-Item -ItemType Directory -Force build/coreiot-demo | Out-Null
node coreiot/rules/export-sandbox-chain.cjs build/coreiot-demo/smart-classroom-sandbox.rulechain.json
```

Use **Rule chains → Add rule chain → Import rule chain** in the sandbox. The export includes the alarm classifiers and a log-only automation branch. It requires the sandbox attributes and scoped routing below. If importing, follow steps 2, 4 and 5. Use the wiring table in step 3 to insert the automation buffer before testing RPC. If the tenant rejects the import or the node configuration differs, use the manual setup. [ThingsBoard rule chain import](https://thingsboard.io/docs/user-guide/rule-engine/#import-a-rule-chain) · [Upstream rule chain template](https://github.com/thingsboard/thingsboard/blob/master/application/src/main/data/json/tenant/device_profile/rule_chain_template.json)

1. For manual setup, create `Smart Classroom Sandbox` in **Rule chains**. Keep the current Root Rule Chain and the existing profile routing.
2. On the sandbox device's **Attributes → Server attributes** tab, create Boolean `classroomAutomationEnabled = false`, `classroomManualOverride = true`, and `classroomDoorProximityAlertEnabled = false`. Create String `classroomRuleSettings` and paste the JSON object from [sandbox-settings.json](sandbox-settings.json) as its value. Missing settings or invalid threshold pairs suppress the corresponding actuator rule.
3. Wire the new chain using the table. Choose **JavaScript** when adding the script bodies. Use distinct names for nodes with the same type so their logs are easy to follow.

| Starting node | Relation | Destination and configuration |
| --- | --- | --- |
| Input | | **Originator attributes** named Latest sample, latest telemetry key `temperature`, **Fetch latest telemetry with timestamp** enabled |
| Latest sample | `Success` | **Script filter** named Fresh telemetry with [fresh-telemetry.js](fresh-telemetry.js) |
| Fresh telemetry | `True` | **Switch** with [temperature-alert.js](temperature-alert.js) |
| Temperature switch | `High` | **Create alarm**, type `Classroom High Temperature`, severity `MAJOR`, node-configured alarm data, propagation disabled |
| Temperature switch | `Recovered` | **Clear alarm**, same type |
| Fresh telemetry | `True` | **Originator attributes** named Proximity attributes, server key `classroomDoorProximityAlertEnabled` |
| Proximity attributes | `Success` | **Switch** with [door-proximity-alert.js](door-proximity-alert.js) |
| Door proximity switch | `Near` | **Create alarm**, type `Classroom Door Proximity`, severity `WARNING`, node-configured alarm data, propagation disabled |
| Door proximity switch | `Recovered` | **Clear alarm**, same type |
| Fresh telemetry | `True` | **Deduplication**, strategy `LAST`, interval 12 seconds, maximum pending messages 32 per originator. Set retries to 0 where the UI supports this. This branch applies to automation. |
| Deduplication | `Success` | **Originator attributes** named Automation attributes, server keys `classroomAutomationEnabled`, `classroomManualOverride`, `classroomRuleSettings`, latest telemetry key `temperature`, **Fetch latest telemetry with timestamp** enabled |
| Automation attributes | `Success` | **Script filter** named Fresh after lookup with [fresh-telemetry.js](fresh-telemetry.js) |
| Fresh after lookup | `True` | **Transformation script** with [automation.js](automation.js) |
| Transformation script | `Success` | **Script filter** with [automation-request-filter.js](automation-request-filter.js) |
| Request filter | `True` | **Log** with `return JSON.stringify(msg);` for dry runs |

Configure all three attribute nodes to add values to metadata. Enable **Tell failure if attribute or telemetry are missing** on Latest sample and Automation attributes, and leave it off on Proximity attributes. Disconnect the `Ignore` and `False` relations. Use `return {temperature: msg.temperature};` for the temperature alarm details and `return {door: msg.door, distance: msg.distance};` for the proximity alarm details. Check the `Created`, `Updated`, and `Cleared` events in node debug during staging. The import uses a direct link from Fresh telemetry to Automation attributes. Insert the Deduplication node on that link for the full flow. When Deduplication is unavailable, use the direct link for dry-run logging and keep RPC disconnected until the tenant has a verified rate limiter. [Originator attributes](https://thingsboard.io/docs/reference/rule-engine/nodes/enrichment/originator-attributes/) · [Deduplication](https://thingsboard.io/docs/reference/rule-engine/nodes/transformation/deduplication/) · [Create alarm](https://thingsboard.io/docs/reference/rule-engine/nodes/action/create-alarm/) · [Clear alarm](https://thingsboard.io/docs/pe/reference/rule-engine/nodes/action/clear-alarm/)

4. Export the current sandbox Root Rule Chain for reference. From the existing **Save time series** node's `Success` output, add a parallel **Script filter** with this body. The save node must persist latest values using the sample timestamp for the alert and automation branches. If you used a different sandbox name, replace both `classroom-01-sim` literals with that name and use the same simulator device ID. Keep the existing storage and manual RPC paths connected.

```js
return msgType === "POST_TELEMETRY_REQUEST" && !!metadata && metadata.deviceName === "classroom-01-sim" &&
    !!msg && msg.deviceId === "classroom-01-sim";
```

5. Connect that filter's `True` output to a **Rule chain** node targeting `Smart Classroom Sandbox` and save both chains. Open **Latest telemetry** and confirm the simulator still updates it. Inspect debug events to confirm the tenant supplies `metadata.ts` from the time-series envelope and the server attributes arrive with the `ss_` prefix as strings. In output from **Latest sample** and **Automation attributes**, `metadata.temperature` should contain a JSON string with the latest stored `ts` and `value`. The freshness filters discard samples over 30 seconds old, over five seconds in the future, or superseded in storage. If the tenant cannot supply the latest timestamp, record the alert and automation checks as pending and keep automatic RPC disconnected. [CoreIOT Rule Engine](https://coreiot.io/docs/gioi-thieu-rule-engine-2/) · [Rule chain configuration](https://thingsboard.io/docs/user-guide/rule-engine/#configuration)

### Run sandbox automation

With the simulator attached and the request filter wired to **Log**, set `classroomAutomationEnabled = true` and `classroomManualOverride = false`. Vary the input and wait at least one buffer interval for each case. Use the sequence below as starting values for the synthetic readings and reported states.

| Simulation input | Expected candidate |
| --- | --- |
| `motion=true`, `light=100`, `lamp=false`, `temperature=31` | `setLamp` with `params:true` |
| `motion=false`, `light=100`, `lamp=true`, `temperature=27` | `setLamp` with `params:false` |
| `motion=true`, `light=400`, `lamp=true` | `setLamp` with `params:false` |
| `motion=true`, `light=300`, `temperature=29` | Hold reported states |
| Repeat the turn-on case with `classroomManualOverride=true` | No candidate until explicit release |

For an RPC smoke test with the simulator, first verify the buffer coalesces several telemetry samples into one evaluation. Connect the request filter's `True` relation to **RPC call request** with a ten-second timeout and retain the **Log** branch. Connect `Success` to a **Script filter** using [rpc-ack-filter.js](rpc-ack-filter.js). Record matching ACKs, application rejections and RPC timeouts. A successful ACK contains a command ID, `ok:true`, and the requested Boolean as `actualState`. Verify the resulting state separately in telemetry. Automation creates two-way, non-persistent RPCs with retries disabled. Exercise one actuator at a time when collecting latency evidence. [RPC call request node](https://thingsboard.io/docs/reference/rule-engine/nodes/action/rpc-call-request/)

The alert and automation branches require the candidate timestamp to match the latest stored `temperature` timestamp, so an older report arriving late cannot supersede a newer stored sample. The 12-second automation buffer groups telemetry by originator and emits the latest arrival before evaluating rules. It limits repeat candidates during a ten-second RPC window. After buffering, a second lookup and freshness check verify the current sample and override. RPC replies end at the ACK filter and logs. Later telemetry with the desired state suppresses another command. An offline classroom stops submitting fresh telemetry, and an RPC already dispatched can time out without changing the dashboard's reported state. A later fresh sample can start a new evaluation. The buffer provides rate limiting, with application-time override and command correlation handled separately at integration.

Restore `classroomAutomationEnabled = false` before connecting any other client. For rollback, remove the sandbox RPC connection and detach the added branch from the tenant's existing telemetry path.

### Configure recipient notifications

Check which channels the course tenant exposes before configuring alerts. For **Web** delivery, open **Notification center** and create a recipient target for a project test account. For each alarm, create an **Alarm** template with subject `${alarmType}` and its message from the table. Create one Alarm-triggered rule scoped to the matching type and severity, choose **Alarm created** as the only event, and select one immediate recipient stage. In the sandbox, use a recipient who is outside any broad default alarm rule, or use the existing rule as the sole delivery path for that recipient. Repeated trigger samples update the active alarm for the same originator and type. Those updates do not generate another creation notification. [Notification center](https://thingsboard.io/docs/user-guide/notifications/) · [Alarm rule triggers](https://thingsboard.io/docs/reference/notification-system/rule-triggers/) · [Alarm template parameters](https://thingsboard.io/docs/reference/notification-system/template-parameters/#alarm)

| Alarm type | Severity | Notification message |
| --- | --- | --- |
| `Classroom High Temperature` | `MAJOR` | `${alarmOriginatorName} reported excessive classroom temperature.` |
| `Classroom Door Proximity` | `WARNING` | `${alarmOriginatorName} reported a nearby object while the door was open.` |

With automation disabled, publish each value in sequence as fresh telemetry for the same sandbox device. Stop the previous simulator instance before restarting with changed readings and the same test credential. Set `classroomDoorProximityAlertEnabled = true` only for the proximity sequence and return the sandbox alarm to a recovered reading before removing the opt-in.

| Alarm | Create, repeat, hold, clear and recreate inputs | Expected evidence |
| --- | --- | --- |
| Temperature | `35`, `36`, `34`, `33`, `35` °C | First creation and receipt, same alarm ID on repeat, hold at `34`, clear at `33`, then a new alarm ID and receipt |
| Door proximity | Door open at `15`, `10`, `20`, `25`, then `15` cm. Also check door closed at `10` cm clears an active alarm. | First creation and receipt, same alarm ID on repeat, hold at `20`, clear at `25`, then a new alarm ID and receipt |

Before each sequence, establish a recovered reading so the first trigger creates a new alarm. For Web delivery, sign in as the test recipient, open the notification inbox or bell, and record the received message and time alongside the alarm ID. Repeat and hold samples should add no inbox entry. For another channel approved by the course tenant, capture equivalent evidence from its receiving endpoint. Local checks exercise classification. Notification receipt remains pending a tenant and recipient test.

## Override proposal for team review

`classroomAutomationEnabled` and `classroomManualOverride` are staging server attributes. A and B need an agreed way to report local manual actions and release events before the project uses cloud automation on physical actuators. The current boolean RPC payload contains no indication of command intent, and both dashboard and automatic cloud commands would reach the current local contract with `source: "coreiot"`.

Proposed policy is that accepting a manual lamp action from firmware, gateway UI, or cloud begins an indefinite per-classroom manual override. Only an explicit release ends it. The component that applies actuator changes must enforce the override at application time. Agree on authenticated signalling for manual and automatic intent and a monotonic override revision, so a queued automatic command from before a manual action or release can be rejected. Agree how A's local web UI and B's gateway synchronize override transitions with C, and how to fail closed if that state is unknown after reconnect. The current staging flags prevent creating new commands while the override is active. An already-issued RPC can still arrive. Leave physical automation off until the team agrees and validates the application-time policy. [Shared protocol](../../shared/PROTOCOL.md)

## Local verification

```powershell
node --test tests/coreiot/rules.test.js
```

The test runner evaluates the script bodies with representative Rule Engine inputs. It covers disabled and overridden automation, telemetry freshness and arrival order, motion and temperature thresholds, hysteresis, malformed values and settings, command and ACK shape, both alert classifiers, and the detached import graph. Import and execution on CoreIOT, buffer timing, RPC delivery, alarm lifecycle, and notification receipt require the sandbox checks above.
