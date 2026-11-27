
#include "ota.h"
#include "config.h"
#include "automation.h"

#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <atomic>

static bool otaReady = false;

static std::atomic<bool> otaUpdating{false};

// 1. Initialize OTA

void FirmwareOTA::begin() {
#if defined(SMART_CLASSROOM_COREIOT_OTA)
    CoreIotOTA::begin();
    return;
#endif
    if (otaReady == true) {
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {
        return;
    }

    if (OTA_PASSWORD[0] == '\0') {
        Serial.println("OTA password not configured");
        return;
    }

    ArduinoOTA.setHostname(DEVICE_ID);
    ArduinoOTA.setPort(OTA_PORT);
    ArduinoOTA.setPassword(OTA_PASSWORD);

    // OTA starts
    ArduinoOTA.onStart([]() {

        if (!startUpdate()) {
            Serial.println("OTA could not set outputs to their safe state");
        }

        Serial.println("OTA update started");

    });

    // OTA completed
    ArduinoOTA.onEnd([]() {

        Serial.println("OTA update completed");

    });

    // OTA progress
    ArduinoOTA.onProgress([](
        unsigned int progress,
        unsigned int total
    ) {
        if (total == 0) {
            return;
        }

        unsigned int percent =
            static_cast<uint64_t>(progress) * 100 / total;

        Serial.printf(
            "OTA Progress: %u%%\n",
            percent
        );
    });

    // OTA error
    ArduinoOTA.onError([](ota_error_t error) {

        finishUpdate();

        Serial.printf(
            "OTA Error: %u\n",
            static_cast<unsigned int>(error)
        );

    });

    ArduinoOTA.begin();

    otaReady = true;

    Serial.println("OTA initialized");
}

// 2. Process OTA

void FirmwareOTA::update() {
    if (otaReady == false ||
        WiFi.status() != WL_CONNECTED) {

        return;
    }

    ArduinoOTA.handle();
}

// 3. Check OTA status

bool FirmwareOTA::isUpdating() {
    return otaUpdating.load();
}

bool FirmwareOTA::startUpdate() {
    otaUpdating.store(true);
    if (Automation::prepareForUpdate()) {
        return true;
    }
    otaUpdating.store(false);
    return false;
}

void FirmwareOTA::finishUpdate() {
    otaUpdating.store(false);
}
