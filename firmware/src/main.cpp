
#include <Arduino.h>
#include <WiFi.h>
#include <atomic>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "config.h"
#include "system_data.h"
#include "sensors.h"
#include "actuators.h"
#include "automation.h"
#include "web_server.h"
#include "mqtt_client.h"
#include "ota.h"

// ==================================================
// 0. STARTUP SYNCHRONIZATION
// ==================================================

static std::atomic<bool> startupReady{false};

static void waitForStartup() {

    while (!startupReady.load()) {

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

// ==================================================
// 1. SENSOR TASK
// ==================================================

static void sensorTask(void* parameter) {
    (void)parameter;

    waitForStartup();

    while (true) {

        if (FirmwareOTA::isUpdating()) {

            vTaskDelay(pdMS_TO_TICKS(100));

            continue;
        }

        SensorData sensors = Sensors::read();

        SystemData::updateSensors(sensors);

        ClassroomData data =
            SystemData::getSnapshot();

        Actuators::updateLCD(data);

        if (MOCK_MODE && MOCK_SERIAL_LOG) {

            Serial.printf(
                "[Mock] T=%.1f H=%.1f Light=%d Motion=%d "
                "D=%.1f L=%d F=%d Door=%d Events=%lu\n",

                data.sensors.temperature,
                data.sensors.humidity,
                data.sensors.light,
                (int)data.sensors.motion,
                data.sensors.distance,
                (int)data.actuators.lamp,
                (int)data.actuators.fan,
                (int)data.actuators.door,
                (unsigned long)data.sensors.nearDoorCount
            );
        }

        vTaskDelay(
            pdMS_TO_TICKS(SENSOR_INTERVAL_MS)
        );
    }
}

// ==================================================
// 2. AUTOMATION TASK
// ==================================================

static void automationTask(void* parameter) {
    (void)parameter;

    waitForStartup();

    unsigned long lastAutomationMs =
        millis() - AUTOMATION_INTERVAL_MS;

    while (true) {

        unsigned long now = millis();

        if (
            now - lastAutomationMs >=
            AUTOMATION_INTERVAL_MS
        ) {

            lastAutomationMs = now;

            Automation::update();
        }

        uint64_t code = 0;

        if (Sensors::readIR(code)) {

            Automation::handleIR(code);
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// ==================================================
// 3. NETWORK TASK
// ==================================================

static void networkTask(void* parameter) {
    (void)parameter;

    waitForStartup();

    bool webStarted = false;

    bool wasConnected = false;

    unsigned long disconnectedSinceMs =
        millis();

    while (true) {

        if (WiFi.status() == WL_CONNECTED) {

            // Print IP after WiFi connects

            if (wasConnected == false) {

                wasConnected = true;

                Serial.print("WiFi connected, IP: ");

                Serial.println(WiFi.localIP());
            }

            // Initialize Web Server once

            if (webStarted == false) {

                LocalWeb::begin();

                webStarted = true;
            }

            // Initialize OTA if configured

            if (OTA_PASSWORD[0] != '\0') {

                FirmwareOTA::begin();
            }

            LocalWeb::update();

            FirmwareOTA::update();
        }
        else {

            unsigned long now = millis();

            if (wasConnected == true) {

                wasConnected = false;

                disconnectedSinceMs = now;

                Serial.println("WiFi disconnected");
            }

            // Reconnect fallback

            if (
                WIFI_SSID[0] != '\0' &&
                now - disconnectedSinceMs >=
                WIFI_TIMEOUT_MS
            ) {

                disconnectedSinceMs = now;

                Serial.println("WiFi reconnecting...");

                WiFi.reconnect();
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// ==================================================
// 4. MQTT TASK
// ==================================================

static void mqttTask(void* parameter) {
    (void)parameter;

    waitForStartup();

    ClassroomMQTT::begin();

    while (true) {

        ClassroomMQTT::update();

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// ==================================================
// 5. SETUP
// ==================================================

void setup() {

    // Serial initialization

    Serial.begin(SERIAL_BAUD_RATE);

    unsigned long serialStartMs =
        millis();

    while (
        !Serial &&
        millis() - serialStartMs < 3000
    ) {

        delay(10);
    }

    Serial.println("================================");

    Serial.println("Smart Classroom Starting...");

    Serial.println("================================");

    Serial.print("Device ID: ");

    Serial.println(DEVICE_ID);

    Serial.print("Firmware version: ");

    Serial.println(FW_VERSION);

    Serial.print("Mock mode: ");

    Serial.println(MOCK_MODE ? "ON" : "OFF");

    // SystemData

    if (!SystemData::begin()) {

        Serial.println("SystemData init failed");

        return;
    }

    Serial.println("SystemData initialized");

    // Sensors

    if (!Sensors::begin()) {

        Serial.println("Sensors init failed");

        return;
    }

    Serial.println("Sensors initialized");

    // Actuators

    if (!Actuators::begin()) {

        Serial.println("Actuators init failed");

        return;
    }

    Serial.println("Actuators initialized");

    // Automation

    if (!Automation::begin()) {

        Serial.println("Automation init failed");

        return;
    }

    Serial.println("Automation initialized");

    // WiFi configuration

    WiFi.mode(WIFI_STA);

    WiFi.setAutoReconnect(true);

    if (WIFI_SSID[0] != '\0') {

        WiFi.begin(
            WIFI_SSID,
            WIFI_PASSWORD
        );

        Serial.println("Connecting to WiFi...");
    }
    else {

        Serial.println("WiFi SSID not configured");
    }

    // Create FreeRTOS tasks

    bool allTasksCreated = true;

    // Sensor Task

    if (
        xTaskCreate(
            sensorTask,
            "SensorTask",
            4096,
            nullptr,
            1,
            nullptr
        ) != pdPASS
    ) {

        Serial.println(
            "Sensor Task creation failed"
        );

        allTasksCreated = false;
    }
    else {

        Serial.println("Sensor Task created");
    }

    // Automation Task

    if (
        xTaskCreate(
            automationTask,
            "AutomationTask",
            4096,
            nullptr,
            2,
            nullptr
        ) != pdPASS
    ) {

        Serial.println(
            "Automation Task creation failed"
        );

        allTasksCreated = false;
    }
    else {

        Serial.println("Automation Task created");
    }

    // Network Task

    if (
        xTaskCreate(
            networkTask,
            "NetworkTask",
            8192,
            nullptr,
            1,
            nullptr
        ) != pdPASS
    ) {

        Serial.println(
            "Network Task creation failed"
        );

        allTasksCreated = false;
    }
    else {

        Serial.println("Network Task created");
    }

    // MQTT Task

    if (
        xTaskCreate(
            mqttTask,
            "MQTTTask",
            8192,
            nullptr,
            1,
            nullptr
        ) != pdPASS
    ) {

        Serial.println(
            "MQTT Task creation failed"
        );

        allTasksCreated = false;
    }
    else {

        Serial.println("MQTT Task created");
    }

    // Complete startup

    Serial.println("================================");

    if (allTasksCreated) {

        startupReady.store(true);

        Serial.println("Smart Classroom Ready!");
    }
    else {

        Serial.println(
            "System startup incomplete! "
            "Tasks remain blocked until reboot."
        );
    }

    Serial.println("================================");
}

// ==================================================
// 6. LOOP
// ==================================================

void loop() {

    vTaskDelay(pdMS_TO_TICKS(1000));
}
