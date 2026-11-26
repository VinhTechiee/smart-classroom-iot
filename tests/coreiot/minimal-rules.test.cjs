const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const directory = join(__dirname, "../../coreiot/minimal");
const exportPath = join(directory, "smart-classroom-humidity.rulechain.json");
const settings = require(join(directory, "server-attributes.example.json"));
const {ruleChain, metadata: graph} = require(exportPath);
const nodes = Object.fromEntries(graph.nodes.map(node => [node.name, node]));
const telemetryType = "POST_TELEMETRY_REQUEST";
const now = 1_800_000_000_000;

function script(name, field = "jsScript") {
    const body = nodes[name].configuration[field];
    const run = vm.compileFunction(body, ["msg", "metadata", "msgType"], {
        parsingContext: vm.createContext({Date: {now: () => now}}),
        filename: name
    });
    return (msg, metadata, msgType = telemetryType) => JSON.parse(JSON.stringify(run(msg, metadata, msgType)));
}

const accepts = script("Classroom humidity only");
const preserve = script("Preserve humidity sample");
const classify = script("Humidity alarm threshold");
const alarmDetails = script("Create humidity alarm", "alarmDetailsBuildJs");
const decide = script("LED decision");
const hasAttempt = script("LED attempt required");
const build = script("Build LED request");
const verifyCommand = script("Valid LED command");
const ack = script("Check device ACK");

function telemetry(humidity = 80, lamp = false, ts = now) {
    const deviceId = "classroom-01-sim";
    return {
        msg: {deviceId, humidity, lamp},
        metadata: {deviceName: deviceId, ts: String(ts)}
    };
}

function sample(humidity = 80, lamp = false, ts = now) {
    const incoming = telemetry(humidity, lamp, ts);
    const {msg, metadata} = preserve(incoming.msg, incoming.metadata);
    return {
        msg: {
            ...msg,
            humidity: {ts, value: humidity},
            lamp: {ts, value: lamp},
            ss_classroomHumidityMeasurement: settings.classroomHumidityMeasurement,
            ss_classroomAutomationEnabled: true,
            ss_classroomManualOverride: false,
            ss_active: true
        },
        metadata
    };
}

function command(telemetry, reread = telemetry.msg) {
    const attempt = decide(telemetry.msg, telemetry.metadata);
    if (!hasAttempt(attempt.msg, attempt.metadata, attempt.msgType)) return null;
    const latest = {...reread};
    delete latest.sample;
    delete latest.ss_classroomLastLedAttempt;
    const request = build({...attempt.msg, ...latest}, attempt.metadata, attempt.msgType);
    return verifyCommand(request.msg, request.metadata, request.msgType) ? request : null;
}

test("humidity export is reproducible and boots detached with no path into automatic RPC", () => {
    const generator = join(directory, "export-humidity-chain.cjs");
    const exportJson = readFileSync(exportPath, "utf8").replace(/\r\n/g, "\n");
    assert.equal(execFileSync(process.execPath, [generator], {encoding: "utf8"}), exportJson);
    assert.equal(ruleChain.type, "CORE");
    assert.equal(ruleChain.root, false);
    assert.equal(graph.ruleChainConnections, null);
    assert.equal(graph.nodes[graph.firstNodeIndex].name, "Classroom humidity only");
    assert.equal(Object.keys(nodes).length, graph.nodes.length);
    assert.equal(settings.classroomAutomationEnabled, false);
    assert.equal(settings.classroomManualOverride, true);

    const edges = graph.connections.map(connection => {
        const {fromIndex, toIndex, type} = connection;
        assert.ok(graph.nodes[fromIndex] && graph.nodes[toIndex]);
        return [graph.nodes[fromIndex].name, type, graph.nodes[toIndex].name];
    });
    const rpcName = "RPC LED - connect in simulator";
    assert.ok(edges.every(([, , to]) => to !== rpcName));
    for (const edge of [
        ["Classroom humidity only", "True", "Order by device"],
        ["Order by device", "Success", "Preserve humidity sample"],
        ["Preserve humidity sample", "Success", "Latest humidity and controls"],
        ["Latest humidity and controls", "Success", "Humidity alarm threshold"],
        ["Humidity alarm threshold", "High", "Create humidity alarm"],
        ["Humidity alarm threshold", "Recovered", "Clear humidity alarm"],
        ["Latest humidity and controls", "Success", "LED decision"],
        ["LED decision", "Success", "LED attempt required"],
        ["LED attempt required", "True", "Save LED attempt"],
        ["Save LED attempt", "Success", "Recheck humidity and controls"],
        ["Save LED attempt", "Failure", "Humidity rule processing failed"],
        ["Recheck humidity and controls", "Success", "Build LED request"],
        ["Recheck humidity and controls", "Failure", "Humidity rule processing failed"],
        ["Build LED request", "Success", "Valid LED command"],
        ["Valid LED command", "True", "LED candidate"],
        [rpcName, "Success", "Check device ACK"],
        [rpcName, "Failure", "LED RPC failed or timed out"],
        ["Check device ACK", "True", "LED ACK accepted"],
        ["Check device ACK", "False", "LED ACK rejected"]
    ]) assert.ok(edges.some(actual => actual.every((part, index) => part === edge[index])), edge.join(" -> "));

    assert.equal(nodes["Order by device"].type, "org.thingsboard.rule.engine.flow.TbCheckpointNode");
    assert.equal(nodes["Order by device"].queueName, "SequentialByOriginator");
    const lookup = nodes["Latest humidity and controls"].configuration;
    const recheck = nodes["Recheck humidity and controls"].configuration;
    for (const config of [lookup, recheck]) {
        assert.equal(config.fetchTo, "DATA");
        assert.equal(config.getLatestValueWithTs, true);
        assert.deepEqual(config.latestTsKeyNames, ["humidity", "lamp"]);
    }
    assert.deepEqual(recheck.serverAttributeNames, [...Object.keys(settings), "active"]);
    assert.deepEqual(lookup.serverAttributeNames, [...recheck.serverAttributeNames, "classroomLastLedAttempt"]);
    assert.equal(nodes["Save LED attempt"].configuration.scope, "SERVER_SCOPE");
    assert.equal(nodes["Save LED attempt"].configuration.notifyDevice, false);
    assert.equal(nodes["Save LED attempt"].configuration.sendAttributesUpdatedNotification, false);
    assert.deepEqual(nodes["Save LED attempt"].configuration.processingSettings, {type: "ON_EVERY_MESSAGE"});
    assert.equal(nodes[rpcName].configuration.timeoutInSeconds, 10);
    assert.equal(nodes["Create humidity alarm"].configuration.severity, "MAJOR");
    for (const name of ["Create humidity alarm", "Clear humidity alarm"]) {
        assert.equal(nodes[name].configuration.alarmType, "Classroom High Humidity");
    }
});

