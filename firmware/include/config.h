
#pragma once

#include <stdint.h>

#if __has_include("config.local.h")
#include "config.local.h"
#endif

// 0. SECRETS

#if defined(SMART_CLASSROOM_COREIOT_OTA)
extern char WIFI_SSID[33];
extern char WIFI_PASSWORD[65];
extern char MQTT_HOST[128];
extern char MQTT_USERNAME[65];
extern char MQTT_PASSWORD[129];
constexpr char OTA_PASSWORD[] = "";
void loadLabNetworkSettings();
#elif __has_include("secrets.h")
#include "secrets.h"
#else
constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";
constexpr char MQTT_HOST[] = "";
constexpr char OTA_PASSWORD[] = "";
#endif
#if !defined(SMART_CLASSROOM_COREIOT_OTA)
#ifndef SMART_CLASSROOM_MQTT_USERNAME
#define SMART_CLASSROOM_MQTT_USERNAME ""
#endif
#ifndef SMART_CLASSROOM_MQTT_PASSWORD
#define SMART_CLASSROOM_MQTT_PASSWORD ""
#endif
constexpr char MQTT_USERNAME[] = SMART_CLASSROOM_MQTT_USERNAME;
constexpr char MQTT_PASSWORD[] = SMART_CLASSROOM_MQTT_PASSWORD;
#endif

#ifndef SMART_CLASSROOM_FW_VERSION
#define SMART_CLASSROOM_FW_VERSION "1.0.0"
#endif
constexpr char FW_VERSION[] = SMART_CLASSROOM_FW_VERSION;

#ifndef SMART_CLASSROOM_DEVICE_ID
#if defined(SMART_CLASSROOM_COREIOT_OTA)
#define SMART_CLASSROOM_DEVICE_ID "classroom-ota-board"
#elif defined(SMART_CLASSROOM_YOLOBIT)
#define SMART_CLASSROOM_DEVICE_ID "classroom-yolobit"
#else
#define SMART_CLASSROOM_DEVICE_ID "classroom-01"
#endif
#endif
constexpr char DEVICE_ID[] = SMART_CLASSROOM_DEVICE_ID;

#ifndef SMART_CLASSROOM_NTP_HOST
#define SMART_CLASSROOM_NTP_HOST "pool.ntp.org"
#endif
constexpr char NTP_HOST[] = SMART_CLASSROOM_NTP_HOST;

constexpr unsigned long SERIAL_BAUD_RATE = 115200;

// 1. SYSTEM CONFIGURATION

#ifndef SMART_CLASSROOM_MOCK_MODE
#define SMART_CLASSROOM_MOCK_MODE 0
#endif
constexpr bool MOCK_MODE = SMART_CLASSROOM_MOCK_MODE;
#if defined(SMART_CLASSROOM_COREIOT_OTA)
static_assert(!MOCK_MODE, "CoreIOT OTA requires genuine hardware acquisition");
#endif
#ifndef SMART_CLASSROOM_LIGHT_POLARITY
#define SMART_CLASSROOM_LIGHT_POLARITY 0
#endif
constexpr int LIGHT_POLARITY = SMART_CLASSROOM_LIGHT_POLARITY;
static_assert(LIGHT_POLARITY >= -1 && LIGHT_POLARITY <= 1, "Choose 0 for CoreIOT ownership or +1/-1 after ADC calibration");
constexpr bool MOCK_CYCLE = false;
constexpr bool MOCK_SERIAL_LOG = true;
// HARDWARE CONFIGURATION

#if defined(SMART_CLASSROOM_YOLOBIT)

constexpr bool HAS_DHT20 = true;
constexpr bool HAS_ONBOARD_RGB = true;
constexpr bool HAS_ONBOARD_LED = false;

constexpr bool HAS_EXTERNAL_LAMP = false;
constexpr bool HAS_LIGHT_SENSOR = true;
constexpr bool HAS_PIR = false;
constexpr bool HAS_ULTRASONIC = true;
constexpr bool HAS_IR = false;

constexpr bool HAS_SERVO = true;
constexpr bool HAS_LCD = true;
constexpr bool DOOR_AUTO_AT_BOOT = false;

#else

constexpr bool HAS_DHT20 = true;
constexpr bool HAS_ONBOARD_RGB = true;
constexpr bool HAS_ONBOARD_LED = true;

constexpr bool HAS_EXTERNAL_LAMP = false;
constexpr bool HAS_LIGHT_SENSOR = true;
constexpr bool HAS_PIR = true;
constexpr bool HAS_ULTRASONIC = true;
constexpr bool HAS_IR = false;

