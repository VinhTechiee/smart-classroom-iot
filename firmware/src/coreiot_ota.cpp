#include "config.h"

#if defined(SMART_CLASSROOM_COREIOT_OTA)

#include "command_deadline.h"
#include "mqtt_client.h"
#include "ota.h"
#include "system_data.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_http_client.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

char WIFI_SSID[33]{};
char WIFI_PASSWORD[65]{};
char MQTT_HOST[128]{};
char MQTT_USERNAME[65]{};
char MQTT_PASSWORD[129]{};

namespace {

constexpr char SETTINGS[] = "classroom";
constexpr char TENANT[] = "https://app.coreiot.io/api/v1/";
constexpr char TITLE[] = "smart-classroom-yolouno";
constexpr char BASELINE[] = "1.0.0";
constexpr char TARGET[] = "1.1.0";
constexpr size_t MAX_METADATA = 4096;
constexpr unsigned long POLL_MS = 15000;
constexpr unsigned long DOWNLOAD_LIMIT_MS = 120000;

String certificate;
String deviceUrl;
String approvedSha;
uint32_t approvedSize = 0;
bool taskStarted = false;

bool safeToken(const String& token) {
    if (token.isEmpty() || token.length() > 128) {
        return false;
    }
    for (char c : token) {
        if (!(c >= 'A' && c <= 'Z') && !(c >= 'a' && c <= 'z') &&
            !(c >= '0' && c <= '9') && c != '-' && c != '_' && c != '.' && c != '~') {
            return false;
        }
    }
    return true;
}

bool validDigest(const String& digest) {
    if (digest.length() != 64) {
        return false;
    }
    for (char c : digest) {
        if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f')) {
            return false;
        }
    }
    return true;
}

class Request {
public:
    explicit Request(const String& url) {
        esp_http_client_config_t config{};
        config.url = url.c_str();
        config.cert_pem = certificate.c_str();
        config.timeout_ms = 5000;
        config.disable_auto_redirect = true;
        client = esp_http_client_init(&config);
    }

    ~Request() {
        if (client) {
            esp_http_client_cleanup(client);
        }
    }

    bool get() {
        return client && esp_http_client_open(client, 0) == ESP_OK &&
            esp_http_client_fetch_headers(client) >= 0 &&
            esp_http_client_get_status_code(client) == 200;
    }

    bool post(const JsonDocument& data) {
        if (!client) {
            return false;
        }
        String body;
        serializeJson(data, body);
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, body.c_str(), body.length());
        return esp_http_client_perform(client) == ESP_OK && esp_http_client_get_status_code(client) == 200;
    }

    int read(char* data, int size) {
        return esp_http_client_read(client, data, size);
    }

    int contentLength() const {
        return esp_http_client_get_content_length(client);
    }

    bool complete() const {
        return esp_http_client_is_complete_data_received(client);
    }

private:
    esp_http_client_handle_t client;
};

bool reportState(const char* state, const char* error = nullptr) {
    Serial.printf("[CoreIOT OTA] %s%s%s\n", state, error ? " " : "", error ? error : "");
    JsonDocument message;
    message["fw_state"] = state;
    if (error) {
        message["fw_error"] = error;
    }
    if (strcmp(state, "UPDATED") == 0) {
        message["current_fw_title"] = TITLE;
        message["current_fw_version"] = FW_VERSION;
        message["fw_error"] = "";
    }
    return Request(deviceUrl + "/telemetry").post(message);
}

bool reportRunningFirmware() {
    JsonDocument message;
    message["current_fw_title"] = TITLE;
    message["current_fw_version"] = FW_VERSION;
    // Client attributes establish the running release; telemetry records it for OTA history.
    return Request(deviceUrl + "/attributes").post(message) &&
        Request(deviceUrl + "/telemetry").post(message);
}

bool readAssignment(JsonDocument& result) {
    Request request(deviceUrl + "/attributes?sharedKeys=fw_title,fw_version,fw_checksum,fw_checksum_algorithm");
    if (!request.get() || request.contentLength() > MAX_METADATA) {
        return false;
    }
    String body;
    char block[384];
    const unsigned long started = millis();
    while (!request.complete() && millis() - started < 10000) {
        const int read = request.read(block, sizeof(block));
        if (read <= 0 || body.length() + read > MAX_METADATA || !body.concat(block, read)) {
            return false;
        }
    }
    return request.complete() && !deserializeJson(result, body) && result.is<JsonObject>();
}

const char* downloadImage(const esp_partition_t* partition) {
    Request request(deviceUrl + "/firmware?title=" + TITLE + "&version=" + TARGET);
    if (!request.get()) {
        return "download_http_failed";
    }
    if (request.contentLength() <= 0 || uint32_t(request.contentLength()) != approvedSize) {
        return "unexpected_content_length";
    }

    esp_ota_handle_t handle;
    if (esp_ota_begin(partition, approvedSize, &handle) != ESP_OK) {
        return "ota_begin_failed";
    }

    mbedtls_sha256_context digest;
    mbedtls_sha256_init(&digest);
    const char* error = nullptr;
    if (mbedtls_sha256_starts_ret(&digest, 0) != 0) {
        error = "sha256_init_failed";
    }
    char block[2048];
    uint32_t received = 0;
    const unsigned long started = millis();
    while (!error && received < approvedSize && millis() - started < DOWNLOAD_LIMIT_MS) {
        const int count = request.read(block, min(sizeof(block), size_t(approvedSize - received)));
        if (count <= 0) {
            break;
        }
        if (mbedtls_sha256_update_ret(&digest, reinterpret_cast<const uint8_t*>(block), count) != 0 ||
            esp_ota_write(handle, block, count) != ESP_OK) {
            error = "ota_write_failed";
            break;
        }
        received += count;
    }

    uint8_t hash[32]{};
    if (!error && (received != approvedSize || !request.complete())) {
        error = "download_incomplete";
    }
    if (!error && mbedtls_sha256_finish_ret(&digest, hash) != 0) {
        error = "sha256_failed";
    }
    mbedtls_sha256_free(&digest);

    if (!error && !reportState("DOWNLOADED")) {
        error = "state_delivery_failed";
    }
    if (!error) {
        char hex[65];
        for (size_t i = 0; i < sizeof(hash); ++i) {
            snprintf(hex + 2 * i, 3, "%02x", unsigned(hash[i]));
        }
        if (approvedSha != hex) {
            error = "sha256_mismatch";
        }
    }
    if (error) {
        esp_ota_abort(handle);
        return error;
    }
    // IDF validates the app image and its target chip before the boot slot can be selected.
    if (esp_ota_end(handle) != ESP_OK) {
        return "incompatible_app_image";
    }
    return nullptr;
}

