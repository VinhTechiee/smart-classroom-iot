# Member C demo

Use the [platform deployment guide](PLATFORM_DEPLOYMENT.md) to rehearse first. This sequence assumes a five-minute Member C segment. Keep the physical dashboard open alongside the sensor log, ACK trace, RuleChain debug view, and recipient inbox. Use a separate **Smart Classroom — Synthetic** dashboard for any simulator section.

## Handoff checklist

- A supplies the Yolo UNO board revision, humidity sensor model and unit, current firmware and serial-log procedure, and the board LED mapping. A confirms which readings the board produces and how to test the LED and safe stop.
- B supplies broker and gateway launch steps, configuration and log locations, a per-device CoreIOT mapping, and traces for telemetry, RPC, timeouts and reconnects. B confirms any available AI event key and entity. The current checkout contains scaffolds for both team modules. [Gateway acceptance contract](../INTEGRATION.md)
- C verifies the sandbox and physical aliases, confirms a recipient can open the selected channel, and prepares a fresh low baseline. Keep physical automation disabled until A and B verify override and expiry behavior. Use the synthetic sequence for automation if that gate remains open.
- A, B and C rehearse the physical OTA separately on the lab unit, with a recovery artifact and USB access. Prepare timestamped evidence from the verified update if the live segment is too short. [OTA runbook](../platform/OTA.md)

## Five-minute sequence

| Elapsed | Show | Pass evidence |
| --- | --- | --- |
| 0:00–0:45 | Show the real Yolo UNO and one forwarded RH sample on **Smart Classroom — Physical**. Point out the correct identity, firmware version, cloud activity and recent humidity. | Screenshot with device ID and a fresh timestamp, plus its corresponding local sample. |
| 0:45–1:40 | Set manual override, press **LED ON**, then **LED OFF** once the first action is verified. If the board has no confirmed controllable LED, label this section synthetic and use the sandbox. | Both cloud request IDs, correlated application ACKs, fresh matching `lamp` states, and physical LED observations where supported. |
| 1:40–3:05 | Show the humidity chain branch after storage. Run the rehearsed high, deadband and recovery sequence on the eligible device. Show the existing alarm through high and deadband and the OFF decision after recovery. | Rule execution trace, threshold and override settings, alarm ID and timestamps, plus automatic ACK and fresh state when actuation is enabled. |
| 3:05–3:45 | Open the approved recipient's Web inbox or configured delivery channel. Show the new notification and the alarm's cleared status. | Recipient-side receipt timestamp and alarm ID. Repeat high samples generate one notification per active cycle. |
| 3:45–4:40 | Show the physical lab's before/after OTA record, including boot and reconnect. | `1.0.0` and `1.1.0` serial and cloud evidence, package SHA-256, and successful post-update checks. |
| 4:40–5:00 | Summarize measured latencies using the evidence record. If B has an integrated AI event, show it alongside the real sample in the first segment. | Counts, minimum, mean and maximum, with trial records available. [Measurement templates](VERIFICATION.md#measurement-record) |

## Recover during the demo

If the real sensor stops reporting, pause cloud controls. Disable automation and set manual override on the hardware entity if the UI is reachable. Check board serial and Wi-Fi, local broker, gateway mapping and cloud reconnect, then dashboard alias. After a timeout, observe the LED and read its latest state before deciding whether to send a new command. Resume with one fresh hardware sample and one verified manual command.

If hardware is unavailable, use the synthetic dashboard, the sole Python simulator and the documented scenario commands. If the tenant is also unavailable, show saved evidence from the latest successful rehearsal with its source and date. A pending physical OTA can be reported as pending with the verified delivery stage shown separately. [Simulator scenarios](PLATFORM_DEPLOYMENT.md#10-run-the-synthetic-scenarios)
