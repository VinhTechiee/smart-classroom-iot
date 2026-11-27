
#include "web_server.h"
#include "config.h"
#include "system_data.h"
#include "automation.h"

#include <Arduino.h>
#include <cstring>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>

static WebServer server(WEB_SERVER_PORT);

// ==================================================
// HTML, CSS, JAVASCRIPT
// ==================================================

static const char WEB_PAGE[] PROGMEM = R"HTML(

<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">

    <title>Smart Classroom</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f1f5f9;
            color: #1e293b;
        }

        header {
            background: #1e40af;
            color: white;
            padding: 24px;
            text-align: center;
        }

        main {
            max-width: 900px;
            margin: auto;
            padding: 20px;
        }

        .grid {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
        }

        .card {
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 12px;
            box-shadow: 0 3px 10px #00000010;
        }

        .value {
            font-size: 28px;
            font-weight: bold;
            color: #2563eb;
        }

        button {
            border: none;
            border-radius: 7px;
            padding: 12px 16px;
            margin: 4px;
            cursor: pointer;
            color: white;
            font-size: 14px;
        }

        button:disabled {
            opacity: 0.5;
            cursor: wait;
        }

        .on {
            background: #16a34a;
        }

        .off {
            background: #dc2626;
        }

        .auto {
            background: #2563eb;
        }

        .manual {
            background: #64748b;
        }

        #message {
            padding: 12px;
            color: #475569;
        }

        footer {
            text-align: center;
            padding: 20px;
            color: #64748b;
        }
    </style>
</head>

<body>

<header>
    <h1>Smart Classroom</h1>
    <p>ESP32 Smart Classroom Dashboard</p>
</header>

<main>

    <div class="card">
        <p id="connection">Đang kết nối...</p>
        <p id="systemInfo"></p>
    </div>

    <h2>Dữ liệu cảm biến</h2>

    <div class="grid">

        <div class="card">
            <p>Nhiệt độ</p>
            <div class="value" id="temperature">--</div>
        </div>

        <div class="card">
            <p>Độ ẩm</p>
            <div class="value" id="humidity">--</div>
        </div>

        <div class="card">
            <p>Ánh sáng</p>
            <div class="value" id="light">--</div>
        </div>

        <div class="card">
            <p>Khoảng cách</p>
            <div class="value" id="distance">--</div>
        </div>

        <div class="card">
            <p>Chuyển động</p>
            <div id="motion">--</div>
        </div>

    </div>

    <h2>Điều khiển thiết bị</h2>

    <!-- DEN -->

    <div class="card">
        <h3>Đèn</h3>

        <p>Trạng thái: <b id="lamp">--</b></p>
        <p>Chế độ: <b id="lampMode">--</b></p>

        <button class="on"
            onclick="control('lamp', true)">Bật</button>

        <button class="off"
            onclick="control('lamp', false)">Tắt</button>

        <button class="auto"
            onclick="setMode('lamp', true)">Auto</button>

        <button class="manual"
            onclick="setMode('lamp', false)">Manual</button>
    </div>

    <!-- QUAT -->

    <div class="card">
        <h3>Quạt</h3>

        <p>Trạng thái: <b id="fan">--</b></p>
        <p>Chế độ: <b id="fanMode">--</b></p>

        <button class="on"
            onclick="control('fan', true)">Bật</button>

        <button class="off"
            onclick="control('fan', false)">Tắt</button>

        <button class="auto"
            onclick="setMode('fan', true)">Auto</button>

        <button class="manual"
            onclick="setMode('fan', false)">Manual</button>
    </div>

    <!-- CUA -->

    <div class="card">
        <h3>Cửa</h3>

        <p>Trạng thái: <b id="door">--</b></p>
        <p>Chế độ: <b id="doorMode">--</b></p>

        <button class="on"
            onclick="control('door', true)">Mở</button>

        <button class="off"
            onclick="control('door', false)">Đóng</button>

        <button class="auto"
            onclick="setMode('door', true)">Auto</button>

        <button class="manual"
            onclick="setMode('door', false)">Manual</button>
    </div>

    <div id="message"></div>

</main>

<footer>
    Smart Classroom - IoT Project
</footer>

