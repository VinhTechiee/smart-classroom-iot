const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const now = 1_800_000_000_000;
const telemetryType = "POST_TELEMETRY_REQUEST";
const settings = require("../../coreiot/rules/sandbox-settings.json");
const enabled = {
    ts: String(now),
    temperature: JSON.stringify({ts: now, value: 31}),
    ss_classroomAutomationEnabled: "true",
    ss_classroomManualOverride: "false",
    ss_classroomRuleSettings: JSON.stringify(settings)
};
const hotAndDark = {temperature: 31, light: 249, motion: true, lamp: false, door: false};

function readNode(filename) {
    const script = fs.readFileSync(path.join(__dirname, "../../coreiot/rules", filename), "utf8");
    return vm.compileFunction(script, ["msg", "metadata", "msgType"], {
        parsingContext: vm.createContext({Date: {now: () => now}}),
        filename
    });
}

const automation = readNode("automation.js");
const isFreshTelemetry = readNode("fresh-telemetry.js");
const isRequest = readNode("automation-request-filter.js");
const isSuccessfulAck = readNode("rpc-ack-filter.js");
const alert = readNode("temperature-alert.js");
const proximityAlert = readNode("door-proximity-alert.js");

function commands(telemetry, metadata = enabled, msgType = telemetryType) {
    if (!isFreshTelemetry(telemetry, metadata, msgType)) return [];
    const outputs = automation(telemetry, metadata, msgType);
    const candidates = Array.isArray(outputs) ? outputs : [outputs];
    return candidates.filter(({msg}) => isRequest(msg));
}

function payloads(...args) {
    return Array.from(commands(...args), ({msg}) => ({...msg}));
}

test("automation defaults to disabled and requires explicit release", () => {
    for (const metadata of [
        {},
        {...enabled, ss_classroomAutomationEnabled: "false"},
        {...enabled, ss_classroomManualOverride: undefined},
        {...enabled, ss_classroomManualOverride: "true"},
        {...enabled, ss_classroomManualOverride: "0"}
    ]) {
        assert.deepEqual(payloads(hotAndDark, metadata), []);
    }
});

test("automation excludes missing, stale, implausibly future, and non-telemetry input", () => {
    for (const ts of [undefined, "", "invalid", String(now - 30_001), String(now + 5_001)]) {
        assert.deepEqual(payloads(hotAndDark, {...enabled, ts}), []);
    }
    assert.deepEqual(payloads(hotAndDark, enabled, "POST_ATTRIBUTES_REQUEST"), []);
    assert.deepEqual(payloads(null), []);
    assert.equal(isFreshTelemetry(hotAndDark, null, telemetryType), false);
    for (const ts of [String(now - 30_000), String(now + 5_000)]) {
        const latest = JSON.stringify({ts: Number(ts), value: 31});
        assert.equal(isFreshTelemetry(hotAndDark, {...enabled, ts, temperature: latest}, telemetryType), true);
    }
});

test("fresh out-of-band readings make two-way boolean requests to the telemetry originator", () => {
    const requests = commands(hotAndDark, enabled);
    assert.deepEqual(payloads(hotAndDark), [
        {method: "setLamp", params: true}
    ]);
    assert.equal(requests.length, 1);
    for (const request of requests) {
        assert.equal(request.msgType, telemetryType);
        assert.deepEqual({...request.metadata}, {
            classroomExpectedRpcState: "true",
            oneway: "false",
            persistent: "false"
        });
    }
    assert.deepEqual(payloads({temperature: 27, light: 350, motion: true, lamp: true}), [
        {method: "setLamp", params: false}
    ]);
});

test("freshness gate suppresses superseded arrivals before alerts and automation", () => {
    const earlier = now - 5_000;
    const superseded = {...enabled, ts: String(earlier)};
    assert.equal(isFreshTelemetry(hotAndDark, superseded, telemetryType), false);
    assert.deepEqual(payloads(hotAndDark, superseded), []);
    assert.deepEqual(payloads(hotAndDark, {...enabled, temperature: undefined}), []);
    assert.deepEqual(payloads(hotAndDark, {...enabled, temperature: "31"}), []);
    assert.equal(payloads(hotAndDark, {
        ...enabled, ts: String(earlier), temperature: JSON.stringify({ts: earlier, value: 31})
    }).length, 1);
});

test("hysteresis and already-reported state suppress repeat requests", () => {
    assert.deepEqual(payloads({...hotAndDark, lamp: true}), []);
    for (const actual of [true, false]) {
        assert.deepEqual(payloads({temperature: 29, light: 300, motion: true, lamp: actual}), []);
    }
});

test("invalid inputs are suppressed for the affected actuator", () => {
    assert.deepEqual(payloads({...hotAndDark, temperature: "30"}), [{method: "setLamp", params: true}]);
    assert.deepEqual(payloads({...hotAndDark, lamp: 0}), []);
    assert.deepEqual(payloads({...hotAndDark, light: NaN}), []);
    for (const motion of [undefined, null, "true", 1]) {
        assert.deepEqual(payloads({...hotAndDark, motion}), []);
    }
    assert.equal(isRequest({method: "setDoor", params: false}), false);
    assert.equal(isRequest({method: "setFan", params: true}), false);
    assert.equal(isRequest({method: "setLamp", params: "false"}), false);
});

