
#include "sensors.h"
#include "config.h"

#include <Arduino.h>
#include <Wire.h>
#include <DHT20.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <cmath>

#include "control_logic.h"

static DHT20 dht20;
static bool i2cReady = false;
static bool dhtReady = false;
static NearDoorTracker nearTracker;

static IRrecv irrecv(IR_PIN);
static decode_results results;

// 1. Initialize sensors


bool Sensors::begin() {
    if (MOCK_MODE == true) {
        return true;
    }

    if (HAS_PIR) {
        pinMode(PIR_PIN, INPUT);
    }

    if (HAS_LIGHT_SENSOR) {
        pinMode(LIGHT_PIN, INPUT);
        analogReadResolution(12);
    }

    if (HAS_ULTRASONIC) {
        pinMode(TRIG_PIN, OUTPUT);
        pinMode(ECHO_PIN, INPUT);

        digitalWrite(TRIG_PIN, LOW);
    }

    if (HAS_IR) {
        irrecv.enableIRIn();
    }

    if (HAS_DHT20 || HAS_LCD) {

        i2cReady = Wire.begin(
            I2C_SDA, I2C_SCL, 100000
        );

        if (!i2cReady) {
            Serial.println("[Sensors] WARNING: I2C init failed");
            return true;
        }

        delay(100);

        if (HAS_DHT20) {

            dhtReady = dht20.begin();

            if (!dhtReady) {
                Serial.println("[Sensors] WARNING: DHT20 not found");
            }
        }
    }

    return true;
}


// 2. Read temperature and humidity

bool Sensors::isI2CReady() {
    return i2cReady;
}

bool Sensors::readDHT20(float& temperature, float& humidity) {
    if (!HAS_DHT20) {
        return false;
    }
    if (MOCK_MODE == true) {
        temperature = 32.0f;
        humidity = 65.0f;

        return true;
    }
    else {
        if (!i2cReady) return false;

        if (!dhtReady) {
            dhtReady = dht20.begin();

            if (!dhtReady) return false;
        }

        int status = dht20.read();

        if (status != DHT20_OK) {
            dhtReady = false;
            return false;
        }

        temperature = dht20.getTemperature();
        humidity = dht20.getHumidity();

        return std::isfinite(temperature) &&
               std::isfinite(humidity) &&
               temperature >= -40.0f &&
               temperature <= 85.0f &&
               humidity >= 0.0f &&
               humidity <= 100.0f;
    }
}

// 3. Read light sensor

bool Sensors::readLight(int& light) {
    

    if (!HAS_LIGHT_SENSOR) {
        return false;
    }


    if (MOCK_MODE == true) {
        light = 850;
        return true;
    }
    else {
        light = analogRead(LIGHT_PIN);
        return true;
    }
}

// 4. Read motion sensor

bool Sensors::readMotion(bool& motion) {
    if (!HAS_PIR) {
        return false;
    }
    if (MOCK_MODE == true) {
        motion = true;
        return true;
    }
    else {
        motion = (digitalRead(PIR_PIN) == HIGH);
        return true;
    }
}

// 5. Read ultrasonic sensor

bool Sensors::readDistance(float& distance) {
    if (!HAS_ULTRASONIC) {
        return false;
    }

    if (MOCK_MODE == true) {
        distance = 10.0f;
        return true;
    }
    else {
        digitalWrite(TRIG_PIN, LOW);
        delayMicroseconds(2);

        digitalWrite(TRIG_PIN, HIGH);
        delayMicroseconds(10);

        digitalWrite(TRIG_PIN, LOW);

        unsigned long duration = pulseIn(
            ECHO_PIN,
            HIGH,
            ULTRASONIC_TIMEOUT_US
        );

        if (duration == 0) {
            return false;
        }

        float cm = (duration * 0.0343f) / 2.0f;

        if (cm < ULTRASONIC_MIN_CM ||
            cm > ULTRASONIC_MAX_CM) {
            return false;
        }

        distance = cm;

        return true;
    }
}

// 6. Read infrared remote

bool Sensors::readIR(uint64_t& code) {
    if (!HAS_IR) {
        return false;
    }
    if (MOCK_MODE == true) {
        return false;
    }
    else {
        if (!irrecv.decode(&results)) {
            return false;
        }

        if (results.overflow ||
            results.repeat ||
            results.decode_type == UNKNOWN ||
            hasACState(results.decode_type) ||
            results.bits > 64) {

            irrecv.resume();

            return false;
        }

        code = results.value;

        irrecv.resume();

        return true;
    }
}

// 7. Read all sensors


SensorData Sensors::read() {
    SensorData data;

    data.dhtValid = readDHT20(
        data.temperature,
        data.humidity
    );

    data.lightValid = readLight(data.light);
    data.motionValid = readMotion(data.motion);
    data.distanceValid = readDistance(data.distance);

    data.sampledAtMs = millis();

    // Optional changing mock data
    if (MOCK_MODE && MOCK_CYCLE) {

        bool hot = (data.sampledAtMs / 40000UL) % 2 == 0;

        if (data.dhtValid) {
            data.temperature = hot ? 32.0f : 27.0f;
            data.humidity = hot ? 65.0f : 55.0f;
        }

        if (data.lightValid) {
            data.light = hot ? 850 : 1300;
        }

        if (data.motionValid) {
            data.motion = hot;
        }

        if (data.distanceValid) {
            data.distance = hot ? 10.0f : 40.0f;
        }
    }

    // Near-door event tracking
    if (nearTracker.observe(
            data.distanceValid,
            data.distance,
            data.sampledAtMs,
            DOOR_DISTANCE_CM,
            DOOR_CLOSE_DISTANCE_CM)) {

        Serial.printf(
            "[Door] Near event #%lu\n",
            (unsigned long)nearTracker.count
        );
    }

    data.nearDoorCount = nearTracker.count;
    data.lastNearDoorAtMs = nearTracker.lastAt;

    return data;
}
