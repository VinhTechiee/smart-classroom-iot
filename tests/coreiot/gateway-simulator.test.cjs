const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { test } = require('node:test')
const { SimulatedClassroom, attachGateway, cloudTelemetry } = require('./gateway-simulator.cjs')

const topic = 'v1/devices/me/telemetry'
const requests = 'v1/devices/me/rpc/request/'
const responses = 'v1/devices/me/rpc/response/'
const now = 1764000000000

test('sends all agreed telemetry fields when the source clock is synchronized', () => {
  const classroom = new SimulatedClassroom({ deviceId: 'classroom-test' })
  const sample = classroom.sample(now)
  assert.deepEqual(sample, {
    deviceId: 'classroom-test',
    ts: now,
    temperature: 28.5,
    humidity: 65,
    light: 320,
    motion: true,
    distance: 42,
    lamp: false,
    fan: false,
    door: false,
    fwVersion: '1.0.0',
  })
  assert.deepEqual(cloudTelemetry(sample, now + 250), { ts: now, values: sample })
})

test('keeps null in the local source sample and uses the gateway receipt time in the cloud envelope', () => {
  const classroom = new SimulatedClassroom({ synchronized: false })
  const sample = classroom.sample(now)
  const encoded = cloudTelemetry(sample, now + 250)
  assert.equal(sample.ts, null)
  assert.equal(encoded.ts, now + 250)
  assert.equal(Object.hasOwn(encoded.values, 'ts'), false)
  assert.deepEqual({ ...encoded.values, ts: null }, sample)
})

test('applies valid boolean RPC for all actuators and correlates the reported states', () => {
  const classroom = new SimulatedClassroom()
  for (const [index, [method, state]] of [['setLamp', 'lamp'], ['setFan', 'fan'], ['setDoor', 'door']].entries()) {
    const result = classroom.applyRpc(`${requests}${index}`, JSON.stringify({ method, params: true }), now)
    assert.equal(result.responseTopic, `${responses}${index}`)
    assert.deepEqual(result.acknowledgement, { id: `coreiot-${index}`, ok: true, actualState: true, ts: now })
    assert.equal(result.telemetry.values[state], true)
  }
  const result = classroom.applyRpc(`${requests}3`, '{"method":"setDoor","params":false}', now)
  assert.equal(result.acknowledgement.actualState, false)
  assert.equal(result.telemetry.values.door, false)
  assert.equal(result.telemetry.values.lamp, true)
  assert.equal(result.telemetry.values.fan, true)
})

test('rejects malformed RPC, unsupported methods and non-boolean parameters without changing state', () => {
  const classroom = new SimulatedClassroom()
  const inputs = [
    ['{', 'invalid_json'],
    ['{"method":"setWindow","params":true}', 'unsupported_method'],
    ['{"method":"constructor","params":true}', 'unsupported_method'],
    ['{"method":"setFan","params":1}', 'invalid_value'],
    ['{"method":"setLamp","params":"true"}', 'invalid_value'],
    ['{"method":"setDoor","params":{"value":true}}', 'invalid_value'],
  ]
  for (const [index, [payload, error]] of inputs.entries()) {
    const result = classroom.applyRpc(`${requests}${index}`, payload, now)
    assert.deepEqual(result.acknowledgement, { id: `coreiot-${index}`, ok: false, actualState: null, ts: now, error })
    assert.equal(result.telemetry, undefined)
  }
  assert.equal(classroom.sample().lamp, false)
  assert.equal(classroom.sample().fan, false)
  assert.equal(classroom.sample().door, false)
})

test('replays a duplicate request acknowledgement without reapplying stale state', () => {
  const classroom = new SimulatedClassroom()
  const on = '{"method":"setLamp","params":true}'
  const off = '{"method":"setLamp","params":false}'
  const first = classroom.applyRpc(`${requests}1`, on, now)
  classroom.applyRpc(`${requests}2`, off, now + 1)
  const duplicate = classroom.applyRpc(`${requests}1`, on, now + 2)
  assert.deepEqual(duplicate.acknowledgement, first.acknowledgement)
  assert.equal(duplicate.telemetry, undefined)
  assert.equal(classroom.sample().lamp, false)
  classroom.startSession()
  assert.equal(classroom.applyRpc(`${requests}1`, on, now + 3).telemetry.values.lamp, true)
})

test('gateway binds the CoreIOT MQTT topics, publishes ACK before telemetry and resubscribes on reconnect', (t) => {
  const published = []
  const subscriptions = []
  const client = new EventEmitter()
  client.connected = true
  client.publish = (topic, payload, options, callback) => {
    published.push({ topic, payload: JSON.parse(payload), options })
    callback()
  }
  client.subscribe = (filter, options, callback) => {
    subscriptions.push({ filter, options })
    callback(null, [{ qos: 1 }])
  }
  client.end = () => {}
  const simulator = new SimulatedClassroom()
  const log = { log() {}, error: assert.fail }
  t.after(attachGateway(client, simulator, 10000, log))

  client.emit('connect')
  client.emit('message', `${requests}8`, Buffer.from('{"method":"setLamp","params":true}'), { retain: true })
  client.emit('message', `${requests}9`, Buffer.from('{"method":"setLamp","params":true}'), { retain: false })
  assert.deepEqual(published.map(({ topic }) => topic), [topic, `${responses}9`, topic])
  assert.equal(published[0].payload.values.lamp, false)
  assert.equal(published[1].payload.actualState, true)
  assert.equal(published[2].payload.values.lamp, true)
  assert.ok(published.every(({ options }) => options.qos === 1 && options.retain === false))

  client.connected = false
  client.emit('close')
  client.emit('message', `${requests}10`, Buffer.from('{"method":"setLamp","params":false}'), { retain: false })
  assert.equal(published.length, 3)
  client.connected = true
  client.emit('connect')
  const subscription = { filter: `${requests}+`, options: { qos: 1 } }
  assert.deepEqual(subscriptions, [subscription, subscription])
  assert.equal(published.at(-1).payload.values.lamp, true)
})
