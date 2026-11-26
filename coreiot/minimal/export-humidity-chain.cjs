const {readFileSync, writeFileSync} = require("node:fs");
const {join} = require("node:path");
const defaults = require("./server-attributes.example.json");

const nodes = [];
const connections = [];
const alarmType = "Classroom High Humidity";
const rpcTimeoutSeconds = 10;
const cooldownMs = 12_000;

function node(type, name, layoutX, layoutY, configuration, configurationVersion = 0) {
    const index = nodes.length;
    nodes.push({
        type: `org.thingsboard.rule.engine.${type}`,
        name,
        configurationVersion,
        configuration,
        additionalInfo: {layoutX, layoutY}
    });
    return index;
}

function js(body) {
    return {scriptLang: "JS", jsScript: body.replace(/\r\n/g, "\n").trim()};
}

function log(name, x, y) {
    return node("action.TbLogNode", name, x, y, js(
        `return ${JSON.stringify(name)} + " " + JSON.stringify({device: metadata.deviceName, sampleTs: metadata.ts, data: msg});`
    ));
}

function connect(fromIndex, toIndex, type) {
    connections.push({fromIndex, toIndex, type});
}

const humidityDecision = String.raw`
function latestMatches(sample, ts, value) {
    return !!sample && sample.ts === ts && sample.value === value;
}

function humidityRelation(now, sample) {
    if (!sample || msg.ss_classroomHumidityMeasurement !== "relative_air_humidity" ||
        typeof metadata.ts !== "string" || !/^\d+$/.test(metadata.ts) ||
        typeof sample.humidity !== "number" || !isFinite(sample.humidity) || sample.humidity < 0 || sample.humidity > 100) {
        return null;
    }

    var ts = Number(metadata.ts);
    if (now - ts > 30000 || ts - now > 5000 || !latestMatches(msg.humidity, ts, sample.humidity)) {
        return null;
    }

    var high = msg.ss_classroomHumidityHigh;
    var recovery = msg.ss_classroomHumidityRecovery;
    if (high === undefined && recovery === undefined) {
        high = ${defaults.classroomHumidityHigh};
        recovery = ${defaults.classroomHumidityRecovery};
    }
    if (typeof high !== "number" || typeof recovery !== "number" ||
        !(recovery >= 0 && recovery < high && high <= 100)) return null;

    if (sample.humidity >= high) return "High";
    if (sample.humidity <= recovery) return "Recovered";
    return null;
}
`;

const ledDecision = `${humidityDecision}
function desiredLedState(now, sample) {
    if (msg.ss_classroomAutomationEnabled !== true || msg.ss_classroomManualOverride !== false ||
        msg.ss_active !== true) return null;

    var relation = humidityRelation(now, sample);
    if (!relation || typeof sample.lamp !== "boolean" ||
        !latestMatches(msg.lamp, Number(metadata.ts), sample.lamp)) return null;

    var desired = relation === "High";
    return sample.lamp === desired ? null : desired;
}
`;

const input = node("filter.TbJsFilterNode", "Classroom humidity only", 220, 250, js(`
return msgType === "POST_TELEMETRY_REQUEST" && !!metadata && !!msg &&
    (metadata.deviceName === "classroom-01-sim" || metadata.deviceName === "classroom-01") &&
    msg.deviceId === metadata.deviceName && typeof msg.humidity === "number" &&
    isFinite(msg.humidity) && msg.humidity >= 0 && msg.humidity <= 100;
`));
const queue = node("flow.TbCheckpointNode", "Order by device", 470, 250, {}, 1);
nodes[queue].queueName = "SequentialByOriginator";
const preserve = node("transform.TbTransformMsgNode", "Preserve humidity sample", 720, 250, js(`
return {
    msg: {sample: {humidity: msg.humidity, lamp: msg.lamp}},
    metadata: {deviceName: metadata.deviceName, ts: metadata.ts},
    msgType: msgType
};
`));
const lookupConfig = {
    fetchTo: "DATA",
    clientAttributeNames: [],
    sharedAttributeNames: [],
    serverAttributeNames: [...Object.keys(defaults), "active"],
    latestTsKeyNames: ["humidity", "lamp"],
    tellFailureIfAbsent: false,
    getLatestValueWithTs: true
};
const latest = node("metadata.TbGetAttributesNode", "Latest humidity and controls", 970, 250, {
    ...lookupConfig,
    serverAttributeNames: [...lookupConfig.serverAttributeNames, "classroomLastLedAttempt"]
}, 1);
const alarmSwitch = node("filter.TbJsSwitchNode", "Humidity alarm threshold", 1220, 100, js(`${humidityDecision}
var relation = humidityRelation(Date.now(), msg.sample);
return relation ? [relation] : [];
`));
const alarmConfig = {
    alarmType,
    scriptLang: "JS",
    alarmDetailsBuildJs: "return {humidity: msg.sample.humidity, sampleTs: Number(metadata.ts)};"
};
const createAlarm = node("action.TbCreateAlarmNode", "Create humidity alarm", 1470, 50, {
    ...alarmConfig,
    severity: "MAJOR",
    useMessageAlarmData: false,
    propagate: false,
    propagateToOwner: false,
    propagateToOwnerHierarchy: false,
    propagateToTenant: false,
    relationTypes: []
});
const clearAlarm = node("action.TbClearAlarmNode", "Clear humidity alarm", 1470, 150, alarmConfig);