<script>

    let busy = false;
    let latestStatus = null;

    function setText(id, value) {
        document.getElementById(id).textContent = value;
    }

    function showValue(value, unit) {
        return value == null
            ? "--"
            : (typeof value === "number" &&
               !Number.isInteger(value)
                ? value.toFixed(1)
                : value) + unit;
    }

    function showState(state, known, onText, offText) {
        if (!known) {
            return "Chưa xác định";
        }

        return state ? onText : offText;
    }

    // Load sensor and actuator data

function updateButtons() {

    const devices = [
        ["lamp", "hasLamp", "lampAutoAvailable"],
        ["fan", "hasFan", "fanAutoAvailable"],
        ["door", "hasDoor", "doorAutoAvailable"]
    ];

    devices.forEach(([id, available, autoAvailable]) => {

        const card = document
            .getElementById(id)
            .closest(".card");

        card.querySelectorAll("button").forEach(button => {

            button.disabled =
                busy ||
                !latestStatus ||
                !latestStatus[available] ||
                (
                    button.classList.contains("auto") &&
                    !latestStatus[autoAvailable]
                );
        });
    });
}

    async function loadStatus() {

        try {
            const response = await fetch("/api/status", {
                cache: "no-store"
            });

            if (!response.ok) {
                throw new Error("Status request failed");
            }

            const data = await response.json();
            latestStatus = data;

            setText("connection", "Đã kết nối ESP32");

            setText(
                "systemInfo",
                data.deviceId +
                " | Firmware " + data.fwVersion +
                (data.mockMode ? " | MOCK MODE" : "")
            );

            setText(
                "temperature",
                showValue(data.temperature, " °C")
            );

            setText(
                "humidity",
                showValue(data.humidity, " %")
            );

            setText(
                "light",
                showValue(data.light, " ADC")
            );

            setText(
                "distance",
                showValue(data.distance, " cm")
            );

            setText(
                "motion",
                data.motion == null
                    ? "--"
                    : data.motion
                        ? "Có chuyển động"
                        : "Không chuyển động"
            );

            setText(
                "lamp",
                showState(
                    data.lamp,
                    data.lampKnown,
                    "BẬT",
                    "TẮT"
                )
            );

            setText(
                "fan",
                showState(
                    data.fan,
                    data.fanKnown,
                    "BẬT",
                    "TẮT"
                )
            );

            setText(
                "door",
                showState(
                    data.door,
                    data.doorKnown,
                    "MỞ",
                    "ĐÓNG"
                )
            );

            setText(
                "lampMode",
                data.lampAuto ? "AUTO" : "MANUAL"
            );

            setText(
                "fanMode",
                data.fanAuto ? "AUTO" : "MANUAL"
            );

            setText(
                "doorMode",
                data.doorAuto ? "AUTO" : "MANUAL"
            );

if (!data.hasDHT20) {
    setText("temperature", "Không lắp");
    setText("humidity", "Không lắp");
}

if (!data.hasLight) {
    setText("light", "Không lắp");
}

if (!data.hasPIR) {
    setText("motion", "Không lắp");
}

if (!data.hasUltrasonic) {
    setText("distance", "Không lắp");
}

if (!data.hasLamp) {
    setText("lamp", "Không lắp");
    setText("lampMode", "--");
}

if (!data.hasFan) {
    setText("fan", "Không lắp");
    setText("fanMode", "--");
}

if (!data.hasDoor) {
    setText("door", "Không lắp");
    setText("doorMode", "--");
}

updateButtons();


        } catch (error) {

            setText("connection", "Mất kết nối ESP32");

            const ids = [
                "temperature", "humidity", "light",
                "distance", "motion", "lamp", "fan",
                "door", "lampMode", "fanMode", "doorMode"
            ];

            ids.forEach(id => setText(id, "--"));
            latestStatus = null;
updateButtons();
        }
    }

    // Send HTTP POST command

    async function sendCommand(url, body) {

        if (busy) {
            return;
        }

        busy = true;

        document.querySelectorAll("button")
            .forEach(b => b.disabled = true);

        try {

            const response = await fetch(url, {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify(body)
            });

            const result = await response.json();

            if (response.ok && result.ok) {

                setText(
                    "message",
                    "Điều khiển thành công"
                );
            }
            else {

                setText(
                    "message",
                    "Điều khiển thất bại"
                );
            }

        } catch (error) {

            setText("message", "Lỗi kết nối");
        }
        finally {

    await loadStatus();

    busy = false;

    updateButtons();
}
    }

    // Manual control

    function control(target, state) {

        return sendCommand("/api/control", {
            target: target,
            state: state
        });
    }

    // Auto / Manual

    function setMode(target, enabled) {

        return sendCommand("/api/mode", {
            target: target,
            enabled: enabled
        });
    }

    // Poll every 2 seconds

    async function pollStatus() {

        if (!busy) {
            await loadStatus();
        }

        setTimeout(pollStatus, 2000);
    }
    updateButtons();

    pollStatus();

