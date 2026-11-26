# Smart Classroom IoT

An IoT-based classroom monitoring and automation system developed for the Internet of Things course at HCMUT. The proposed system integrates an ESP32-S3 (YoloUNO), a PC gateway, and CoreIOT for environmental monitoring, actuator control, event classification, and alerts.

## Architecture

```text
Sensors / Actuators <-> YoloUNO <-> Local MQTT Broker <-> PC Gateway <-> CoreIOT
```

## Modules

| Module | Responsibility | Owner |
| --- | --- | --- |
| `firmware/` | Sensors, actuators, device web server, OTA client | A |
| `gateway/` | MQTT bridge, local UI, command routing | B |
| `ai/` | Event classification, training and evaluation | B |
| `coreiot/` | Dashboard, RuleChain, notifications, OTA configuration | C |
| `shared/` | Interface contract and sample messages | All |
| `tests/` | Integration tests and measurement records | All |
| `docs/` | Architecture, wiring and project evidence | All |

## Development

Read [the interface contract](shared/PROTOCOL.md) and [the development plan](docs/DEVELOPMENT.md) before implementing modules. Use individual feature branches and pull requests into `main`. Keep credentials in local configuration files; commit examples only.

## Status

Member C's [CoreIOT deployment guide](coreiot/docs/PLATFORM_DEPLOYMENT.md) covers the current Yolo UNO kit, humidity monitoring, board LED RPC, notifications, OTA and the Python simulator. The [extended configuration](coreiot/README.md#extended-hardware-configuration) is available for a future kit. Course tenant configuration and end-to-end hardware verification are pending.
