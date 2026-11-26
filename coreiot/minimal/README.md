# Minimal CoreIOT assets

Start with the [platform deployment guide](../docs/PLATFORM_DEPLOYMENT.md). It uses the existing `Smart Classroom` device profile and `classroom-01-sim`.

| Task | Assets and reference |
| --- | --- |
| T11 Dashboard and LED | [Humidity dashboard](smart-classroom-humidity.dashboard.json), [temperature variant](smart-classroom-temp-humidity.dashboard.json), and [binding details](DASHBOARD.md) |
| T12 Automation and alarm | [Detached RuleChain](smart-classroom-humidity.rulechain.json), [export source](export-humidity-chain.cjs), [initial server attributes](server-attributes.example.json), and [node setup](AUTOMATION.md) |
| T13 Delivery | [Recipient, template, rule and verification](NOTIFICATIONS.md) |
| T14 OTA | [Package download, physical acceptance and recovery](../platform/OTA.md) |
| T15 Optional gateway lab | [Design and verification dependencies](GATEWAY.md) |

The [device profile](smart-classroom.device-profile.json) and [device](smart-classroom.device.json) REST templates are for a new minimal sandbox. The [extended assets](../platform/README.md) cover the original kit.

OhStem lists a D13 LED and an RGB NeoPixel on Yolo UNO. A confirms the actual board revision, firmware mapping, and its reported `lamp` state. A also confirms air relative humidity and whether the sensor supplies temperature. [OhStem Yolo UNO specifications](https://ohstem.vn/san-pham/yolo-uno/)