</script>

</body>
</html>

)HTML";

// ==================================================
// 1. SEND JSON RESPONSE
// ==================================================

static void sendJson(
    int statusCode,
    const JsonDocument& doc
) {
    if (doc.overflowed()) {

        server.send(
            500,
            "application/json",
            "{\"error\":\"JSON overflow\"}"
        );

        return;
    }

    String response;

    if (serializeJson(doc, response) != measureJson(doc)) {

        server.send(
            500,
            "application/json",
            "{\"error\":\"Serialization failed\"}"
        );

        return;
    }

    server.sendHeader("Cache-Control", "no-store");

    server.send(
        statusCode,
        "application/json",
        response
    );
}

// ==================================================
// 2. SEND ERROR
// ==================================================

static void sendError(
    int statusCode,
    const char* message
) {
    JsonDocument reply;

    reply["ok"] = false;
    reply["error"] = message;

    sendJson(statusCode, reply);
}

// ==================================================
// 3. HANDLE ROOT
// ==================================================

static void handleRoot() {

    server.send_P(
        200,
        "text/html; charset=utf-8",
        WEB_PAGE
    );
}

// ==================================================
// 4. HANDLE NOT FOUND
// ==================================================

static void handleNotFound() {

    sendError(404, "Not Found");
}

// ==================================================
// 5. GET SYSTEM STATUS
// ==================================================

static void handleStatus() {

    ClassroomData data =
        SystemData::getSnapshot();

    bool fresh =
        millis() - data.sensors.sampledAtMs
        <= SENSOR_STALE_MS;

    if (!fresh) {
        data.sensors.dhtValid = false;
        data.sensors.lightValid = false;
        data.sensors.motionValid = false;
        data.sensors.distanceValid = false;
    }

    JsonDocument doc;

    if (data.sensors.dhtValid == true) {

        doc["temperature"] =
            data.sensors.temperature;

        doc["humidity"] =
            data.sensors.humidity;
    }
    else {
        doc["temperature"] = nullptr;
        doc["humidity"] = nullptr;
    }

    if (data.sensors.lightValid == true) {

        doc["light"] = data.sensors.light;
    }
    else {

        doc["light"] = nullptr;
    }

    if (data.sensors.motionValid == true) {

        doc["motion"] = data.sensors.motion;
    }
    else {

        doc["motion"] = nullptr;
    }

    if (data.sensors.distanceValid == true) {

        doc["distance"] = data.sensors.distance;
    }
    else {

        doc["distance"] = nullptr;
    }

    // Sensor timestamps and events

    doc["sampledAtMs"] =
        data.sensors.sampledAtMs;

    doc["nearDoorCount"] =
        data.sensors.nearDoorCount;

    doc["lastNearDoorAtMs"] =
        data.sensors.lastNearDoorAtMs;

    // Actuator states

    doc["lamp"] = data.actuators.lamp;
    doc["fan"] = data.actuators.fan;
    doc["door"] = data.actuators.door;

    // Known states

    doc["lampKnown"] = data.actuators.lampKnown;
    doc["fanKnown"] = data.actuators.fanKnown;
    doc["doorKnown"] = data.actuators.doorKnown;

    // Auto / Manual

    doc["lampAuto"] = data.actuators.lampAuto;
    doc["fanAuto"] = data.actuators.fanAuto;
    doc["doorAuto"] = data.actuators.doorAuto;
    // Hardware availability

doc["hasDHT20"] = HAS_DHT20;
doc["hasLight"] = HAS_LIGHT_SENSOR;
doc["hasPIR"] = HAS_PIR;
doc["hasUltrasonic"] = HAS_ULTRASONIC;

doc["hasLamp"] = HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED;
doc["hasFan"] = HAS_FAN;
doc["hasDoor"] = HAS_SERVO;

doc["lampAutoAvailable"] =
    (HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED) &&
    HAS_PIR && HAS_LIGHT_SENSOR;

doc["fanAutoAvailable"] = HAS_FAN && HAS_DHT20;

doc["doorAutoAvailable"] = HAS_SERVO && HAS_ULTRASONIC;
    // System information

    doc["deviceId"] = DEVICE_ID;
    doc["fwVersion"] = FW_VERSION;
    doc["mockMode"] = MOCK_MODE;

    sendJson(200, doc);
}

