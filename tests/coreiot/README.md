# Member C verification

From the repository root, [install the Python simulator](../../coreiot/README.md#install-and-run-the-python-simulator) and use Node.js 22 or later for the RuleChain and dashboard checks.

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
node --test tests/coreiot/*.test.cjs tests/coreiot/*.test.js
```

The Python suite exercises the same simulator used for tenant integration, including RPC correlation, timeout, duplicate and retained-request handling, reconnect, MQTT loopback, and the tenant smoke runner's telemetry checks. MQTT loopback uses the simulator's pinned `paho-mqtt` package. The JavaScript suites exercise the RuleChain scripts and validate dashboard and device templates with built-in Node modules. Each local suite uses synthetic data.

Use the [deployment guide](../../coreiot/docs/PLATFORM_DEPLOYMENT.md#6-verify-two-way-led-on-and-off) to run the authenticated LED smoke test, the [OTA lab steps](../../coreiot/platform/OTA.md#check-package-delivery-without-hardware) for virtual download verification, and the [verification guide](../../coreiot/docs/VERIFICATION.md) to record physical evidence.
