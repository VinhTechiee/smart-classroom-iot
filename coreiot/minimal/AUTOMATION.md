# Humidity RuleChain

Import [Smart Classroom - Humidity](smart-classroom-humidity.rulechain.json) as a separate chain. It accepts telemetry from `classroom-01-sim` and `classroom-01` when the reported `deviceId` matches the CoreIOT device name. To use different names, edit the **Classroom humidity only** filter in [the export source](export-humidity-chain.cjs), regenerate the JSON and use the same device names in CoreIOT and each publisher. The 80% RH and 75% RH defaults are demonstration values.

Follow the [platform deployment guide](../docs/PLATFORM_DEPLOYMENT.md) for the deployment sequence and runnable simulator scenarios. Use this reference to check the imported graph and diagnose rule execution.

| Fresh relative humidity | Alarm | Automatic LED candidate |
| --- | --- | --- |
| At or above the high threshold | Open or update `Classroom High Humidity` with `MAJOR` severity | ON when reported `lamp` is `false` |
| Between the thresholds | Keep existing status | Hold reported `lamp` |
| At or below the recovery threshold | Clear the active alarm | OFF when reported `lamp` is `true` |

## Server attributes

Apply [the example server attributes](server-attributes.example.json) on `classroom-01-sim` under **Attributes → Server attributes**. Enter the values with these types.

| Key | Type | Initial value |
| --- | --- | --- |
| `classroomHumidityMeasurement` | String | `relative_air_humidity` for the simulator and a confirmed physical % RH sensor |
| `classroomHumidityHigh` | Number | `80` |
| `classroomHumidityRecovery` | Number | `75` |
| `classroomAutomationEnabled` | Boolean | `false` |
| `classroomManualOverride` | Boolean | `true` |

Configure thresholds together in the range 0–100, with recovery strictly below high. If both are absent, the defaults apply. A partial, malformed or inverted pair suspends both rule decisions. CoreIOT manages the Boolean `active` attribute. The chain manages the String `classroomLastLedAttempt`, which starts absent and stores the sample and request timestamps. For a soil-moisture sensor, agree on a separate calibrated reading, unit, telemetry key and thresholds before configuring its rules.

## Imported graph and trace