test("only matching classroom telemetry with numeric RH enters the graph", () => {
    const {msg, metadata} = telemetry();
    for (const humidity of [0, 80, 100]) assert.equal(accepts({...msg, humidity}, metadata), true);
    for (const humidity of [undefined, null, "80", -0.1, 100.1, NaN, Infinity]) {
        assert.equal(accepts({...msg, humidity}, metadata), false);
    }
    assert.equal(accepts({...msg, deviceId: "classroom-01"}, metadata), false);
    assert.equal(accepts({...msg, deviceId: "other"}, {...metadata, deviceName: "other"}), false);
    assert.equal(accepts(msg, metadata, "POST_ATTRIBUTES_REQUEST"), false);
});

test("the original reading cannot supply or override trusted freshness and control values", () => {
    const {msg, metadata} = telemetry();
    const cleaned = preserve({
        ...msg, sample: {humidity: 99}, ss_classroomAutomationEnabled: true, ss_active: true
    }, {...metadata, humidity: "stale", ss_classroomManualOverride: "false"});
    assert.deepEqual(cleaned, {msg: {sample: {humidity: 80, lamp: false}}, metadata, msgType: telemetryType});
    assert.deepEqual(classify(cleaned.msg, cleaned.metadata), []);
    assert.equal(command(cleaned), null);
});

test("freshness rejects absent, stale, future and superseded samples for alarms and LEDs", () => {
    for (const ts of [now - 30_001, now + 5_001]) {
        const telemetry = sample(80, false, ts);
        assert.deepEqual(classify(telemetry.msg, telemetry.metadata), []);
        assert.equal(command(telemetry), null);
    }
    const {msg, metadata} = sample();
    for (const ts of [undefined, "invalid"]) {
        assert.deepEqual(classify(msg, {...metadata, ts}), []);
        assert.equal(command({msg, metadata: {...metadata, ts}}), null);
    }
    for (const changed of [
        {humidity: undefined}, {humidity: "80"},
        {humidity: {ts: now + 1, value: 80}},
        {humidity: {ts: now, value: 75}}, {humidity: {ts: now, value: "80"}},
        {ss_classroomHumidityMeasurement: undefined}, {ss_classroomHumidityMeasurement: "soil_moisture"}
    ]) {
        const variant = {...msg, ...changed};
        assert.deepEqual(classify(variant, metadata), []);
        assert.equal(command({msg: variant, metadata}), null);
    }
    for (const ts of [now - 30_000, now + 5_000]) assert.ok(command(sample(80, false, ts)));
});

test("alarm hysteresis and recovery continue independently of LED availability and override", () => {
    for (const [humidity, expected] of [[80, ["High"]], [79.99, []], [75.01, []], [75, ["Recovered"]]]) {
        const {msg, metadata} = sample(humidity, null);
        delete msg.sample.lamp;
        delete msg.lamp;
        msg.ss_classroomAutomationEnabled = false;
        msg.ss_classroomManualOverride = true;
        msg.ss_active = false;
        assert.deepEqual(classify(msg, metadata), expected);
        assert.equal(command({msg, metadata}), null);
        assert.deepEqual(alarmDetails(msg, metadata), {humidity, sampleTs: now});
    }
});

