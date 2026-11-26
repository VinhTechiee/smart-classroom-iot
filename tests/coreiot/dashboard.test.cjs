const assert = require('node:assert/strict');
const { test } = require('node:test');
const dashboard = require('../../coreiot/platform/smart-classroom.dashboard.json');
const profile = require('../../coreiot/platform/smart-classroom.device-profile.json');
const device = require('../../coreiot/platform/smart-classroom.device.json');

const { widgets, states, entityAliases, timewindow } = dashboard.configuration;
const [classroomAlias] = Object.values(entityAliases);

function getWidget(title) {
    const match = Object.values(widgets).find(widget => widget.config.title === title);
    assert.ok(match, `Missing widget ${title}`);
    return match;
}

function dataKeys(title) {
    return getWidget(title).config.datasources.flatMap(source => source.dataKeys);
}

function format(dataKey, time, value) {
    assert.equal(dataKey.usePostProcessing, true);
    return new Function('time', 'value', dataKey.postFuncBody)(time, value);
}

test('device templates select the standard device API and require a tenant profile ID', () => {
    assert.equal(profile.name, device.type);
    assert.equal(profile.transportType, 'DEFAULT');
    assert.equal(profile.profileData.transportConfiguration.type, profile.transportType);
    assert.equal(profile.provisionType, 'DISABLED');
    assert.equal(profile.profileData.provisionConfiguration.type, profile.provisionType);
    assert.deepEqual(device.deviceProfileId, { id: '${deviceProfile.id}', entityType: 'DEVICE_PROFILE' });
    assert.equal(device.name, '${deviceName}');
    assert.equal(device.id, undefined);
    assert.equal(device.credentials, undefined);
});

test('dashboard layout uses an unbound single classroom alias and has no overlapping widgets', () => {
    const layout = states.default.layouts.main;
    assert.equal(classroomAlias.alias, 'Classroom');
    assert.equal(classroomAlias.filter.resolveMultiple, false);
    assert.equal(classroomAlias.filter.entityType, 'DEVICE');
    assert.equal(classroomAlias.filter.entityNameFilter, '__select_classroom_device_in_entity_aliases__');
    assert.deepEqual(Object.keys(layout.widgets).sort(), Object.keys(widgets).sort());

    const occupiedCells = new Set();
    for (const [id, widget] of Object.entries(widgets)) {
        const { row, col, sizeX, sizeY, config } = widget;
        assert.equal(widget.id, id);
        assert.deepEqual(layout.widgets[id], { row, col, sizeX, sizeY });
        assert.ok(row >= 0 && col >= 0 && sizeX > 0 && sizeY > 0 && col + sizeX <= layout.gridSettings.columns);
        for (let y = row; y < row + sizeY; y++) {
            for (let x = col; x < col + sizeX; x++) {
                const cell = `${x},${y}`;
                assert.equal(occupiedCells.has(cell), false, `Overlapping widget at ${cell}`);
                occupiedCells.add(cell);
            }
        }
        for (const source of config.datasources ?? []) {
            assert.equal(source.entityAliasId, classroomAlias.id);
        }
    }
});

test('latest telemetry covers monitoring fields and keeps unknown states distinct from false', () => {
    const environmental = dataKeys('Environmental monitoring');
    assert.deepEqual(environmental.map(key => key.name), ['temperature', 'humidity', 'light', 'motion', 'distance']);

    const states = dataKeys('Actuator monitoring (last reported)');
    assert.deepEqual(states.map(key => key.name), ['lamp', 'fan', 'door']);
    for (const key of [...states, ...environmental.filter(item => item.name === 'motion')]) {
        assert.equal(key.type, 'timeseries');
        assert.equal(format(key, 0, undefined), 'Unknown');
        assert.equal(format(key, 0, null), 'Unknown');
        assert.notEqual(format(key, 0, false), 'Unknown');
        assert.equal(format(key, 0, 'false'), format(key, 0, false));
    }
    assert.equal(format(states[0], 0, true), 'On');
    assert.equal(format(states[0], 0, false), 'Off');
    assert.equal(format(states[2], 0, true), 'Open');
    assert.equal(format(states[2], 0, false), 'Closed');
});

test('system and history use stored telemetry times and independent freshness window', () => {
    const system = dataKeys('System monitoring');
    assert.deepEqual(system.map(key => [key.name, key.type]), [
        ['deviceId', 'timeseries'], ['active', 'attribute'], ['fwVersion', 'timeseries'], ['temperature', 'timeseries']
    ]);
    assert.equal(format(system[1], 0, 'true'), 'Active');
    assert.equal(format(system[1], 0, false), 'Inactive');
    assert.equal(format(system[3], Date.UTC(2026, 10, 25, 8), 28.5), '2026-11-25T08:00:00.000Z');
    assert.equal(format(system[3], undefined, undefined), 'Unknown');

    const recent = getWidget('Recent temperature samples (30 s)').config;
    assert.equal(recent.useDashboardTimewindow, false);
    assert.equal(recent.timewindow.realtime.timewindowMs, 30_000);
    assert.equal(recent.timewindow.aggregation.type, 'NONE');
    assert.equal(timewindow.realtime.timewindowMs, 1_800_000);
    assert.equal(timewindow.aggregation.type, 'NONE');
    const history = [
        ['Temperature (°C)', ['temperature']], ['Humidity (%)', ['humidity']],
        ['Light-level history (raw)', ['light']], ['Actuator history', ['lamp', 'fan', 'door']]
    ];
    for (const [title, keyNames] of history) {
        assert.equal(getWidget(title).config.useDashboardTimewindow, true);
        assert.deepEqual(dataKeys(title).map(key => key.name), keyNames);
    }
    assert.equal(getWidget('Actuator history').config.settings.showTimestamp, true);
});

test('controls issue six two-way, nonpersistent commands with native boolean params', () => {
    const actions = Object.values(widgets).filter(widget => widget.type === 'rpc');
    const commands = actions.map(({ config }) => {
        const { methodName, methodParams, oneWayElseTwoWay, requestPersistent, showError } = config.settings;
        assert.equal(config.targetDevice.entityAliasId, classroomAlias.id);
        assert.deepEqual(config.targetDeviceAliasIds, [classroomAlias.id]);
        assert.equal(oneWayElseTwoWay, false);
        assert.equal(requestPersistent, false);
        assert.equal(showError, true);
        return [methodName, JSON.parse(methodParams)];
    });
    assert.deepEqual(commands, [
        ['setLamp', true], ['setLamp', false], ['setFan', true], ['setFan', false], ['setDoor', true], ['setDoor', false]
    ]);
});
