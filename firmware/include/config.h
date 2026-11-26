
#pragma once

#include <stdint.h>

// 0. SECRETS

#if __has_include("secrets.h")
#include "secrets.h"
#else
constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";
constexpr char MQTT_HOST[] = "";
constexpr char OTA_PASSWORD[] = "";
#endif

// 1. SYSTEM CONFIGURATION

constexpr bool MOCK_MODE = true;
constexpr bool MOCK_CYCLE = false;
constexpr bool MOCK_SERIAL_LOG = true;
constexpr bool MQTT_EXTENDED_SCHEMA = false;

constexpr char FW_VERSION[] = "1.0.0";
constexpr char DEVICE_ID[] = "classroom-node-01";

constexpr unsigned long SERIAL_BAUD_RATE = 115200;

// 2. ONBOARD LED CONFIGURATION

constexpr int LED_PIN = 48;
constexpr int NEO_PIN = 45;
constexpr int LED_COUNT = 1;

// 3. I2C CONFIGURATION

constexpr int I2C_SDA = 11;
constexpr int I2C_SCL = 12;

constexpr int DHT20_ADDRESS = 0x38;

constexpr int LCD_ADDRESS = 0x21;
constexpr int LCD_COLS = 16;
constexpr int LCD_ROWS = 2;

// 4. SENSOR PIN CONFIGURATION

constexpr int LIGHT_PIN = 1;
constexpr int PIR_PIN = 10;

constexpr int TRIG_PIN = 6;
constexpr int ECHO_PIN = 7;

constexpr int IR_PIN = 4;

// 5. ACTUATOR PIN CONFIGURATION

constexpr int LAMP_PIN = 18;
constexpr int LAMP_LED_COUNT = 4;

constexpr int FAN_PIN = 8;
constexpr int FAN_AUX_PIN = 9;

constexpr int SERVO_PIN = 5;

constexpr int DOOR_CLOSED_ANGLE = 0;
constexpr int DOOR_OPEN_ANGLE = 90;

// 6. AUTOMATION THRESHOLDS

constexpr float TEMP_FAN_ON = 30.0f;
constexpr float TEMP_FAN_OFF = 28.0f;

constexpr float TEMP_WARNING = 35.0f;
constexpr float TEMP_DANGER = 40.0f;

constexpr float HUMIDITY_WARNING = 60.0f;
constexpr float HUMIDITY_DANGER = 70.0f;

constexpr int LIGHT_DARK_THRESHOLD = 1000;
constexpr int LIGHT_BRIGHT_THRESHOLD = 1200;

constexpr float DOOR_DISTANCE_CM = 15.0f;
constexpr float DOOR_CLOSE_DISTANCE_CM = 25.0f;

constexpr unsigned long DOOR_HOLD_MS = 5000;

constexpr float ULTRASONIC_MIN_CM = 2.0f;
constexpr float ULTRASONIC_MAX_CM = 400.0f;

constexpr unsigned long MOTION_TIMEOUT_MS = 30000;

// 7. TIMING CONFIGURATION

constexpr unsigned long SENSOR_INTERVAL_MS = 2000;
constexpr unsigned long AUTOMATION_INTERVAL_MS = 200;
constexpr unsigned long LCD_INTERVAL_MS = 2000;
constexpr unsigned long MQTT_INTERVAL_MS = 5000;

constexpr unsigned long SENSOR_STALE_MS =
    3 * SENSOR_INTERVAL_MS;

constexpr unsigned long WIFI_TIMEOUT_MS = 10000;
constexpr unsigned long MQTT_RECONNECT_MS = 5000;

constexpr unsigned long ULTRASONIC_TIMEOUT_US = 30000;

// 8. WEB SERVER CONFIGURATION

constexpr int WEB_SERVER_PORT = 80;

// 9. MQTT CONFIGURATION

constexpr int MQTT_PORT = 1883;
constexpr int MQTT_BUFFER_SIZE = 1024;

constexpr char MQTT_TOPIC_TELEMETRY[] =
    "classroom/node/telemetry";

constexpr char MQTT_TOPIC_COMMAND[] =
    "classroom/node/cmd";

constexpr char MQTT_TOPIC_ACK[] =
    "classroom/node/ack";

// 10. OTA CONFIGURATION

constexpr int OTA_PORT = 3232;

// 11. IR REMOTE CODES

constexpr uint64_t IR_BTN_LAMP_ON = 0;
constexpr uint64_t IR_BTN_LAMP_OFF = 0;
constexpr uint64_t IR_BTN_LAMP_AUTO = 0;

constexpr uint64_t IR_BTN_FAN_ON = 0;
constexpr uint64_t IR_BTN_FAN_OFF = 0;
constexpr uint64_t IR_BTN_FAN_AUTO = 0;

constexpr uint64_t IR_BTN_DOOR_OPEN = 0;
constexpr uint64_t IR_BTN_DOOR_CLOSE = 0;
constexpr uint64_t IR_BTN_DOOR_AUTO = 0;

constexpr unsigned long IR_DEBOUNCE_MS = 300;
