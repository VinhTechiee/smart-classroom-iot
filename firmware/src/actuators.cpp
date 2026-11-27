
#include "actuators.h"
#include "config.h"
#include "sensors.h"

#include <Arduino.h>
#include <cstring>
#include <cstdio>
#include <Wire.h>
#include <Adafruit_NeoPixel.h>
#include <ESP32Servo.h>
#include <LiquidCrystal_I2C.h>

static Adafruit_NeoPixel lampPixels(
    LAMP_LED_COUNT,
    LAMP_PIN,
    NEO_GRB + NEO_KHZ800
);
static Adafruit_NeoPixel onboardPixels(
    LED_COUNT,
    NEO_PIN,
    NEO_GRB + NEO_KHZ800
);

static Servo doorServo;

static LiquidCrystal_I2C lcd(
    LCD_ADDRESS,
    LCD_COLS,
    LCD_ROWS
);

static bool lcdReady = false;

// 1. Initialize actuators


bool Actuators::begin() {
    if (MOCK_MODE == true) {
        return true;
    }

    // External lamp
    if (HAS_EXTERNAL_LAMP) {
        if (!lampPixels.begin()) {
            return false;
        }

        lampPixels.setBrightness(50);
        lampPixels.clear();
        lampPixels.show();
    }

    // Onboard RGB
    if (HAS_ONBOARD_RGB) {
        if (!onboardPixels.begin()) {
            return false;
        }

        onboardPixels.setBrightness(
    LED_COUNT > 1 ? 15 : 50
);
        onboardPixels.clear();
        onboardPixels.show();
    }

    // Onboard LED
    if (HAS_ONBOARD_LED) {
        pinMode(LED_PIN, OUTPUT);
        digitalWrite(LED_PIN, LED_ACTIVE_HIGH ? LOW : HIGH);
    }

    // Servo
    if (HAS_SERVO) {
        doorServo.setPeriodHertz(50);
        doorServo.attach(SERVO_PIN);

        if (!doorServo.attached()) {
            return false;
        }

        doorServo.write(DOOR_CLOSED_ANGLE);
    }

    // LCD
    if (HAS_LCD) {
        if (!Sensors::isI2CReady()) {
            Serial.println(
                "[Actuators] WARNING: LCD skipped, I2C unavailable"
            );
            return true;
        }

        Wire.beginTransmission(LCD_ADDRESS);

        if (Wire.endTransmission() != 0) {
            Serial.println(
                "[Actuators] WARNING: LCD not found"
            );
            return true;
        }

        lcdReady = true;

        lcd.init();
        lcd.backlight();
        lcd.clear();

        lcd.setCursor(0, 0);
        lcd.print("Smart Classroom");

        lcd.setCursor(0, 1);
        lcd.print("System Ready");
    }

    return true;
}


// 2. Control lamp


bool Actuators::setLamp(bool state) {

    if (!HAS_EXTERNAL_LAMP && !HAS_ONBOARD_LED) {
        return false;
    }

    if (MOCK_MODE == true) {
        return true;
    }

    if (HAS_EXTERNAL_LAMP) {
        if (state == true) {
            for (int i = 0; i < LAMP_LED_COUNT; i++) {
                lampPixels.setPixelColor(
                    i, 255, 255, 255
                );
            }
        }
        else {
            lampPixels.clear();
        }

        lampPixels.show();
    }

    if (HAS_ONBOARD_LED) {
        digitalWrite(
            LED_PIN,
            state == LED_ACTIVE_HIGH ? HIGH : LOW
        );
    }

    return true;
}


// 4. Control door

bool Actuators::setDoor(bool state) {
    if (!HAS_SERVO) {
        return false;
    }
    if (MOCK_MODE == true) {
        return true;
    }
    else {
        if (!doorServo.attached()) {
            return false;
        }

        if (state == true) {
            doorServo.write(DOOR_OPEN_ANGLE);
        }
        else {
            doorServo.write(DOOR_CLOSED_ANGLE);
        }

        return true;
    }
}

// 5. Update LCD

void Actuators::updateLCD(const ClassroomData& data) {
    if (!HAS_LCD) {
        return;
    }
    if (MOCK_MODE == true || lcdReady == false) {
        return;
    }

    static unsigned long lastPageMs = 0;
    static bool displayed = false;
    static uint8_t page = 0;
    const unsigned long now = millis();
    if (displayed && now - lastPageMs < LCD_INTERVAL_MS) return;
    displayed = true;
    lastPageMs = now;

    char first[LCD_COLS + 1]{};
    char second[LCD_COLS + 1]{};
    const bool fresh = now - data.sensors.sampledAtMs <= SENSOR_STALE_MS;
    const auto& sensors = data.sensors;
    switch (page) {
        case 0:
            if (fresh && sensors.dhtValid) {
                snprintf(first, sizeof(first), "Temp: %.1f C", sensors.temperature);
                snprintf(second, sizeof(second), "RH: %.1f %%", sensors.humidity);
            } else {
                snprintf(first, sizeof(first), "Temp: N/A");
                snprintf(second, sizeof(second), "RH: N/A");
            }
            break;
        case 1:
            if (fresh && sensors.lightValid) {
                snprintf(first, sizeof(first), "Light: %d", sensors.light);
            } else {
                snprintf(first, sizeof(first), "Light: N/A");
            }
            snprintf(second, sizeof(second), "Motion: %s",
                !fresh || !sensors.motionValid ? "N/A" : sensors.motion ? "YES" : "NO");
            break;
        case 2:
            if (fresh && sensors.distanceValid) {
                snprintf(first, sizeof(first), "Dist: %.1f cm", sensors.distance);
            } else {
                snprintf(first, sizeof(first), "Distance: N/A");
            }
            snprintf(second, sizeof(second), "Door: %s", !data.actuators.doorKnown ? "N/A" :
                data.actuators.door ? "OPEN" : "CLOSED");
            break;
    }
    const char* rows[] = {first, second};
    for (int row = 0; row < LCD_ROWS; ++row) {
        lcd.setCursor(0, row);
        const size_t length = strlen(rows[row]);
        for (size_t col = 0; col < LCD_COLS; ++col) {
            lcd.write(col < length ? rows[row][col] : ' ');
        }
    }
    page = (page + 1) % 3;
}


void Actuators::updateWarningLED(const ClassroomData& data) {

    if (!HAS_ONBOARD_RGB || MOCK_MODE) {
        return;
    }

    uint32_t color;

    if (!data.sensors.dhtValid ||
        millis() - data.sensors.sampledAtMs > SENSOR_STALE_MS) {

        // Blue: sensor data unavailable
        color = onboardPixels.Color(0, 0, 255);
    }
    else if (
        data.sensors.temperature >= TEMP_DANGER ||
        data.sensors.humidity >= HUMIDITY_DANGER
    ) {

        // Red: danger
        color = onboardPixels.Color(255, 0, 0);
    }
    else if (
        data.sensors.temperature >= TEMP_WARNING ||
        data.sensors.humidity >= HUMIDITY_WARNING
    ) {

        // Yellow: warning
        color = onboardPixels.Color(255, 255, 0);
    }
    else {

        // Green: normal
        color = onboardPixels.Color(0, 255, 0);
    }

    for (int i = 0; i < LED_COUNT; i++) {

        onboardPixels.setPixelColor(i, color);
    }

    onboardPixels.show();
}