// ==================================================
// 6. PARSE TARGET
// ==================================================

static bool parseTarget(
    const String& name,
    ControlTarget& target
) {
    if (name == "lamp") {

        target = ControlTarget::Lamp;

        return true;
    }
    else if (name == "fan") {

        target = ControlTarget::Fan;

        return true;
    }
    else if (name == "door") {

        target = ControlTarget::Door;

        return true;
    }

    return false;
}

// ==================================================
// 7. READ JSON COMMAND
// ==================================================

static bool readCommand(
    const char* valueKey,
    ControlTarget& target,
    bool& value
) {
    // Require application/json content type

    String contentType =
        server.header("Content-Type");

    int separator = contentType.indexOf(';');

    if (separator >= 0) {
        contentType =
            contentType.substring(0, separator);
    }

    contentType.trim();

    if (!contentType.equalsIgnoreCase("application/json")) {

        sendError(
            415,
            "Content-Type must be application/json"
        );

        return false;
    }

    if (!server.hasArg("plain")) {

        sendError(400, "Missing body");

        return false;
    }

    String body = server.arg("plain");

    if (body.length() > 512) {

        sendError(413, "Body too large");

        return false;
    }

    JsonDocument doc;

    DeserializationError error =
        deserializeJson(doc, body);

    if (
        error ||
        !doc.is<JsonObject>() ||
        doc.overflowed()
    ) {

        sendError(400, "Invalid JSON");

        return false;
    }

    if (
        !doc["target"].is<const char*>() ||
        !doc[valueKey].is<bool>()
    ) {

        sendError(400, "Invalid target or value");

        return false;
    }

    JsonString targetName =
        doc["target"].as<JsonString>();

    if (
        memchr(
            targetName.c_str(),
            '\0',
            targetName.size()
        ) != nullptr
    ) {

        sendError(400, "Invalid target");

        return false;
    }

    String name = targetName.c_str();

    if (!parseTarget(name, target)) {

        sendError(400, "Unknown target");

        return false;
    }

    value = doc[valueKey].as<bool>();

    return true;
}

// ==================================================
// 8. CONTROL ACTUATOR
// ==================================================

static void handleControl() {

    ControlTarget target =
        ControlTarget::Lamp;

    bool state = false;

    if (!readCommand("state", target, state)) {
        return;
    }

    ControlResult result =
        Automation::applyManualCommand(
            target,
            state,
            ControlSource::Web
        );

    JsonDocument reply;

    reply["ok"] = result.ok;
    reply["actualState"] = result.actualState;
    reply["stateKnown"] = result.stateKnown;

    if (result.ok == true) {

        sendJson(200, reply);
    }
    else {

        sendJson(500, reply);
    }
}

// ==================================================
// 9. SET AUTO / MANUAL MODE
// ==================================================

static void handleMode() {

    ControlTarget target =
        ControlTarget::Lamp;

    bool enabled = false;

    if (!readCommand("enabled", target, enabled)) {
        return;
    }

    bool ok = Automation::setAutomatic(
        target,
        enabled
    );

    JsonDocument reply;

    reply["ok"] = ok;

    if (ok == true) {

        sendJson(200, reply);
    }
    else {

        sendJson(500, reply);
    }
}

// ==================================================
// 10. INITIALIZE WEB SERVER
// ==================================================

void LocalWeb::begin() {

    server.on(
        "/",
        HTTP_GET,
        handleRoot
    );

    server.on(
        "/api/status",
        HTTP_GET,
        handleStatus
    );

    server.on(
        "/api/control",
        HTTP_POST,
        handleControl
    );

    server.on(
        "/api/mode",
        HTTP_POST,
        handleMode
    );

    const char* headers[] = {
        "Content-Type"
    };

    server.collectHeaders(headers, 1);

    server.onNotFound(handleNotFound);

    server.begin();

    Serial.println("Web Server started");

    Serial.print("Web Server IP: ");

    Serial.println(WiFi.localIP());
}

// ==================================================
// 11. HANDLE HTTP REQUESTS
// ==================================================

void LocalWeb::update() {

    server.handleClient();
}
