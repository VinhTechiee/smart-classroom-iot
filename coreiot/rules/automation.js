// Paste this body into the Rule Chain's JavaScript transformation node.
var noCommand = {msg: {}, metadata: metadata, msgType: msgType};
if (msgType !== "POST_TELEMETRY_REQUEST" || !msg || !metadata ||
    metadata.ss_classroomAutomationEnabled !== "true" ||
    metadata.ss_classroomManualOverride !== "false") {
    return noCommand;
}

var settings;
try {
    settings = JSON.parse(metadata.ss_classroomRuleSettings);
} catch (error) {
    return noCommand;
}
if (!settings || typeof settings !== "object") {
    return noCommand;
}

var commands = [];

function isNumber(value) {
    return typeof value === "number" && isFinite(value);
}

function requestChange(method, reported, desired) {
    if (typeof reported !== "boolean" || reported === desired) {
        return;
    }
    commands.push({
        msg: {method: method, params: desired},
        metadata: {
            classroomExpectedRpcState: String(desired),
            oneway: "false",
            persistent: "false"
        },
        msgType: msgType
    });
}

if (typeof msg.motion === "boolean" && isNumber(msg.light) &&
    isNumber(settings.lampOnBelow) && isNumber(settings.lampOffAt) &&
    settings.lampOnBelow < settings.lampOffAt) {
    if (msg.motion && msg.light < settings.lampOnBelow) {
        requestChange("setLamp", msg.lamp, true);
    } else if (!msg.motion || msg.light >= settings.lampOffAt) {
        requestChange("setLamp", msg.lamp, false);
    }
}

if (isNumber(msg.temperature) && isNumber(settings.fanOnAbove) &&
    isNumber(settings.fanOffBelow) && settings.fanOffBelow < settings.fanOnAbove) {
    if (msg.temperature > settings.fanOnAbove) {
        requestChange("setFan", msg.fan, true);
    } else if (msg.temperature < settings.fanOffBelow) {
        requestChange("setFan", msg.fan, false);
    }
}

// The downstream Script Filter discards this object when no command is due.
return commands.length ? commands : noCommand;