test("lamp requires motion and low light to turn on and turns off for inactivity or brightness", () => {
    for (const [light, motion, lamp, expected] of [
        [249, true, false, [{method: "setLamp", params: true}]],
        [250, true, false, []],
        [249, false, false, []],
        [249, false, true, [{method: "setLamp", params: false}]],
        [349, true, true, []],
        [350, true, true, [{method: "setLamp", params: false}]]
    ]) {
        assert.deepEqual(payloads({light, motion, lamp}), expected);
    }
});

test("missing, malformed, or inverted threshold settings cannot actuate", () => {
    for (const ss_classroomRuleSettings of [undefined, "{", "null", "[]", "{}", "2", "true"]) {
        assert.deepEqual(payloads(hotAndDark, {...enabled, ss_classroomRuleSettings}), []);
    }
    assert.deepEqual(payloads(hotAndDark, {
        ...enabled,
        ss_classroomRuleSettings: JSON.stringify({...settings, lampOnBelow: 400})
    }), []);
});

test("RPC requires a matching boolean and an application-level success acknowledgement", () => {
    const ack = {id: "cmd-1", ok: true, actualState: false, ts: null};
    const metadata = {classroomExpectedRpcState: "false"};
    assert.equal(isSuccessfulAck(ack, metadata), true);
    assert.equal(isSuccessfulAck({...ack, actualState: true}, metadata), false);
    assert.equal(isSuccessfulAck({...ack, actualState: "false"}, metadata), false);
    assert.equal(isSuccessfulAck({...ack, ok: false, error: "actuator failed"}, metadata), false);
    assert.equal(isSuccessfulAck({...ack, id: ""}, metadata), false);
    assert.equal(isSuccessfulAck(ack, {}), false);
});

test("alert classification covers open, clear, deadband, and invalid readings", () => {
    for (const [temperature, expected] of [
        [36, "High"], [35, "High"], [34, "Ignore"], [33, "Recovered"],
        ["37", "Ignore"], [null, "Ignore"], [undefined, "Ignore"], [Infinity, "Ignore"]
    ]) {
        assert.equal(alert({temperature}, {}, telemetryType), expected);
    }
    assert.equal(alert({temperature: 35}, {}, "ALARM"), "Ignore");
});

test("door proximity alarm is opt-in and holds its state between distance thresholds", () => {
    const metadata = {ss_classroomDoorProximityAlertEnabled: "true"};
    for (const [door, distance, expected] of [
        [true, 10, "Near"], [true, 15, "Near"], [true, 15.1, "Ignore"],
        [true, 24.9, "Ignore"], [true, 25, "Recovered"], [false, 10, "Recovered"],
        [false, null, "Ignore"], [true, -1, "Ignore"], [true, "10", "Ignore"],
        [true, Infinity, "Ignore"], ["true", 10, "Ignore"]
    ]) {
        assert.equal(proximityAlert({door, distance}, metadata, telemetryType), expected);
    }
    assert.equal(proximityAlert({door: true, distance: 10}, {}, telemetryType), "Ignore");
    assert.equal(proximityAlert({door: true, distance: 10}, metadata, "ALARM"), "Ignore");
});

test("sandbox export wires the actual scripts and stays detached and log-only for actuator automation", () => {
    const rulesPath = path.join(__dirname, "../../coreiot/rules");
    const generator = path.join(rulesPath, "export-sandbox-chain.cjs");
    const {ruleChain, metadata} = JSON.parse(execFileSync(process.execPath, [generator], {encoding: "utf8"}));
    const {nodes, connections} = metadata;
    assert.equal(ruleChain.root, false);
    assert.equal(metadata.ruleChainConnections, null);
    assert.equal(nodes[metadata.firstNodeIndex].name, "Latest sample");
    assert.ok(!nodes.some(({type}) => /RPC|Notification/.test(type)));

    function destinations(name, relation) {
        const fromIndex = nodes.findIndex(node => node.name === name);
        return connections.filter(connection => connection.fromIndex === fromIndex && connection.type === relation)
            .map(connection => nodes[connection.toIndex].name);
    }

    assert.deepEqual(destinations("Latest sample", "Success"), ["Fresh telemetry"]);
    assert.deepEqual(destinations("Fresh telemetry", "True"),
        ["Temperature switch", "Proximity attributes", "Automation attributes"]);
    assert.deepEqual(destinations("Automation attributes", "Success"), ["Fresh after lookup"]);
    assert.deepEqual(destinations("Fresh after lookup", "True"), ["Automation decisions"]);
    assert.deepEqual(destinations("Request filter", "True"), ["Log automation candidate"]);
    assert.deepEqual(destinations("Temperature switch", "High"), ["Create Classroom High Temperature"]);
    assert.deepEqual(destinations("Temperature switch", "Recovered"), ["Clear Classroom High Temperature"]);
    assert.deepEqual(destinations("Door proximity switch", "Near"), ["Create Classroom Door Proximity"]);
    assert.deepEqual(destinations("Door proximity switch", "Recovered"), ["Clear Classroom Door Proximity"]);
    for (const name of ["Latest sample", "Automation attributes"]) {
        const {configuration} = nodes.find(node => node.name === name);
        assert.deepEqual(configuration.latestTsKeyNames, ["temperature"]);
        assert.equal(configuration.getLatestValueWithTs, true);
        assert.equal(configuration.tellFailureIfAbsent, true);
    }
    const body = nodes.find(node => node.name === "Automation decisions").configuration.jsScript;
    assert.equal(body, fs.readFileSync(path.join(rulesPath, "automation.js"), "utf8"));
});
