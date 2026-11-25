# Member C verification

From the repository root, [install the Python simulator](../../coreiot/README.md#install-and-run-the-python-simulator) and use Node.js 22 or later for the RuleChain and dashboard checks.

```powershell
& .venv/coreiot/Scripts/python.exe -m unittest discover -s tests/coreiot -p 'test_*.py' -v
node --test tests/coreiot/dashboard.test.cjs tests/coreiot/rules.test.js
```

The Python suite covers RPC correlation, timeout and duplicate handling, reconnect, MQTT loopback, and the tenant smoke runner's telemetry checks. The JavaScript suites exercise the RuleChain scripts and validate dashboard and device templates. Each local suite uses synthetic data.

Run the [authenticated tenant smoke test](../../coreiot/docs/VERIFICATION.md#run-against-the-course-tenant) with the Python simulator and a separate sandbox entity. Use the [physical demo checklist](../../coreiot/docs/DEMO.md) for hardware evidence.