const decision = node("transform.TbTransformMsgNode", "LED decision", 1220, 360, js(`${ledDecision}
var skip = {msg: {}, metadata: metadata, msgType: msgType};
var now = Date.now();
var desired = desiredLedState(now, msg.sample);
if (desired === null) return skip;

var sampleTs = Number(metadata.ts);
if (msg.ss_classroomLastLedAttempt !== undefined) {
    if (typeof msg.ss_classroomLastLedAttempt !== "string") return skip;
    try {
        var previous = JSON.parse(msg.ss_classroomLastLedAttempt);
        if (!previous || !validTimestamp(previous.sampleTs) || !validTimestamp(previous.requestedAt) ||
            previous.sampleTs >= sampleTs || now - previous.requestedAt < ${cooldownMs}) return skip;
    } catch (error) {
        return skip;
    }
}

function validTimestamp(ts) {
    return typeof ts === "number" && ts > 0 && isFinite(ts) && Math.floor(ts) === ts;
}

return {
    msg: {classroomLastLedAttempt: JSON.stringify({sampleTs: sampleTs, requestedAt: now})},
    metadata: {
        deviceName: metadata.deviceName, ts: metadata.ts, notifyDevice: "false",
        classroomLedSample: JSON.stringify(msg.sample),
        classroomExpectedRpcState: String(desired), expirationTime: String(now + ${rpcTimeoutSeconds * 1000})
    },
    msgType: "POST_ATTRIBUTES_REQUEST"
};
`));
const hasAttempt = node("filter.TbJsFilterNode", "LED attempt required", 1470, 360,
    js(`return msgType === "POST_ATTRIBUTES_REQUEST" && typeof msg.classroomLastLedAttempt === "string";`));
const save = node("telemetry.TbMsgAttributesNode", "Save LED attempt", 1720, 360, {
    scope: "SERVER_SCOPE",
    notifyDevice: false,
    sendAttributesUpdatedNotification: false,
    updateAttributesOnlyOnValueChange: false,
    processingSettings: {type: "ON_EVERY_MESSAGE"}
}, 3);
const recheck = node("metadata.TbGetAttributesNode", "Recheck humidity and controls", 1970, 360, lookupConfig, 1);
const build = node("transform.TbTransformMsgNode", "Build LED request", 2220, 360, js(`${ledDecision}
var desired = desiredLedState(Date.now(), JSON.parse(metadata.classroomLedSample));
var state = metadata.classroomExpectedRpcState;
return {
    msg: desired !== null && String(desired) === state ? {method: "setLamp", params: desired} : {},
    metadata: {
        deviceName: metadata.deviceName, ts: metadata.ts,
        classroomExpectedRpcState: metadata.classroomExpectedRpcState,
        expirationTime: metadata.expirationTime, oneway: "false", persistent: "false", retries: "0"
    },
    msgType: "POST_TELEMETRY_REQUEST"
};
`));
const command = node("filter.TbJsFilterNode", "Valid LED command", 2470, 360, js(`
var now = Date.now();
var ageMs = now - Number(metadata.ts);
return msg.method === "setLamp" && typeof msg.params === "boolean" &&
    String(msg.params) === metadata.classroomExpectedRpcState &&
    ageMs >= -5000 && ageMs <= 30000 && Number(metadata.expirationTime) > now;
`));
const candidate = log("LED candidate", 2720, 280);
const rpc = node("rpc.TbSendRPCRequestNode", "RPC LED - connect in simulator", 2720, 440, {
    timeoutInSeconds: rpcTimeoutSeconds
});
const ack = node("filter.TbJsFilterNode", "Check device ACK", 2970, 440,
    js(readFileSync(join(__dirname, "../rules/rpc-ack-filter.js"), "utf8")));
const accepted = log("LED ACK accepted", 3220, 340);
const rejected = log("LED ACK rejected", 3220, 440);
const rpcFailure = log("LED RPC failed or timed out", 3220, 540);
const processingFailure = log("Humidity rule processing failed", 1470, 620);

connect(input, queue, "True");
connect(queue, preserve, "Success");
connect(preserve, latest, "Success");
connect(latest, alarmSwitch, "Success");
connect(alarmSwitch, createAlarm, "High");
connect(alarmSwitch, clearAlarm, "Recovered");
connect(latest, decision, "Success");
connect(decision, hasAttempt, "Success");
connect(hasAttempt, save, "True");
connect(save, recheck, "Success");
connect(recheck, build, "Success");
connect(build, command, "Success");
connect(command, candidate, "True");
connect(rpc, ack, "Success");
connect(rpc, rpcFailure, "Failure");
connect(ack, accepted, "True");
connect(ack, rejected, "False");
for (const source of [queue, preserve, latest, alarmSwitch, createAlarm, clearAlarm, decision, save, recheck, build]) {
    connect(source, processingFailure, "Failure");
}

const exportData = {
    ruleChain: {
        name: "Smart Classroom - Humidity",
        type: "CORE",
        root: false,
        additionalInfo: {description: "Relative humidity alarm and dry-run board LED automation. Attach after telemetry storage."}
    },
    metadata: {firstNodeIndex: input, nodes, connections, ruleChainConnections: null}
};
const json = `${JSON.stringify(exportData, null, 2)}\n`;
if (process.argv[2]) writeFileSync(process.argv[2], json, "utf8");
else process.stdout.write(json);
