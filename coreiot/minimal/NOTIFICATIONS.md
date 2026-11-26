# T13 · High-humidity notifications

The [humidity RuleChain](smart-classroom-humidity.rulechain.json) owns the `Classroom High Humidity` alarm at `MAJOR` severity. Set `classroomHumidityMeasurement` to `relative_air_humidity` after confirming that the sensor measures air relative humidity. Fresh, numeric readings of at least 80% RH open or update the active alarm. Readings above 75% and below 80% preserve it, and fresh readings of 75% RH or lower clear it. Use the demonstration thresholds in [server attributes](server-attributes.example.json). The alarm also works with LED automation off or in manual override. [Create Alarm node](https://thingsboard.io/docs/reference/rule-engine/nodes/action/create-alarm/) · [Clear Alarm node](https://thingsboard.io/docs/reference/rule-engine/nodes/action/clear-alarm/)

## Configure in the course tenant

1. Attach the RuleChain to the sandbox telemetry path as described in the [platform deployment guide](../docs/PLATFORM_DEPLOYMENT.md). In the sandbox device's **Alarms** tab, verify that the chain creates the exact alarm type. Use this chain as the sole producer for this alarm type.
2. In **Notification center → Recipients → Add recipients**, create `Smart Classroom Demo Recipient` with type **Platform users** and filter **User list**. Select one approved CoreIOT user and ask them to confirm that Web notifications are enabled for their account.
3. In **Templates → Add template**, use name `Smart Classroom - High Humidity`, type **Alarm** and delivery method **Web**. In the **Compose** step, copy the subject and message body from [the JSON template](high-humidity.notification-template.json). [Alarm template parameters](https://thingsboard.io/docs/reference/notification-system/template-parameters/#alarm)
4. In **Rules → Add rule**, use name `Smart Classroom - High Humidity Created`, trigger **Alarm**, and the template from step 3. Under **Recipients**, select the recipient from step 2 in a single immediate stage with zero delay. In **Alarm trigger settings**, set **Alarm type list** to `Classroom High Humidity`, **Alarm severity list** to **Major**, and **Notify on** to **Alarm created** only.
5. Check existing rules for overlap with this originator, recipient and channel. A catch-all `New alarm` rule can deliver a second message to the same user. Choose an approved test account outside that audience or have the tenant owner resolve the overlap in the sandbox. Enable the demo rule once matching is confirmed. Repeated high readings update the same active alarm and do not trigger another creation notification. A new alarm after recovery produces a new notification. [Notification Center](https://thingsboard.io/docs/pe/user-guide/notifications/) · [Alarm triggers](https://thingsboard.io/docs/pe/reference/notification-system/rule-triggers/#alarm)

Web delivery can be verified in the recipient's CoreIOT inbox. If using email, configure an approved account and the tenant's email provider, then verify the message in that mailbox. Tenant administrator access may be required. [Notification delivery channels](https://thingsboard.io/docs/pe/user-guide/notifications/)

## REST configuration assets

The public CoreIOT `4.2.0PE` OpenAPI lists the following administrator endpoints. The bodies are repository templates that can be submitted through the course tenant's authenticated Swagger or REST client after verifying its version and substituting the tenant UUIDs. Use these in place of the corresponding UI creation steps. If an entity with the same name already exists, inspect it and reuse its UUID. Include its existing top-level `id` object only if intentionally updating it.

| Order | Request | Body | Tenant values |
| --- | --- | --- | --- |
| 1 | `POST /api/notification/target` | [Recipient](high-humidity.notification-target.json) | Set `${demoUserId}` to the approved user's UUID. Record the response's `id.id` as the target UUID. |
| 2 | `POST /api/notification/template` | [Web alarm template](high-humidity.notification-template.json) | Record the response's `id.id` as the template UUID. |
| 3 | `POST /api/notification/rule` | [Alarm creation rule](high-humidity.notification-rule.json) | Substitute `${notificationTemplateId}` and `${notificationTargetId}` with the returned UUIDs. The rule is saved disabled. |

Selecting the correct tenant user, checking default rules, enabling the demo rule and checking the recipient's inbox require signed-in platform access. The public schema and repository checks cannot establish notification receipt. [CoreIOT Swagger UI](https://app.coreiot.io/swagger-ui/index.html) · [CoreIOT OpenAPI](https://app.coreiot.io/v3/api-docs) · [v4.2 escalation form](https://github.com/thingsboard/thingsboard/blob/v4.2/ui-ngx/src/app/modules/home/pages/notification/rule/escalations.component.ts)

## Verify receipt and recovery

Run on `classroom-01-sim` with fresh timestamps, the relative-humidity measurement configured, and LED automation off. Start with 75% RH if a previous test left an alarm active. Record the recipient inbox count before the sequence. Wait for each reading to reach CoreIOT before sending the next one.

Use the simulator commands in the [deployment scenarios](../docs/PLATFORM_DEPLOYMENT.md). Keep every rehearsal on the sandbox entity and label its evidence synthetic. For an additional platform timestamp validation, stop the simulator before sending any test payloads with the sandbox device's MQTT test client. Publish a 70% sample more than 30 seconds old and a fresh sample with a nonnumeric value. Include the sandbox `deviceId` and source Unix millisecond timestamps. [CoreIOT device telemetry setup](https://coreiot.io/docs/ket-noi-va-gui-du-lieu/) · [Timestamped payload format](https://thingsboard.io/docs/reference/mqtt-api/telemetry/)

```powershell
& .venv/coreiot/Scripts/python.exe -m coreiot.simulator --env-file coreiot/.env --minimal --humidity 80
```

| Sample | Expected alarm | Expected new inbox items |
| --- | --- | --- |
| 79% | No active alarm | 0 |
| 80% | Open `MAJOR`, save its alarm ID | 1 |
| 85%, then 77% | Same alarm ID stays active | 0 |
| Stale 70%, missing or invalid humidity | Same alarm ID stays active | 0 |
| 75% | Original alarm becomes cleared | 0 |
| 80% | New alarm ID opens | 1 |
| 75% | Final alarm clears | 0 |

Capture the alarm IDs and states, tenant version, UTC alarm creation and delivery times, and both messages from the approved recipient's inbox. For Web delivery, open the bell menu in the recipient's account and check **Inbox → All**. Use **Notification center → Sent** to diagnose delivery failure. The alarm and **Sent** records establish platform processing. Only the recipient inbox establishes delivery. Tenant delivery is pending until the approved recipient verifies receipt. [Inbox and Sent](https://thingsboard.io/docs/pe/user-guide/notifications/)