constexpr bool HAS_SERVO = true;
constexpr bool HAS_LCD = true;

constexpr bool DOOR_AUTO_AT_BOOT = true;

#endif

// 2. ONBOARD LED CONFIGURATION


// 2. HARDWARE PIN CONFIGURATION

#if defined(SMART_CLASSROOM_YOLOBIT)

// Yolo:Bit onboard LED matrix

constexpr int LED_PIN = -1;
constexpr int NEO_PIN = 4;
constexpr int LED_COUNT = 25;

// I2C: P20 and P19

constexpr int I2C_SDA = 21;
constexpr int I2C_SCL = 22;

// Sensors

constexpr int LIGHT_PIN = 32; // P0
constexpr int TRIG_PIN = 26;  // P10
constexpr int ECHO_PIN = 18;  // P13

// Reserved for future sensors
constexpr int PIR_PIN = 27;   // P2
constexpr int IR_PIN = 33;    // P1

// Actuators

constexpr int LAMP_PIN = 19;  // P14
constexpr int SERVO_PIN = 15; // P4


#else

// YoloUNO onboard LED

#ifndef SMART_CLASSROOM_UNO_LED
#define SMART_CLASSROOM_UNO_LED 48
#endif
constexpr int LED_PIN = SMART_CLASSROOM_UNO_LED;
#ifndef SMART_CLASSROOM_UNO_RGB
#define SMART_CLASSROOM_UNO_RGB 45
#endif
constexpr int NEO_PIN = SMART_CLASSROOM_UNO_RGB;
constexpr int LED_COUNT = 1;

// I2C

#ifndef SMART_CLASSROOM_UNO_SDA
#define SMART_CLASSROOM_UNO_SDA 11
#endif
constexpr int I2C_SDA = SMART_CLASSROOM_UNO_SDA;
#ifndef SMART_CLASSROOM_UNO_SCL
#define SMART_CLASSROOM_UNO_SCL 12
#endif
constexpr int I2C_SCL = SMART_CLASSROOM_UNO_SCL;

// Sensors

#ifndef SMART_CLASSROOM_UNO_LIGHT
#define SMART_CLASSROOM_UNO_LIGHT 1
#endif
constexpr int LIGHT_PIN = SMART_CLASSROOM_UNO_LIGHT;
#ifndef SMART_CLASSROOM_UNO_PIR
#define SMART_CLASSROOM_UNO_PIR 10
#endif
constexpr int PIR_PIN = SMART_CLASSROOM_UNO_PIR;

#ifndef SMART_CLASSROOM_UNO_TRIG
#define SMART_CLASSROOM_UNO_TRIG 6
#endif
constexpr int TRIG_PIN = SMART_CLASSROOM_UNO_TRIG;
#ifndef SMART_CLASSROOM_UNO_ECHO
#define SMART_CLASSROOM_UNO_ECHO 7
#endif
constexpr int ECHO_PIN = SMART_CLASSROOM_UNO_ECHO;

constexpr int IR_PIN = 4;

// Actuators

constexpr int LAMP_PIN = 18;

#ifndef SMART_CLASSROOM_UNO_SERVO
#define SMART_CLASSROOM_UNO_SERVO 5
#endif
constexpr int SERVO_PIN = SMART_CLASSROOM_UNO_SERVO;

constexpr bool usableUnoExternalPin(int pin) {
    return (pin >= 1 && pin <= 18 && pin != 3) || pin == 21 ||
        (pin >= 38 && pin <= 42) || pin == 47;
}
constexpr int UNO_ACTIVE_PINS[] = {I2C_SDA, I2C_SCL, LIGHT_PIN, PIR_PIN, TRIG_PIN, ECHO_PIN, SERVO_PIN, LED_PIN, NEO_PIN};
constexpr bool uniqueUnoPins(unsigned i = 0, unsigned j = 1) {
    return i == 8 || (j == 9 ? uniqueUnoPins(i + 1, i + 2) :
        UNO_ACTIVE_PINS[i] != UNO_ACTIVE_PINS[j] && uniqueUnoPins(i, j + 1));
}
static_assert(usableUnoExternalPin(I2C_SDA) && usableUnoExternalPin(I2C_SCL) &&
    usableUnoExternalPin(PIR_PIN) && usableUnoExternalPin(TRIG_PIN) &&
    usableUnoExternalPin(ECHO_PIN) && usableUnoExternalPin(SERVO_PIN), "Check Yolo UNO external pin assignments");
