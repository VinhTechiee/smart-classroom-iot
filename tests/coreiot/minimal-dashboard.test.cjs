const assert = require('node:assert/strict');
const { test } = require('node:test');

const humidity = require('../../coreiot/minimal/smart-classroom-humidity.dashboard.json');
const temperatureHumidity = require('../../coreiot/minimal/smart-classroom-temp-humidity.dashboard.json');
const profile = require('../../coreiot/minimal/smart-classroom.device-profile.json');
const device = require('../../coreiot/minimal/smart-classroom.device.json');

function findWidget(widgets, title) {
    const widget = widgets.find(item => item.config.title === title);
    assert.ok(widget, `Missing widget ${title}`);
    return widget;
}

function dataKeys(widget) {
    return widget.config.datasources.flatMap(source => source.dataKeys);
}

function format(key, timestamp, value) {
    assert.equal(key.usePostProcessing, true);
    return new Function('time', 'value', key.postFuncBody)(timestamp, value);
}

test('minimal profile and device payloads use the existing per-device MQTT path', () => {
    assert.equal(profile.name, 'Smart Classroom Minimal');
    assert.equal(profile.name, device.type);
    assert.equal(profile.type, profile.profileData.configuration.type);
    assert.equal(profile.transportType, 'DEFAULT');
    assert.equal(profile.transportType, profile.profileData.transportConfiguration.type);
    assert.equal(profile.provisionType, 'DISABLED');
    assert.equal(profile.provisionType, profile.profileData.provisionConfiguration.type);
    assert.equal(device.name, '${deviceName}');
    assert.equal(device.additionalInfo.gateway, false);
    assert.deepEqual(device.deviceProfileId, { id: '${deviceProfile.id}', entityType: 'DEVICE_PROFILE' });
    assert.equal(device.credentials, undefined);
    assert.equal(profile.defaultRuleChainId, undefined);
});

