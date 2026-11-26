
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
    else {
        if (!lampPixels.begin()) {
            return false;
        }

        lampPixels.setBrightness(50);
        lampPixels.clear();
        lampPixels.show();

        // Fan
        pinMode(FAN_PIN, OUTPUT);
        digitalWrite(FAN_PIN, LOW);

        pinMode(FAN_AUX_PIN, OUTPUT);
        digitalWrite(FAN_AUX_PIN, LOW);

        // Servo
        doorServo.setPeriodHertz(50);
        doorServo.attach(SERVO_PIN);

        if (!doorServo.attached()) {
            return false;
        }

        doorServo.write(DOOR_CLOSED_ANGLE);

        // LCD
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

        return true;
    }
}

// 2. Control lamp

bool Actuators::setLamp(bool state) {
    if (MOCK_MODE == true) {
        return true;
    }
    else {
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

        return true;
    }
}

// 3. Control fan

bool Actuators::setFan(bool state) {
    if (MOCK_MODE == true) {
        return true;
    }
    else {
        if (state == true) {
            digitalWrite(FAN_PIN, HIGH);
        }
        else {
            digitalWrite(FAN_PIN, LOW);
        }

        return true;
    }
}

// 4. Control door

bool Actuators::setDoor(bool state) {
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
    if (MOCK_MODE == true || lcdReady == false) {
        return;
    }

    char line1[LCD_COLS + 1];
    char line2[LCD_COLS + 1];

    if (data.sensors.dhtValid == true) {
        snprintf(
            line1,
            sizeof(line1),
            "T:%.1fC H:%.0f%%",
            data.sensors.temperature,
            data.sensors.humidity
        );
    }
    else {
        snprintf(
            line1,
            sizeof(line1),
            "DHT20 ERROR"
        );
    }

    auto stateChar = [](bool known, bool state) {
        return known ? (state ? '1' : '0') : '?';
    };

    snprintf(
        line2,
        sizeof(line2),
        "L:%c F:%c D:%c",
        stateChar(data.actuators.lampKnown, data.actuators.lamp),
        stateChar(data.actuators.fanKnown, data.actuators.fan),
        stateChar(data.actuators.doorKnown, data.actuators.door)
    );

    lcd.setCursor(0, 0);

    for (int i = 0; i < LCD_COLS; ++i) {
        lcd.write(
            i < (int)strlen(line1) ? line1[i] : ' '
        );
    }

    lcd.setCursor(0, 1);

    for (int i = 0; i < LCD_COLS; ++i) {
        lcd.write(
            i < (int)strlen(line2) ? line2[i] : ' '
        );
    }
}
