
#include "mqtt_client.h"
#include "config.h"
#include "system_data.h"
#include "automation.h"
#include "ota.h"
#include "command_deadline.h"

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <atomic>
#include <cstring>

// 1. MQTT variables

static WiFiClient wifiClient;
static PubSubClient mqttClient(wifiClient);

static bool mqttReady = false;
static bool wifiWasConnected = false;

static std::atomic<bool> mqttConnected{false};

static unsigned long lastReconnectMs = 0;
static unsigned long lastTelemetryMs = 0;

static constexpr uint16_t CLIENT_BUFFER_BYTES =
    MQTT_BUFFER_SIZE;

static constexpr size_t MAX_JSON_BYTES = 768;

static constexpr size_t MAX_COMMAND_ID_BYTES = 96;

struct ExecutedCommand {
    char id[MAX_COMMAND_ID_BYTES + 1]{};
    uint64_t expiresAt = 0;
    ControlResult result;
    const char* error = nullptr;
};
static ExecutedCommand executed[32];
static bool reportAfterCommand = false;

static constexpr unsigned long TELEMETRY_STALE_MS =
    SENSOR_STALE_MS;

// 2. Publish JSON

static bool publishJson(
    const char* topic,
    const JsonDocument& doc
) {
    if (doc.overflowed()) {
        Serial.println("[MQTT] JSON overflow");
        return false;
    }

    size_t needed = measureJson(doc);

    if (needed > MAX_JSON_BYTES) {
        Serial.println("[MQTT] JSON too large");
        return false;
    }

    char payload[MAX_JSON_BYTES + 1];

    size_t length = serializeJson(
        doc,
        payload,
        sizeof(payload)
    );

    if (length != needed) {
        Serial.println("[MQTT] Serialization failed");
        return false;
    }

    bool ok = mqttClient.publish(
        topic,
        reinterpret_cast<const uint8_t*>(payload),
        static_cast<unsigned int>(length),
        false
    );

    if (!ok) {
        mqttConnected.store(false);
        wifiClient.stop();
    }

    return ok;
}

// 3. Publish ACK

static bool publishAck(
    const char* id,
    const ControlResult& result,
    const char* error = nullptr
) {
    JsonDocument ack;

    ack["id"] = id;
    ack["ok"] = result.ok;
    if (result.stateKnown) {
        ack["actualState"] = result.actualState;
    } else {
        ack["actualState"] = nullptr;
    }
    ack["ts"] = nullptr;

    if (error != nullptr) {
        ack["error"] = error;
    }

    bool ok = publishJson(MQTT_TOPIC_ACK, ack);

    if (!ok) {
        Serial.println("[MQTT] ACK publish failed");
    }

    return ok;
}

// 4. Parse command method

static bool parseMethod(
    const char* method,
    ControlTarget& target
) {
    if (strcmp(method, "setLamp") == 0) {
        target = ControlTarget::Lamp;
    }
    else if (strcmp(method, "setDoor") == 0) {
        target = ControlTarget::Door;
    }
    else {
        return false;
    }

    return true;
}

// 5. MQTT command callback
static bool isTargetAvailable(ControlTarget target) {

    switch (target) {

        case ControlTarget::Lamp:
            return HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED;

        case ControlTarget::Door:
            return HAS_SERVO;

        default:
            return false;
    }
}