const char* installAssignedImage(Preferences& settings) {
    const esp_partition_t* next = esp_ota_get_next_update_partition(nullptr);
    if (!next || !approvedSize || approvedSize > next->size) {
        return "image_exceeds_ota_slot";
    }
    if (!FirmwareOTA::startUpdate()) {
        return "actuator_safe_state_failed";
    }
    if (!reportState("DOWNLOADING")) {
        return "state_delivery_failed";
    }
    if (const char* error = downloadImage(next)) {
        return error;
    }
    if (!reportState("VERIFIED") || !reportState("UPDATING")) {
        return "state_delivery_failed";
    }
    if (settings.putString("boot_target", TARGET) != strlen(TARGET)) {
        return "boot_record_failed";
    }
    if (esp_ota_set_boot_partition(next) != ESP_OK) {
        return "boot_partition_failed";
    }
    ESP.restart();
    return "restart_failed";
}

void worker(void*) {
    Preferences settings;
    if (!settings.begin(SETTINGS)) {
        Serial.println("[CoreIOT OTA] NVS configuration unavailable");
        vTaskDelete(nullptr);
        return;
    }
    const String token = settings.getString("coreiot_token", "");
    certificate = settings.getString("coreiot_ca", "");
    approvedSha = settings.getString("fw_sha256", "");
    approvedSha.toLowerCase();
    approvedSize = settings.getUInt("fw_size", 0);
    if (!safeToken(token) || certificate.isEmpty() || !validDigest(approvedSha) || !approvedSize) {
        Serial.println("[CoreIOT OTA] lab credentials or reviewed release are missing");
        vTaskDelete(nullptr);
        return;
    }
    deviceUrl = TENANT + token;
    String bootTarget = settings.getString("boot_target", "");
    const char* failure = nullptr;
    bool runningReported = false;
    bool attempted = !bootTarget.isEmpty();

    for (;;) {
        if (WiFi.status() == WL_CONNECTED && epochMillis()) {
            if (!runningReported) {
                runningReported = reportRunningFirmware();
            } else if (!bootTarget.isEmpty()) {
                if (bootTarget != FW_VERSION) {
                    failure = "assigned_release_did_not_boot";
                    bootTarget.clear();
                } else {
                    const ClassroomData data = SystemData::getSnapshot();
                    if (ClassroomMQTT::isConnected() && data.sensors.dhtValid &&
                        millis() - data.sensors.sampledAtMs <= SENSOR_STALE_MS && data.actuators.lampKnown) {
                        if (reportState("UPDATED")) {
                            settings.remove("boot_target");
                            bootTarget.clear();
                        }
                    } else if (millis() > DOWNLOAD_LIMIT_MS) {
                        failure = "post_boot_self_test_failed";
                        bootTarget.clear();
                    }
                }
            } else if (failure) {
                if (reportState("FAILED", failure)) {
                    failure = nullptr;
                }
            } else if (!attempted && strcmp(FW_VERSION, BASELINE) == 0) {
                JsonDocument assignment;
                if (readAssignment(assignment)) {
                    const JsonVariantConst shared = assignment["shared"];
                    const String title = shared["fw_title"] | "";
                    const String version = shared["fw_version"] | "";
                    if (title == TITLE && version == TARGET) {
                        String algorithm = shared["fw_checksum_algorithm"] | "";
                        String digest = shared["fw_checksum"] | "";
                        algorithm.toLowerCase();
                        digest.toLowerCase();
                        attempted = true;
                        if ((algorithm == "sha256" || algorithm == "sha-256") && digest == approvedSha) {
                            failure = installAssignedImage(settings);
                            FirmwareOTA::finishUpdate();
                        } else {
                            failure = "assignment_checksum_not_approved";
                        }
                    }
                } else {
                    Serial.println("[CoreIOT OTA] could not read shared attributes");
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}

}  // namespace

void loadLabNetworkSettings() {
    Preferences settings;
    if (settings.begin(SETTINGS, true)) {
        settings.getString("wifi_ssid", WIFI_SSID, sizeof(WIFI_SSID));
        settings.getString("wifi_password", WIFI_PASSWORD, sizeof(WIFI_PASSWORD));
        settings.getString("mqtt_host", MQTT_HOST, sizeof(MQTT_HOST));
        settings.getString("mqtt_username", MQTT_USERNAME, sizeof(MQTT_USERNAME));
        settings.getString("mqtt_password", MQTT_PASSWORD, sizeof(MQTT_PASSWORD));
    }
}

void CoreIotOTA::begin() {
    if (!taskStarted) {
        taskStarted = xTaskCreate(worker, "CoreIotOTA", 12288, nullptr, 1, nullptr) == pdPASS;
    }
}

#endif