test("a valid configured threshold pair changes both alarm and LED thresholds", () => {
    const {msg, metadata} = sample(70.5);
    const custom = {...msg, ss_classroomHumidityHigh: 70.5, ss_classroomHumidityRecovery: 65};
    assert.deepEqual(classify(custom, metadata), ["High"]);
    assert.equal(command({msg: custom, metadata}).msg.params, true);
    for (const invalid of [undefined, null, "70.5", 101, -1, 65, NaN, Infinity]) {
        const variant = {...custom, ss_classroomHumidityHigh: invalid};
        assert.deepEqual(classify(variant, metadata), []);
        assert.equal(command({msg: variant, metadata}), null);
    }
});

test("LED candidates require explicit enable, release, activity and a state change", () => {
    const {msg, metadata} = sample(80, false);
    assert.deepEqual(command({msg, metadata}), {
        msg: {method: "setLamp", params: true},
        metadata: {
            deviceName: "classroom-01-sim", ts: String(now), classroomExpectedRpcState: "true",
            expirationTime: String(now + 10_000), oneway: "false", persistent: "false", retries: "0"
        },
        msgType: telemetryType
    });
    assert.deepEqual(command(sample(75, true)).msg, {method: "setLamp", params: false});
    for (const changed of [
        {ss_classroomAutomationEnabled: undefined}, {ss_classroomAutomationEnabled: false},
        {ss_classroomAutomationEnabled: "true"}, {ss_classroomManualOverride: "false"},
        {ss_classroomManualOverride: undefined}, {ss_classroomManualOverride: true},
        {ss_active: undefined}, {ss_active: false}, {ss_active: "true"},
        {lamp: {ts: now + 1, value: false}}, {lamp: {ts: now, value: true}}
    ]) assert.equal(command({msg: {...msg, ...changed}, metadata}), null);
    for (const telemetry of [sample(80, true), sample(75, false), sample(77, true), sample(77, false), sample(80, "false")]) {
        assert.equal(command(telemetry), null);
    }
});

test("persisted attempts suppress the same sample and a fresh sample inside the cooldown", () => {
    const initial = sample(80, false, now - 15_000);
    const attempt = decide(initial.msg, initial.metadata);
    assert.deepEqual(Object.keys(attempt.msg), ["classroomLastLedAttempt"]);
    const recorded = JSON.parse(attempt.msg.classroomLastLedAttempt);
    assert.deepEqual(recorded, {sampleTs: now - 15_000, requestedAt: now});

    const sameSampleAfterCooldown = JSON.stringify({...recorded, requestedAt: now - 12_001});
    assert.equal(command({...initial, msg: {...initial.msg, ss_classroomLastLedAttempt: sameSampleAfterCooldown}}), null);
    const later = sample();
    later.msg.ss_classroomLastLedAttempt = JSON.stringify({...recorded, requestedAt: now - 11_999});
    assert.equal(command(later), null);
    later.msg.ss_classroomLastLedAttempt = JSON.stringify({...recorded, requestedAt: now - 12_000});
    assert.equal(command(later).msg.params, true);
    for (const malformed of [
        "null", "[]", "{", "{}", recorded, JSON.stringify({sampleTs: now}),
        JSON.stringify({...recorded, requestedAt: -1}), JSON.stringify({...recorded, sampleTs: 1.5})
    ]) {
        later.msg.ss_classroomLastLedAttempt = malformed;
        assert.equal(command(later), null);
    }
});

test("dispatch rereads controls and telemetry after saving an attempt", () => {
    const initial = sample();
    const saved = decide(initial.msg, initial.metadata);
    assert.equal(hasAttempt(saved.msg, saved.metadata, saved.msgType), true);
    for (const changed of [
        {ss_classroomManualOverride: true}, {ss_classroomManualOverride: undefined},
        {ss_classroomAutomationEnabled: false}, {ss_active: false},
        {ss_classroomHumidityMeasurement: "soil_moisture"},
        {ss_classroomHumidityHigh: 85, ss_classroomHumidityRecovery: 75},
        {humidity: {ts: now + 1, value: 80}}, {lamp: {ts: now + 1, value: true}}
    ]) assert.equal(command(initial, {...initial.msg, ...changed}), null);
    assert.deepEqual(command(initial).msg, {method: "setLamp", params: true});
});

test("command dispatch checks the deadline and ACK confirms application success only", () => {
    const request = command(sample(75, true));
    const validAck = {id: "cmd-1", ok: true, actualState: false};
    assert.equal(verifyCommand(request.msg, {...request.metadata, expirationTime: String(now)}), false);
    assert.equal(verifyCommand(request.msg, {...request.metadata, ts: String(now - 30_001)}), false);
    assert.equal(verifyCommand({...request.msg, params: "false"}, request.metadata), false);
    assert.equal(ack(validAck, request.metadata), true);
    for (const variant of [
        {ok: false}, {id: ""}, {actualState: true}, {actualState: "false"}, {actualState: null},
        {id: undefined, ok: undefined, actualState: undefined, error: "TIMEOUT"}
    ]) assert.equal(ack({...validAck, ...variant}, request.metadata), false);
});