static void onMessage(
    char* topic,
    byte* payload,
    unsigned int length
) {
    if (strcmp(topic, MQTT_TOPIC_COMMAND) != 0) {
        return;
    }

    if (
        length == 0 ||
        length > MAX_JSON_BYTES ||
        memchr(payload, '\0', length) != nullptr
    ) {
        Serial.println("[MQTT] Invalid command payload");
        return;
    }

    JsonDocument cmd;

    DeserializationError err = deserializeJson(
        cmd,
        reinterpret_cast<const char*>(payload),
        length
    );

    if (
        err ||
        !cmd.is<JsonObject>() ||
        cmd.overflowed()
    ) {
        Serial.println("[MQTT] Invalid JSON command");
        return;
    }

    // Validate command ID

    if (!cmd["id"].is<const char*>()) {
        Serial.println("[MQTT] Missing/invalid command id");
        return;
    }

    JsonString receivedId =
        cmd["id"].as<JsonString>();

    if (
        receivedId.size() == 0 ||
        receivedId.size() > MAX_COMMAND_ID_BYTES ||
        memchr(
            receivedId.c_str(),
            '\0',
            receivedId.size()
        ) != nullptr
    ) {
        Serial.println("[MQTT] Invalid command id length/content");
        return;
    }

    char id[MAX_COMMAND_ID_BYTES + 1];

    memcpy(
        id,
        receivedId.c_str(),
        receivedId.size()
    );

    id[receivedId.size()] = '\0';

    ControlResult failed;

    uint64_t now = epochMillis();
    uint64_t expiresAt = cmd["expiresAt"].as<uint64_t>();
    if (!cmd["expiresAt"].is<uint64_t>() || !validCommandDeadline(now, expiresAt)) {
        publishAck(id, failed, now == 0 ? "clock_unsynchronized" : "invalid_or_expired_deadline");
        return;
    }
    ExecutedCommand* slot = nullptr;
    for (auto& entry : executed) {
        if (entry.expiresAt > now && strcmp(entry.id, id) == 0) {
            publishAck(id, entry.result, entry.error);
            return;
        }
        if (!slot && entry.expiresAt <= now) {
            slot = &entry;
        }
    }
    if (!slot) {
        publishAck(id, failed, "device_busy");
        return;
    }
    auto finish = [&](const ControlResult& result, const char* error) {
        strcpy(slot->id, id);
        slot->expiresAt = expiresAt;
        slot->result = result;
        slot->error = error;
        reportAfterCommand |= result.ok;
        publishAck(id, result, error);
    };

    // Validate method

    if (!cmd["method"].is<const char*>()) {
        publishAck(
            id,
            failed,
            "missing or invalid method"
        );

        return;
    }

    JsonString method =
        cmd["method"].as<JsonString>();

    if (!cmd["value"].is<bool>()) {
        publishAck(id, failed, "invalid_value");
        return;
    }
    if (method.size() == 0 || memchr(method.c_str(), '\0', method.size()) != nullptr) {
        publishAck(id, failed, "unsupported_method");
        return;
    }
    if (FirmwareOTA::isUpdating()) {
        publishAck(id, failed, "ota_in_progress");
        return;
    }
    const char* source = cmd["source"] | "";
    if (strcmp(method.c_str(), "setDoorAuto") == 0 && strcmp(source, "gateway") == 0) {
        const bool enabled = cmd["value"].as<bool>();
        ControlResult mode;
        mode.ok = Automation::setAutomatic(ControlTarget::Door, enabled, expiresAt);
        mode.actualState = enabled;
        mode.stateKnown = mode.ok;
        finish(mode, mode.ok ? nullptr : "mode_change_failed");
        return;
    }
    ControlTarget target;
    if (!parseMethod(method.c_str(), target)) {
        publishAck(id, failed, "unsupported_method");
        return;
    }
    if (target == ControlTarget::Lamp && LAMP_LOCAL_AVAILABLE && strcmp(source, "gateway") != 0) {
        publishAck(id, failed, "lamp_owned_locally");
        return;
    }

    bool value = cmd["value"].as<bool>();
    if (!isTargetAvailable(target)) {
        publishAck(id, failed, "device_unavailable");
        return;
    }

    ControlResult result =
        Automation::applyManualCommand(
            target,
            value,
        ControlSource::MQTT,
        expiresAt
        );

    const char* error = nullptr;
    if (!result.ok) {
        error = !validCommandDeadline(epochMillis(), expiresAt)
            ? "command_expired" : "control_failed";
    }
    finish(result, error);
}

// 6. Reconnect MQTT broker

static bool reconnect() {

    Serial.printf(
        "[MQTT] Connecting to %s:%d\n",
        MQTT_HOST,
        MQTT_PORT
    );

    const bool connected = MQTT_USERNAME[0]
        ? mqttClient.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD)
        : mqttClient.connect(DEVICE_ID);
    if (!connected) {

        Serial.printf(
            "[MQTT] Connect failed: %d\n",
            mqttClient.state()
        );

        return false;
    }

    if (!mqttClient.subscribe(
            MQTT_TOPIC_COMMAND,
            1
        )) {

        Serial.println("[MQTT] Subscribe send failed");

        mqttClient.disconnect();

        return false;
    }

    Serial.println("[MQTT] Connected; subscribe sent");

    return true;
}

// 7. Initialize MQTT

