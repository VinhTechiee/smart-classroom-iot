const { parseArgs } = require('node:util')

const TELEMETRY_TOPIC = 'v1/devices/me/telemetry'
const REQUEST_PREFIX = 'v1/devices/me/rpc/request/'
const RESPONSE_PREFIX = 'v1/devices/me/rpc/response/'
const ACTUATORS = new Map([
  ['setLamp', 'lamp'],
  ['setFan', 'fan'],
  ['setDoor', 'door'],
])
const DEFAULT_READINGS = {
  temperature: 28.5,
  humidity: 65,
  light: 320,
  motion: true,
  distance: 42,
  lamp: false,
  fan: false,
  door: false,
  fwVersion: '1.0.0',
}
const PUBLISH_OPTIONS = { qos: 1, retain: false }

class SimulatedClassroom {
  #acknowledgements = new Map()

  constructor({ deviceId = 'classroom-01', synchronized = true, readings } = {}) {
    this.values = { deviceId, ...DEFAULT_READINGS, ...readings }
    this.synchronized = synchronized
  }

  sample(now = Date.now()) {
    return { ...this.values, ts: this.synchronized ? now : null }
  }

  startSession() {
    this.#acknowledgements.clear()
  }

  applyRpc(topic, payload, now = Date.now()) {
    if (!topic.startsWith(REQUEST_PREFIX)) return null
    const requestId = topic.slice(REQUEST_PREFIX.length)
    if (!requestId || requestId.includes('/')) return null

    const responseTopic = RESPONSE_PREFIX + requestId
    const previous = this.#acknowledgements.get(requestId)
    if (previous) return { responseTopic, acknowledgement: previous }

    const id = `coreiot-${requestId}`
    const acknowledgement = this.#execute(id, payload, now)
    if (this.#acknowledgements.size >= 128) {
      this.#acknowledgements.delete(this.#acknowledgements.keys().next().value)
    }
    this.#acknowledgements.set(requestId, acknowledgement)
    return {
      responseTopic,
      acknowledgement,
      telemetry: acknowledgement.ok ? cloudTelemetry(this.sample(now), now) : undefined,
    }
  }

  #execute(id, payload, now) {
    const ts = this.synchronized ? now : null
    const failure = (error) => ({ id, ok: false, actualState: null, ts, error })
    let request
    try {
      request = JSON.parse(payload)
    } catch {
      return failure('invalid_json')
    }

    const actuator = ACTUATORS.get(request?.method)
    if (!actuator) return failure('unsupported_method')
    if (typeof request.params !== 'boolean') return failure('invalid_value')

    this.values[actuator] = request.params
    return { id, ok: true, actualState: this.values[actuator], ts }
  }
}

function cloudTelemetry(sample, receivedAt) {
  const values = { ...sample }
  if (sample.ts === null) delete values.ts
  return { ts: sample.ts ?? receivedAt, values }
}

function attachGateway(client, classroom, intervalMs, log = console) {
  let ready = false

  function publish(topic, data) {
    const payload = JSON.stringify(data)
    client.publish(topic, payload, PUBLISH_OPTIONS, (error) => {
      if (error) log.error(`MQTT publish failed for ${topic}: ${error.message}`)
      else log.log(`Synthetic MQTT publish acknowledged on ${topic} ${payload}`)
    })
  }

  function publishSample() {
    if (!ready || !client.connected) return
    const now = Date.now()
    publish(TELEMETRY_TOPIC, cloudTelemetry(classroom.sample(now), now))
  }

  client.on('connect', () => {
    classroom.startSession()
    client.subscribe(`${REQUEST_PREFIX}+`, { qos: 1 }, (error, granted) => {
      if (error || granted?.[0]?.qos >= 128) {
        log.error('MQTT subscription failed for the CoreIOT RPC topic', error?.message ?? '')
        return
      }
      ready = true
      publishSample()
    })
  })
  client.on('close', () => { ready = false })
  client.on('error', (error) => log.error(`MQTT client error: ${error.message}`))
  client.on('message', (topic, payload, packet) => {
    if (!client.connected || packet.retain) return
    const result = classroom.applyRpc(topic, payload)
    if (!result) return
    publish(result.responseTopic, result.acknowledgement)
    if (result.telemetry) publish(TELEMETRY_TOPIC, result.telemetry)
  })

  const timer = setInterval(publishSample, intervalMs)
  timer.unref()
  return () => {
    clearInterval(timer)
    client.end(true)
  }
}

function parseReadings(options) {
  const readings = {}
  for (const [key, initial] of Object.entries(DEFAULT_READINGS)) {
    const raw = options[key === 'fwVersion' ? 'fw-version' : key]
    if (raw === undefined) continue
    if (typeof initial === 'number') {
      readings[key] = Number(raw)
      if (!raw.trim() || !Number.isFinite(readings[key])) {
        throw new Error(`--${key} requires a finite number`)
      }
    } else if (typeof initial === 'boolean') {
      if (raw !== 'true' && raw !== 'false') throw new Error(`--${key} requires true or false`)
      readings[key] = raw === 'true'
    } else {
      readings[key] = raw
    }
  }
  return readings
}

function main() {
  const { values: options } = parseArgs({ options: {
    'interval-ms': { type: 'string', default: '5000' },
    unsynchronized: { type: 'boolean', default: false },
    temperature: { type: 'string' },
    humidity: { type: 'string' },
    light: { type: 'string' },
    motion: { type: 'string' },
    distance: { type: 'string' },
    lamp: { type: 'string' },
    fan: { type: 'string' },
    door: { type: 'string' },
    'fw-version': { type: 'string' },
  } })
  const intervalMs = Number(options['interval-ms'])
  if (!Number.isInteger(intervalMs) || intervalMs < 1 || intervalMs > 2147483647) {
    throw new Error('--interval-ms requires a positive integer up to 2147483647')
  }
  const classroom = new SimulatedClassroom({
    deviceId: process.env.COREIOT_DEVICE_ID || 'classroom-01',
    synchronized: !options.unsynchronized,
    readings: parseReadings(options),
  })
  const { COREIOT_MQTT_URL: url, COREIOT_DEVICE_TOKEN: token } = process.env
  if (!url || !token) throw new Error('Set COREIOT_MQTT_URL and COREIOT_DEVICE_TOKEN in the environment')

  const broker = new URL(url)
  if (!['mqtt:', 'mqtts:'].includes(broker.protocol) || broker.username || broker.password) {
    throw new Error('COREIOT_MQTT_URL requires an MQTT or MQTTS URL without credentials')
  }

  const { connect } = require('mqtt')
  const client = connect(url, { username: token, clean: true, resubscribe: false })
  const stop = attachGateway(client, classroom, intervalMs)
  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
}

if (require.main === module) {
  try {
    main()
  } catch (error) {
    console.error(error.code === 'MODULE_NOT_FOUND'
      ? 'Run npm ci from tests/coreiot to install MQTT.js'
      : error.message)
    process.exitCode = 1
  }
}

module.exports = { SimulatedClassroom, attachGateway, cloudTelemetry }
