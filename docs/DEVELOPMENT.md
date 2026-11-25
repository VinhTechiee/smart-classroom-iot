# Development Plan

| Owner | Deliverables | Report ownership |
| --- | --- | --- |
| A (34%) | Firmware, wiring, sensors and actuators, device web server, OTA client and versioned builds | 2.3.1, 2.6, 3.1–3.3, firmware instructions in Ch. 6 |
| B (33%) | Local MQTT broker setup, gateway bridge, local UI, simulator, AI pipeline, optional N06 | 2.1–2.2, 2.3.2–2.3.4, 3.4–3.5, 3.7 if N06 |
| C (33%) | CoreIOT templates/dashboard, RPC, RuleChain, alerts, OTA package configuration, submission coordination | Ch. 1, 2.3.5, 2.4–2.5, 3.6, Ch. 5 and front matter |

All members contribute their own test data to Chapter 4 and installation instructions to Chapter 6. B coordinates test records; C consolidates the report. Shares are provisional.

## Integration gates

1. Freeze interfaces, pin assignments, control policy and verify required device count and OTA support.
2. A tests on the kit; B tests against a simulated device; C tests against a simulated gateway.
3. Merge reviewed module changes; verify real telemetry, local control, remote RPC and acknowledgements.
4. Verify automation, notifications and AI inference on the integrated system.
5. Perform OTA last, retain a recovery build, rerun regression tests and record evidence.

## Evidence

Record sensor/dashboard and command/ACK latency over at least ten trials, reporting minimum, mean and maximum. Preserve raw logs, AI evaluation on a held-out dataset, reconnect tests, screenshots and OTA version evidence. Never present synthetic data as real hardware measurements.