for (const [variant, dashboard, hasTemperature] of [
    ['humidity', humidity, false], ['temperature and humidity', temperatureHumidity, true]
]) {
    const configuration = dashboard.configuration;
    const widgets = Object.values(configuration.widgets);
    const [alias] = Object.values(configuration.entityAliases);
    const widget = title => findWidget(widgets, title);

    test(`${variant} dashboard uses a portable device alias and a nonoverlapping layout`, () => {
        assert.deepEqual(alias.filter, {
            type: 'entityName',
            resolveMultiple: false,
            entityType: 'DEVICE',
            entityNameFilter: '__select_classroom_device_in_entity_aliases__'
        });
        assert.equal(alias.alias, 'Classroom');
        assert.deepEqual(Object.keys(configuration.entityAliases), [alias.id]);

        const layout = configuration.states.default.layouts.main;
        assert.deepEqual(Object.keys(layout.widgets).sort(), Object.keys(configuration.widgets).sort());
        const occupied = new Set();
        for (const [id, { config, row, col, sizeX, sizeY }] of Object.entries(configuration.widgets)) {
            assert.equal(configuration.widgets[id].id, id);
            assert.deepEqual(layout.widgets[id], { row, col, sizeX, sizeY });
            assert.ok(row >= 0 && col >= 0 && sizeX > 0 && sizeY > 0 && col + sizeX <= layout.gridSettings.columns);
            for (let y = row; y < row + sizeY; y++) {
                for (let x = col; x < col + sizeX; x++) {
                    const cell = `${x},${y}`;
                    assert.equal(occupied.has(cell), false, `Overlapping widget at ${cell}`);
                    occupied.add(cell);
                }
            }
            for (const source of config.datasources ?? []) {
                assert.equal(source.type, 'entity');
                assert.equal(source.entityAliasId, alias.id);
            }
        }
    });

    test(`${variant} dashboard plots humidity and reports telemetry and connectivity separately`, () => {
        const readings = widget('Last reported readings');
        assert.equal(readings.typeFullFqn, 'system.cards.entities_table');
        assert.deepEqual(dataKeys(readings).map(key => [key.name, key.type]), [
            ['humidity', 'timeseries'], ...(hasTemperature ? [['temperature', 'timeseries']] : [])
        ]);

        const chart = widget('Humidity history (% RH)');
        const recent = widget('Recent humidity (30 s)');
        const temperatureCharts = widgets.filter(item => item.config.title.startsWith('Temperature history'));
        assert.equal(temperatureCharts.length, Number(hasTemperature));
        for (const item of [chart, recent, ...temperatureCharts]) {
            assert.equal(item.typeFullFqn, 'system.time_series_chart');
            assert.equal(item.type, 'timeseries');
            assert.deepEqual(dataKeys(item).map(key => [key.name, key.type]), [
                [item === temperatureCharts[0] ? 'temperature' : 'humidity', 'timeseries']
            ]);
        }
        assert.equal(chart.config.useDashboardTimewindow, true);
        assert.equal(recent.config.useDashboardTimewindow, false);
        assert.equal(recent.config.timewindow.realtime.timewindowMs, 30000);
        assert.equal(recent.config.timewindow.aggregation.type, 'NONE');

        const status = dataKeys(widget('Device status'));
        assert.deepEqual(status.map(key => [key.name, key.type]), [
            ['name', 'entityField'], ['active', 'attribute'], ['fwVersion', 'timeseries'],
            ['deviceId', 'timeseries'], ['humidity', 'timeseries'], ['lamp', 'timeseries']
        ]);
        assert.equal(format(status[1], 0, 'true'), 'Active');
        assert.equal(format(status[1], 0, false), 'Inactive');
        assert.equal(format(status[1], 0, undefined), 'Unknown');
        for (const key of status.slice(3)) {
            assert.equal(format(key, Date.UTC(2026, 10, 26, 9), 0), '2026-11-26T09:00:00.000Z');
            assert.equal(format(key, undefined, undefined), 'Unknown');
            assert.equal(format(key, Infinity, undefined), 'Unknown');
        }
    });

    test(`${variant} dashboard controls the LED with two-way RPC and displays its reported state`, () => {
        const commands = widgets.filter(item => item.type === 'rpc').map(({ typeFullFqn, config }) => {
            const { methodName, methodParams, oneWayElseTwoWay, requestPersistent, showError, requestTimeout } = config.settings;
            assert.equal(typeFullFqn, 'system.control_widgets.rpcbutton');
            assert.deepEqual(config.targetDevice, { type: 'entity', entityAliasId: alias.id });
            assert.equal(oneWayElseTwoWay, false);
            assert.equal(requestPersistent, false);
            assert.equal(showError, true);
            assert.equal(requestTimeout, 10000);
            return [methodName, JSON.parse(methodParams)];
        });
        assert.deepEqual(commands, [['setLamp', true], ['setLamp', false]]);
        const reported = dataKeys(widget('Board LED (last reported)'));
        assert.deepEqual(reported.map(key => [key.name, key.type]), [['lamp', 'timeseries']]);
        assert.equal(format(reported[0], 0, true), 'On');
        assert.equal(format(reported[0], 0, 'false'), 'Off');
        assert.equal(format(reported[0], 0, undefined), 'Unknown');
        assert.equal(format(reported[0], 0, null), 'Unknown');
    });

    test(`${variant} dashboard binds active alarm objects and optional gateway events`, () => {
        const alarms = widget('Active alarms');
        assert.equal(alarms.type, 'alarm');
        assert.equal(alarms.typeFullFqn, 'system.alarm_widgets.alarms_table');
        assert.equal(alarms.config.alarmSource.entityAliasId, alias.id);
        assert.deepEqual(alarms.config.alarmFilterConfig.statusList, ['ACTIVE']);
        assert.deepEqual(alarms.config.alarmSource.alarmFilterConfig.statusList, ['ACTIVE']);
        assert.deepEqual(alarms.config.alarmSource.dataKeys.map(key => [key.name, key.type]), [
            ['createdTime', 'alarm'], ['type', 'alarm'], ['severity', 'alarm'], ['status', 'alarm']
        ]);
        assert.equal(alarms.config.useDashboardTimewindow, false);
        assert.equal(alarms.config.timewindow.realtime.timewindowMs, 2592000000);

        const events = widget('Gateway AI events');
        assert.equal(events.typeFullFqn, 'system.cards.timeseries_table');
        assert.equal(events.config.settings.showTimestamp, true);
        assert.deepEqual(dataKeys(events).map(key => [key.name, key.type]), [['aiEvent', 'timeseries']]);
    });
}
