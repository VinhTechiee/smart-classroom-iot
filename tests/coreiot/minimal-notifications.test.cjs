const assert = require('node:assert/strict');
const { test } = require('node:test');

const chain = require('../../coreiot/minimal/smart-classroom-humidity.rulechain.json');
const target = require('../../coreiot/minimal/high-humidity.notification-target.json');
const template = require('../../coreiot/minimal/high-humidity.notification-template.json');
const rule = require('../../coreiot/minimal/high-humidity.notification-rule.json');

test('humidity notification rule matches the chain alarm and triggers on creation only', () => {
    const create = chain.metadata.nodes.find(node => node.type.endsWith('.TbCreateAlarmNode'));
    const clear = chain.metadata.nodes.find(node => node.type.endsWith('.TbClearAlarmNode'));
    assert.ok(create && clear);
    assert.equal(clear.configuration.alarmType, create.configuration.alarmType);
    assert.equal(rule.enabled, false);
    assert.equal(rule.triggerType, 'ALARM');
    assert.deepEqual(rule.triggerConfig, {
        triggerType: 'ALARM',
        alarmTypes: [create.configuration.alarmType],
        alarmSeverities: [create.configuration.severity],
        notifyOn: ['CREATED']
    });
});

test('humidity notification has one immediate Web delivery to one approved tenant user', () => {
    assert.deepEqual(rule.recipientsConfig, {
        triggerType: 'ALARM',
        escalationTable: { '0': ['${notificationTargetId}'] }
    });
    assert.equal(target.configuration.type, 'PLATFORM_USERS');
    assert.deepEqual(target.configuration.usersFilter, {
        type: 'USER_LIST',
        usersIds: ['${demoUserId}']
    });
    assert.deepEqual(rule.templateId, {
        entityType: 'NOTIFICATION_TEMPLATE',
        id: '${notificationTemplateId}'
    });
    assert.equal(template.notificationType, rule.triggerType);
    const methods = template.configuration.deliveryMethodsTemplates;
    assert.deepEqual(Object.keys(methods), ['WEB']);
    assert.equal(methods.WEB.enabled, true);
    assert.match(methods.WEB.subject, /\$\{alarmOriginatorName\}/);
    assert.match(methods.WEB.body, /\$\{alarmId\}/);
});
