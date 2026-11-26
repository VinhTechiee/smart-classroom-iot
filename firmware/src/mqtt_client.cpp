
#include "mqtt_client.h"
#include "config.h"
#include "system_data.h"
#include "automation.h"
#include "ota.h"

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
    ack["actualState"] = result.actualState;
    ack["stateKnown"] = result.stateKnown;
    ack["ts"] = millis();

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
    else if (strcmp(method, "setFan") == 0) {
        target = ControlTarget::Fan;
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

    ControlTarget target = ControlTarget::Lamp;

    // Optional extended MQTT schema

    if (
        MQTT_EXTENDED_SCHEMA &&
        method.size() == 7 &&
        strcmp(method.c_str(), "setMode") == 0
    ) {

        JsonString targetName =
            cmd["target"].as<JsonString>();

        const char* name = targetName.c_str();

        if (
            name &&
            memchr(
                name,
                '\0',
                targetName.size()
            ) != nullptr
        ) {
            name = nullptr;
        }

        bool validTarget = false;

        if (name && strcmp(name, "lamp") == 0) {
            target = ControlTarget::Lamp;
            validTarget = true;
        }
        else if (name && strcmp(name, "fan") == 0) {
            target = ControlTarget::Fan;
            validTarget = true;
        }
        else if (name && strcmp(name, "door") == 0) {
            target = ControlTarget::Door;
            validTarget = true;
        }

        if (
            !validTarget ||
            !cmd["value"].is<bool>() ||
            FirmwareOTA::isUpdating()
        ) {

            publishAck(
                id,
                failed,
                "invalid mode request or OTA active"
            );

            return;
        }

        ControlResult modeResult;

        modeResult.ok = Automation::setAutomatic(
            target,
            cmd["value"].as<bool>()
        );

        ClassroomData snapshot =
            SystemData::getSnapshot();

        if (target == ControlTarget::Lamp) {

            modeResult.actualState =
                snapshot.actuators.lamp;

            modeResult.stateKnown =
                snapshot.actuators.lampKnown;
        }
        else if (target == ControlTarget::Fan) {

            modeResult.actualState =
                snapshot.actuators.fan;

            modeResult.stateKnown =
                snapshot.actuators.fanKnown;
        }
        else {

            modeResult.actualState =
                snapshot.actuators.door;

            modeResult.stateKnown =
                snapshot.actuators.doorKnown;
        }

        publishAck(
            id,
            modeResult,
            modeResult.ok ? nullptr : "mode change failed"
        );

        return;
    }

    // Original command schema

    if (
        method.size() == 0 ||
        memchr(
            method.c_str(),
            '\0',
            method.size()
        ) != nullptr ||
        !parseMethod(method.c_str(), target)
    ) {
        publishAck(
            id,
            failed,
            "unknown method"
        );

        return;
    }

    if (!cmd["value"].is<bool>()) {

        publishAck(
            id,
            failed,
            "value must be boolean"
        );

        return;
    }

    bool value = cmd["value"].as<bool>();

    if (FirmwareOTA::isUpdating()) {

        publishAck(
            id,
            failed,
            "OTA in progress"
        );

        return;
    }

    ControlResult result =
        Automation::applyManualCommand(
            target,
            value,
            ControlSource::MQTT
        );

    publishAck(
        id,
        result,
        result.ok ? nullptr : "control failed"
    );
}

// 6. Reconnect MQTT broker

static bool reconnect() {

    Serial.printf(
        "[MQTT] Connecting to %s:%d\n",
        MQTT_HOST,
        MQTT_PORT
    );

    if (!mqttClient.connect(DEVICE_ID)) {

        Serial.printf(
            "[MQTT] Connect failed: %d\n",
            mqttClient.state()
        );

        return false;
    }

    if (!mqttClient.subscribe(
            MQTT_TOPIC_COMMAND,
            0
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

    doc["ts"] = data.sensors.sampledAtMs;

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

    // Fan state

    if (data.actuators.fanKnown) {
        doc["fan"] = data.actuators.fan;
    }
    else {
        doc["fan"] = nullptr;
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

    // Extended telemetry schema

    if (MQTT_EXTENDED_SCHEMA) {

        doc["lampAuto"] =
            data.actuators.lampAuto;

        doc["fanAuto"] =
            data.actuators.fanAuto;

        doc["doorAuto"] =
            data.actuators.doorAuto;

        doc["nearDoorCount"] =
            data.sensors.nearDoorCount;

        doc["lastNearDoorAtMs"] =
            data.sensors.lastNearDoorAtMs;
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
        now - lastTelemetryMs >= MQTT_INTERVAL_MS &&
        !FirmwareOTA::isUpdating()
    ) {

        lastTelemetryMs = now;

        if (!publishTelemetry()) {

            Serial.println(
                "[MQTT] Telemetry publish failed"
            );
        }
    }
}
