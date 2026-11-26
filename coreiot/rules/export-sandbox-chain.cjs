const {readFileSync, writeFileSync} = require("node:fs");
const {join} = require("node:path");

// Package the checked-in scripts for import as a detached, log-only automation chain.
const nodes = [];
const connections = [];

function addNode(type, name, layoutX, layoutY, configuration, configurationVersion = 0) {
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

function script(filename) {
    return {scriptLang: "JS", jsScript: readFileSync(join(__dirname, filename), "utf8")};
}

function attributes(serverAttributeNames, fetchLatestTemperature = false) {
    return {
        fetchTo: "METADATA",
        clientAttributeNames: [],
        sharedAttributeNames: [],
        latestTsKeyNames: fetchLatestTemperature ? ["temperature"] : [],
        serverAttributeNames,
        tellFailureIfAbsent: fetchLatestTemperature,
        getLatestValueWithTs: fetchLatestTemperature
    };
}

function connect(fromIndex, toIndex, type) {
    connections.push({fromIndex, toIndex, type});
}

function addAlarmBranch(source, relation, alarmType, severity, alarmDetailsBuildJs, layoutY) {
    const config = {alarmType, scriptLang: "JS", alarmDetailsBuildJs};
    const create = addNode("action.TbCreateAlarmNode", `Create ${alarmType}`, 1280, layoutY, {
        ...config,
        severity,
        useMessageAlarmData: false,
        propagate: false,
        propagateToOwner: false,
        propagateToOwnerHierarchy: false,
        propagateToTenant: false,
        relationTypes: []
    });
    const clear = addNode("action.TbClearAlarmNode", `Clear ${alarmType}`, 1280, layoutY + 90, config);
    connect(source, create, relation);
    connect(source, clear, "Recovered");
}

const latest = addNode("metadata.TbGetAttributesNode", "Latest sample", 280, 270, attributes([], true), 1);
const fresh = addNode("filter.TbJsFilterNode", "Fresh telemetry", 530, 270, script("fresh-telemetry.js"));
const temperature = addNode("filter.TbJsSwitchNode", "Temperature switch", 1030, 85, script("temperature-alert.js"));
const proximityAttributes = addNode("metadata.TbGetAttributesNode", "Proximity attributes", 780, 270,
    attributes(["classroomDoorProximityAlertEnabled"]), 1);
const proximity = addNode("filter.TbJsSwitchNode", "Door proximity switch", 1030, 270, script("door-proximity-alert.js"));
const automationAttributes = addNode("metadata.TbGetAttributesNode", "Automation attributes", 780, 470,
    attributes(["classroomAutomationEnabled", "classroomManualOverride", "classroomRuleSettings"], true), 1);
const freshAfterLookup = addNode("filter.TbJsFilterNode", "Fresh after lookup", 1030, 470, script("fresh-telemetry.js"));
const automation = addNode("transform.TbTransformMsgNode", "Automation decisions", 1280, 470, script("automation.js"));
const request = addNode("filter.TbJsFilterNode", "Request filter", 1530, 470, script("automation-request-filter.js"));
const log = addNode("action.TbLogNode", "Log automation candidate", 1780, 470,
    {scriptLang: "JS", jsScript: "return JSON.stringify(msg);"});

connect(latest, fresh, "Success");
connect(fresh, temperature, "True");
connect(fresh, proximityAttributes, "True");
connect(proximityAttributes, proximity, "Success");
connect(fresh, automationAttributes, "True");
connect(automationAttributes, freshAfterLookup, "Success");
connect(freshAfterLookup, automation, "True");
connect(automation, request, "Success");
connect(request, log, "True");
addAlarmBranch(temperature, "High", "Classroom High Temperature", "MAJOR",
    "return {temperature: msg.temperature};", 40);
addAlarmBranch(proximity, "Near", "Classroom Door Proximity", "WARNING",
    "return {door: msg.door, distance: msg.distance};", 230);

const exported = {
    ruleChain: {name: "Smart Classroom Sandbox", type: "CORE", root: false},
    metadata: {firstNodeIndex: latest, nodes, connections, ruleChainConnections: null}
};
const json = `${JSON.stringify(exported, null, 2)}\n`;
const output = process.argv[2];
if (output) {
    writeFileSync(output, json, "utf8");
} else {
    process.stdout.write(json);
}