void ClassroomMQTT::begin() {

    if (mqttReady) {
        return;
    }

    mqttConnected.store(false);

    if (MQTT_HOST[0] == '\0') {

        Serial.println(
            "[MQTT] MQTT_HOST not configured, MQTT disabled"
        );

        return;
    }

    mqttClient.setServer(
        MQTT_HOST,
        MQTT_PORT
    );

    mqttClient.setCallback(onMessage);

    if (!mqttClient.setBufferSize(
            CLIENT_BUFFER_BYTES
        )) {

        Serial.println("[MQTT] Buffer allocation failed");

        return;
    }

    mqttClient.setKeepAlive(15);

    mqttClient.setSocketTimeout(5);

    mqttReady = true;

    lastReconnectMs =
        millis() - MQTT_RECONNECT_MS;

    lastTelemetryMs = millis();

    Serial.println("[MQTT] Initialized");
}

// 8. Check connection state

bool ClassroomMQTT::isConnected() {
    return mqttConnected.load();
}

// 9. Publish telemetry

bool ClassroomMQTT::publishTelemetry() {

    if (
        !mqttReady ||
        !mqttConnected.load() ||
        WiFi.status() != WL_CONNECTED ||
        !mqttClient.connected() ||
        FirmwareOTA::isUpdating()
    ) {
        return false;
    }

    ClassroomData data =
        SystemData::getSnapshot();

    bool fresh =
        millis() - data.sensors.sampledAtMs
        <= TELEMETRY_STALE_MS;

    JsonDocument doc;

    doc["deviceId"] = DEVICE_ID;

    doc["ts"] = nullptr;

    // Temperature and humidity

    if (fresh && data.sensors.dhtValid) {

        doc["temperature"] =
            data.sensors.temperature;

        doc["humidity"] =
            data.sensors.humidity;
    }
    else {
        doc["temperature"] = nullptr;
        doc["humidity"] = nullptr;
    }

    // Light

    if (fresh && data.sensors.lightValid) {
        doc["light"] = data.sensors.light;
    }
    else {
        doc["light"] = nullptr;
    }

    // Motion

    if (fresh && data.sensors.motionValid) {
        doc["motion"] = data.sensors.motion;
    }
    else {
        doc["motion"] = nullptr;
    }

    // Distance

    if (fresh && data.sensors.distanceValid) {
        doc["distance"] = data.sensors.distance;
    }
    else {
        doc["distance"] = nullptr;
    }

    // Lamp state

    if (data.actuators.lampKnown) {
        doc["lamp"] = data.actuators.lamp;
    }
    else {
        doc["lamp"] = nullptr;
    }

    // Door state

    if (data.actuators.doorKnown) {
        doc["door"] = data.actuators.door;
    }
    else {
        doc["door"] = nullptr;
    }

    doc["fwVersion"] = FW_VERSION;
    doc["mockMode"] = MOCK_MODE;

    if (HAS_SERVO && HAS_ULTRASONIC) {
        doc["doorAuto"] = data.actuators.doorAuto;
    }

    return publishJson(
        MQTT_TOPIC_TELEMETRY,
        doc
    );
}

// 10. MQTT update

void ClassroomMQTT::update() {

    if (!mqttReady) {
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {

        mqttConnected.store(false);

        if (wifiWasConnected) {
            wifiClient.stop();
            wifiWasConnected = false;
        }

        return;
    }

    if (!wifiWasConnected) {

        wifiWasConnected = true;

        lastReconnectMs =
            millis() - MQTT_RECONNECT_MS;
    }

    unsigned long now = millis();

    if (!mqttClient.connected()) {

        mqttConnected.store(false);

        if (
            now - lastReconnectMs >= MQTT_RECONNECT_MS &&
            !FirmwareOTA::isUpdating()
        ) {

            bool ok = reconnect();

            lastReconnectMs = millis();

            if (ok) {

                mqttConnected.store(true);

                lastTelemetryMs =
                    millis() - MQTT_INTERVAL_MS;
            }
        }

        return;
    }

    if (
        !mqttClient.loop() ||
        !mqttClient.connected() ||
        WiFi.status() != WL_CONNECTED
    ) {

        mqttConnected.store(false);

        wifiClient.stop();

        return;
    }

    mqttConnected.store(true);

    now = millis();

    if (
        (reportAfterCommand || now - lastTelemetryMs >= MQTT_INTERVAL_MS) &&
        !FirmwareOTA::isUpdating()
    ) {

        lastTelemetryMs = now;

        if (publishTelemetry()) {
            reportAfterCommand = false;
        } else {
            Serial.println(
                "[MQTT] Telemetry publish failed"
            );
        }
    }
}