static_assert(LIGHT_PIN >= 1 && LIGHT_PIN <= 10 && LIGHT_PIN != 3, "Use an ADC1 pin for the light sensor");
static_assert(uniqueUnoPins(), "Yolo UNO active pins must be distinct");

#endif

// Shared hardware configuration

constexpr int DHT20_ADDRESS = 0x38;

#ifndef SMART_CLASSROOM_LCD_ADDRESS
#define SMART_CLASSROOM_LCD_ADDRESS 0x21
#endif
constexpr int LCD_ADDRESS = SMART_CLASSROOM_LCD_ADDRESS;
static_assert(LCD_ADDRESS >= 0x08 && LCD_ADDRESS <= 0x77 && LCD_ADDRESS != DHT20_ADDRESS,
    "Set a distinct 7-bit LCD backpack address");
constexpr int LCD_COLS = 16;
constexpr int LCD_ROWS = 2;

constexpr int LAMP_LED_COUNT = 4;


constexpr int DOOR_CLOSED_ANGLE = 0;
constexpr int DOOR_OPEN_ANGLE = 90;

// 6. AUTOMATION THRESHOLDS


constexpr float TEMP_WARNING = 35.0f;
constexpr float TEMP_DANGER = 40.0f;

constexpr float HUMIDITY_WARNING = 60.0f;
constexpr float HUMIDITY_DANGER = 70.0f;

#ifndef SMART_CLASSROOM_LIGHT_DARK_THRESHOLD
#define SMART_CLASSROOM_LIGHT_DARK_THRESHOLD 1000
#endif
constexpr int LIGHT_DARK_THRESHOLD = SMART_CLASSROOM_LIGHT_DARK_THRESHOLD;
#ifndef SMART_CLASSROOM_LIGHT_BRIGHT_THRESHOLD
#define SMART_CLASSROOM_LIGHT_BRIGHT_THRESHOLD 1200
#endif
constexpr int LIGHT_BRIGHT_THRESHOLD = SMART_CLASSROOM_LIGHT_BRIGHT_THRESHOLD;

constexpr int LIGHT_ADC_MAX = 4095;
static_assert(LIGHT_DARK_THRESHOLD >= 0 && LIGHT_DARK_THRESHOLD < LIGHT_BRIGHT_THRESHOLD &&
    LIGHT_BRIGHT_THRESHOLD <= LIGHT_ADC_MAX, "Check calibrated light thresholds");
constexpr bool LAMP_LOCAL_AVAILABLE = LIGHT_POLARITY != 0 && HAS_LIGHT_SENSOR && HAS_PIR &&
    (HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED);
#ifndef SMART_CLASSROOM_PIR_ACTIVE_HIGH
#define SMART_CLASSROOM_PIR_ACTIVE_HIGH 1
#endif
constexpr bool PIR_ACTIVE_HIGH = SMART_CLASSROOM_PIR_ACTIVE_HIGH;

#ifndef SMART_CLASSROOM_PIR_WARMUP_MS
#define SMART_CLASSROOM_PIR_WARMUP_MS 30000
#endif
constexpr unsigned long PIR_WARMUP_MS = SMART_CLASSROOM_PIR_WARMUP_MS;

#ifndef SMART_CLASSROOM_LED_ACTIVE_HIGH
#define SMART_CLASSROOM_LED_ACTIVE_HIGH 1
#endif
constexpr bool LED_ACTIVE_HIGH = SMART_CLASSROOM_LED_ACTIVE_HIGH;

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
    "classroom/" SMART_CLASSROOM_DEVICE_ID "/telemetry";

constexpr char MQTT_TOPIC_COMMAND[] =
    "classroom/" SMART_CLASSROOM_DEVICE_ID "/cmd";

constexpr char MQTT_TOPIC_ACK[] =
    "classroom/" SMART_CLASSROOM_DEVICE_ID "/ack";

// 10. OTA CONFIGURATION

constexpr int OTA_PORT = 3232;

// 11. IR REMOTE CODES

constexpr uint64_t IR_BTN_LAMP_ON = 0;
constexpr uint64_t IR_BTN_LAMP_OFF = 0;
constexpr uint64_t IR_BTN_LAMP_AUTO = 0;


constexpr uint64_t IR_BTN_DOOR_OPEN = 0;
constexpr uint64_t IR_BTN_DOOR_CLOSE = 0;
constexpr uint64_t IR_BTN_DOOR_AUTO = 0;

constexpr unsigned long IR_DEBOUNCE_MS = 300;