1. Verify the new **Rule chain** node follows **Save time series → Success** on the existing telemetry route and that the existing Root RuleChain, device profile routing and storage still operate. The storage node must write the latest values using the MQTT sample timestamp. Check for the expected record in **Latest telemetry**. [CoreIOT Rule Engine](https://coreiot.io/docs/gioi-thieu-rule-engine-2/) · [MQTT timestamps](https://thingsboard.io/docs/reference/mqtt-api/telemetry/) · [Save time series](https://thingsboard.io/docs/reference/rule-engine/nodes/action/save-timeseries/)
2. Confirm **Order by device** is a **Checkpoint** on the `SequentialByOriginator` queue and that the queue processes one message per originator at a time. If this queue is unavailable, connect **Classroom humidity only → True → Preserve humidity sample** and disconnect **Order by device**. The fallback supports humidity alarms alongside ordinary telemetry. Keep the automatic RPC input disconnected on the fallback. [Checkpoint](https://thingsboard.io/docs/reference/rule-engine/nodes/flow/checkpoint/) · [Rule Engine queues](https://thingsboard.io/docs/pe/user-guide/rule-engine/queues/)
3. Enable node debug for the sandbox trace. **Preserve humidity sample** moves the original fields into `msg.sample` and retains `metadata.ts` from the envelope. **Latest humidity and controls** fetches its values into **Message** (`DATA`) so CoreIOT preserves Number and Boolean types. Compare `metadata.ts` with `msg.humidity.ts` and the original humidity with `msg.humidity.value`. For automatic LED control, `msg.lamp` must also match the sample timestamp and contain the reported Boolean. Look for server attributes in `msg.ss_*`, including Boolean `msg.ss_active` for an active session. A tenant that stores activity as time series will need a compatible activity source before enabling automatic RPC. Leave the RPC input disconnected if `ss_active` is missing. [Originator attributes](https://thingsboard.io/docs/reference/rule-engine/nodes/enrichment/originator-attributes/) · [Device connectivity status](https://thingsboard.io/docs/user-guide/device-connectivity-status/)
4. Confirm **Save LED attempt** writes the attempt on every message to `SERVER_SCOPE`, with device and attribute update notifications disabled. Save failure routes to **Humidity rule processing failed**. **Recheck humidity and controls** reads fresh attributes and telemetry after the save. The request is skipped if settings, activity, override, the latest sample or the reported LED state changed while the attempt was written. Samples older than 30 seconds, more than 5 seconds in the future, or superseded by a newer latest value are skipped. [Save attributes](https://thingsboard.io/docs/reference/rule-engine/nodes/action/save-attributes/)

The export uses upstream ThingsBoard 4.2 node configurations. Earlier deployment notes recorded the public CoreIOT schema as `4.2.0PE`. Confirm the current tenant version and re-export the imported chain to check that it retained node settings and the sequential queue. If a node needs to be recreated in the UI, copy its configuration and JavaScript from the export. [Public CoreIOT API schema](https://app.coreiot.io/v3/api-docs) · [4.2 typed message enrichment source](https://github.com/thingsboard/thingsboard/blob/v4.2/rule-engine/rule-engine-components/src/main/java/org/thingsboard/rule/engine/metadata/TbAbstractNodeWithFetchTo.java) · [4.2 Originator Attributes source](https://github.com/thingsboard/thingsboard/blob/v4.2/rule-engine/rule-engine-components/src/main/java/org/thingsboard/rule/engine/metadata/TbAbstractGetAttributesNode.java)

In upstream 4.2, the RPC node acknowledges the original queue message when it schedules the request. The response or timeout starts a separate queue message. The queue processing deadline must cover lookup, save, recheck and dispatch. If the default queue times out during those operations, have a system administrator configure a dedicated sandbox queue with **Sequential by originator**, **Skip all failures**, and a 15-second processing timeout. Select it on **Order by device** and test ordering and result delivery with the RPC edge disconnected before enabling it. [4.2 default queue configuration](https://github.com/thingsboard/thingsboard/blob/v4.2/application/src/main/java/org/thingsboard/server/service/install/DefaultSystemDataLoaderService.java) · [4.2 RPC node source](https://github.com/thingsboard/thingsboard/blob/v4.2/rule-engine/rule-engine-components/src/main/java/org/thingsboard/rule/engine/rpc/TbSendRPCRequestNode.java)

## Duplicate suppression and RPC outcomes

The persisted attempt blocks replay of the same or an older sample and limits a mismatched device to one attempt per 12 seconds. The guard is applied during dry runs as well. After confirming ordering, persistence and dry-run candidates on the sandbox device, connect **Valid LED command → True → RPC LED - connect in simulator**, keeping **LED candidate** as a parallel output. The request is non-persistent, two-way `setLamp` with a Boolean parameter, a 10-second deadline and no retries. [RPC call request](https://thingsboard.io/docs/reference/rule-engine/nodes/action/rpc-call-request/)

| Test | Expected evidence |
| --- | --- |
| Valid ON and OFF | `LED ACK accepted` with nonempty command `id`, `ok:true`, and matching Boolean `actualState`. Verify a separate update of `lamp` in telemetry. |
| Local ACK missing | Add `--drop-ack --timeout-ms 1000` to a mismatched sample. Verify `LED ACK rejected` with `ok:false`. Capture the reported state if it changes after application. |
| Cloud RPC timeout | Add `--ack-delay-ms 11000 --timeout-ms 15000` to a mismatched sample. Verify the RPC `Failure` relation and `LED RPC failed or timed out`. Capture any later telemetry after the simulator applies the command. |
| Offline | Stop the simulator and confirm no fresh LED candidates. Verify explicit inactivity also suppresses requests. Any in-flight transport failure ends at the failure log. |
| Recovery | Restart the simulator. After the cooldown, only a newer fresh sample with a current mismatched `lamp` can produce another candidate. |

Record a candidate timestamp, save result, RPC relation, ACK payload or transport error, and fresh reported state for each case. Keep `classroomLastLedAttempt` while evaluating cooldown or replay tests. Wait at least 12 seconds after any dry-run attempt before verifying live RPC on a newer sample.

Set `classroomManualOverride=true` before a manual LED command and release it explicitly when automation can resume. The recheck narrows the interval between reading override and sending the command. An in-flight command can still apply, even after a timeout. Members A and B need to agree on command intent and enforce override and command expiry at execution time before enabling automation on a Yolo UNO. After the simulator test, set automation to `false` and override to `true`, then remove the extra RPC input edge. To roll back the chain attachment, detach the new branch after the Root RuleChain storage node. [Shared protocol](../../shared/PROTOCOL.md)

## Offline verification

Edit [the RuleChain exporter](export-humidity-chain.cjs) to change the chain, then regenerate the JSON used for direct tenant import. The offline suite checks that the import matches the exporter output.

```powershell
node coreiot/minimal/export-humidity-chain.cjs coreiot/minimal/smart-classroom-humidity.rulechain.json
node --test tests/coreiot/minimal-rules.test.cjs
```

The tests execute the exported JavaScript and verify the graph wiring and safe defaults. Tenant checks establish Rule Engine execution, queue behavior, transport errors and ACK delivery. Physical verification also requires the actual sensor, Member A's firmware and Member B's gateway.
