
#pragma once

constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";

constexpr char MQTT_HOST[] = "";
// Set if the local Mosquitto listener requires authentication.
#define SMART_CLASSROOM_MQTT_USERNAME ""
#define SMART_CLASSROOM_MQTT_PASSWORD ""

// Override only for a separate classroom or isolated mock test.
// #define SMART_CLASSROOM_DEVICE_ID "classroom-01-sim"
// #define SMART_CLASSROOM_MOCK_MODE 1
// #define SMART_CLASSROOM_NTP_HOST "pool.ntp.org"

constexpr char OTA_PASSWORD[] = "";
