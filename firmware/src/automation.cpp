
#include "automation.h"
#include "config.h"
#include "system_data.h"
#include "actuators.h"
#include "ota.h"
#include "control_logic.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

static SemaphoreHandle_t automationMutex = nullptr;

static unsigned long lastMotionMs = 0;
static bool hasMotion = false;

static DoorCloseTracker doorTracker;

static unsigned long lastIRMs = 0;
static uint64_t lastIRCode = 0;

// 1. Apply output

static ControlResult applyOutput(
    ActuatorData& actuators,
    ControlTarget target,
    bool state
) {
    ControlResult result;

    switch (target) {

        case ControlTarget::Lamp:

            result.ok = Actuators::setLamp(state);

            if (result.ok == true) {
                actuators.lamp = state;
            }

            actuators.lampKnown = result.ok;

            result.actualState = actuators.lamp;
            result.stateKnown = actuators.lampKnown;

            break;

        case ControlTarget::Fan:

            result.ok = Actuators::setFan(state);

            if (result.ok == true) {
                actuators.fan = state;
            }

            actuators.fanKnown = result.ok;

            result.actualState = actuators.fan;
            result.stateKnown = actuators.fanKnown;

            break;

        case ControlTarget::Door:

            result.ok = Actuators::setDoor(state);

            if (result.ok == true) {
                actuators.door = state;
            }

            actuators.doorKnown = result.ok;

            result.actualState = actuators.door;
            result.stateKnown = actuators.doorKnown;

            break;

        default:
            break;
    }

    return result;
}

// 2. Initialize automation


bool Automation::begin() {

    if (automationMutex == nullptr) {
        automationMutex = xSemaphoreCreateMutex();
    }

    if (automationMutex == nullptr) {
        return false;
    }

    lastMotionMs = 0;
    hasMotion = false;

    doorTracker.reset();

    ActuatorData actuators;

    bool lampOK = true;
    bool fanOK = true;
    bool doorOK = true;

    if (HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED) {

        lampOK = applyOutput(
            actuators,
            ControlTarget::Lamp,
            false
        ).ok;
    }

    if (HAS_FAN) {

        fanOK = applyOutput(
            actuators,
            ControlTarget::Fan,
            false
        ).ok;
    }

    if (HAS_SERVO) {

        doorOK = applyOutput(
            actuators,
            ControlTarget::Door,
            false
        ).ok;
    }

    actuators.lampAuto =
        (HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED) &&
        HAS_PIR &&
        HAS_LIGHT_SENSOR;

    actuators.fanAuto = HAS_FAN && HAS_DHT20;

    SystemData::updateActuators(actuators);

    return lampOK && fanOK && doorOK;
}

// 3. Automatic control

void Automation::update() {

    if (automationMutex == nullptr) {
        return;
    }

    if (FirmwareOTA::isUpdating()) {
        return;
    }

    if (xSemaphoreTake(
            automationMutex,
            portMAX_DELAY
        ) != pdTRUE) {
        return;
    }

    if (FirmwareOTA::isUpdating()) {
        xSemaphoreGive(automationMutex);
        return;
    }

    ClassroomData data = SystemData::getSnapshot();

    ActuatorData& actuators = data.actuators;

    unsigned long now = millis();

    // 3.1. Check stale sensor data

    bool sensorFresh =
        (now - data.sensors.sampledAtMs) <= SENSOR_STALE_MS;

    if (sensorFresh == false) {
        data.sensors.dhtValid = false;
        data.sensors.lightValid = false;
        data.sensors.motionValid = false;
        data.sensors.distanceValid = false;
    }

    // 3.2. Motion detection

    if (data.sensors.motionValid == true &&
        data.sensors.motion == true) {

        lastMotionMs = data.sensors.sampledAtMs;

        hasMotion = true;
    }

    bool recentMotion =
        hasMotion == true &&
        (now - lastMotionMs < MOTION_TIMEOUT_MS);

    // 3.3. Automatic lamp

    if (
    (HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED) &&
    HAS_PIR &&
    HAS_LIGHT_SENSOR &&
    actuators.lampAuto == true
) {

        bool desiredLamp = actuators.lamp;

        if (recentMotion == false) {

            desiredLamp = false;
        }
        else if (
            data.sensors.lightValid == true &&
            data.sensors.light <= LIGHT_DARK_THRESHOLD
        ) {

            desiredLamp = true;
        }
        else if (
            data.sensors.lightValid == true &&
            data.sensors.light >= LIGHT_BRIGHT_THRESHOLD
        ) {

            desiredLamp = false;
        }

        if (
            desiredLamp != actuators.lamp ||
            actuators.lampKnown == false
        ) {

            applyOutput(
                actuators,
                ControlTarget::Lamp,
                desiredLamp
            );
        }
    }

    // 3.4. Automatic fan

    if (
    HAS_FAN &&
    actuators.fanAuto == true &&
    data.sensors.dhtValid == true
) {

        bool desiredFan = actuators.fan;

        if (data.sensors.temperature >= TEMP_FAN_ON) {

            desiredFan = true;
        }
        else if (
            data.sensors.temperature <= TEMP_FAN_OFF
        ) {

            desiredFan = false;
        }

        if (
            desiredFan != actuators.fan ||
            actuators.fanKnown == false
        ) {

            applyOutput(
                actuators,
                ControlTarget::Fan,
                desiredFan
            );
        }
    }

    // 3.5. Automatic door

    if (
    HAS_SERVO &&
    HAS_ULTRASONIC &&
    actuators.doorAuto == true
) {

        bool desiredDoor = doorTracker.desired(
            actuators.door,
            data.sensors.distanceValid,
            data.sensors.distance,
            data.sensors.sampledAtMs,
            DOOR_DISTANCE_CM,
            DOOR_CLOSE_DISTANCE_CM,
            DOOR_HOLD_MS
        );

        if (
            data.sensors.distanceValid &&
            (
                desiredDoor != actuators.door ||
                (!actuators.doorKnown && desiredDoor)
            )
        ) {

            applyOutput(
                actuators,
                ControlTarget::Door,
                desiredDoor
            );
        }
    }
    // Update onboard warning LED
Actuators::updateWarningLED(data);
    // 3.6. Save actuator states

    if (!actuators.doorAuto) {
        doorTracker.reset();
    }

    SystemData::updateActuators(actuators);

    xSemaphoreGive(automationMutex);
}

// 4. Manual control

ControlResult Automation::applyManualCommand(
    ControlTarget target,
    bool state,
    ControlSource source
) {
    (void)source;

    ControlResult result;

    if (automationMutex == nullptr) {
        return result;
    }

    if (FirmwareOTA::isUpdating()) {
        return result;
    }

    if (xSemaphoreTake(
            automationMutex,
            portMAX_DELAY
        ) != pdTRUE) {

        return result;
    }

    if (FirmwareOTA::isUpdating()) {
        xSemaphoreGive(automationMutex);
        return result;
    }

    ClassroomData data = SystemData::getSnapshot();

    ActuatorData& actuators = data.actuators;

    result = applyOutput(
        actuators,
        target,
        state
    );

    if (result.ok == true) {

        switch (target) {

            case ControlTarget::Lamp:

                actuators.lampAuto = false;

                break;

            case ControlTarget::Fan:

                actuators.fanAuto = false;

                break;

            case ControlTarget::Door:

                actuators.doorAuto = false;

                doorTracker.reset();

                break;

            default:
                break;
        }
    }

    SystemData::updateActuators(actuators);

    xSemaphoreGive(automationMutex);

    return result;
}

// 5. Set Auto / Manual mode

bool Automation::setAutomatic(
    ControlTarget target,
    bool enabled
) {
    if (automationMutex == nullptr) {
        return false;
    }

    if (xSemaphoreTake(
            automationMutex,
            portMAX_DELAY
        ) != pdTRUE) {

        return false;
    }

    if (FirmwareOTA::isUpdating()) {
        xSemaphoreGive(automationMutex);
        return false;
    }

    ClassroomData data = SystemData::getSnapshot();

    ActuatorData& actuators = data.actuators;

    
bool ok = true;

switch (target) {

    case ControlTarget::Lamp:

        if (!(HAS_EXTERNAL_LAMP || HAS_ONBOARD_LED) ||
            (enabled && (!HAS_PIR || !HAS_LIGHT_SENSOR))) {

            ok = false;
            break;
        }

        actuators.lampAuto = enabled;

        break;

    case ControlTarget::Fan:

        if (!HAS_FAN ||
            (enabled && !HAS_DHT20)) {

            ok = false;
            break;
        }

        actuators.fanAuto = enabled;

        break;

    case ControlTarget::Door:

        if (!HAS_SERVO ||
            (enabled && !HAS_ULTRASONIC)) {

            ok = false;
            break;
        }

        actuators.doorAuto = enabled;

        doorTracker.reset();

        break;

    default:

        ok = false;

        break;
}


    if (ok == true) {

        SystemData::updateActuators(actuators);
    }

    xSemaphoreGive(automationMutex);

    return ok;
}

// 6. IR remote control

void Automation::handleIR(uint64_t code) {

    Serial.printf(
        "IR code: 0x%016llX\n",
        static_cast<unsigned long long>(code)
    );

    if (code == 0) {
        return;
    }

    unsigned long now = millis();

    if (code == lastIRCode &&
        (now - lastIRMs) < IR_DEBOUNCE_MS) {

        return;
    }

    lastIRCode = code;
    lastIRMs = now;

    if (code == IR_BTN_LAMP_ON) {

        applyManualCommand(
            ControlTarget::Lamp,
            true,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_LAMP_OFF) {

        applyManualCommand(
            ControlTarget::Lamp,
            false,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_LAMP_AUTO) {

        setAutomatic(ControlTarget::Lamp, true);
    }
    else if (code == IR_BTN_FAN_ON) {

        applyManualCommand(
            ControlTarget::Fan,
            true,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_FAN_OFF) {

        applyManualCommand(
            ControlTarget::Fan,
            false,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_FAN_AUTO) {

        setAutomatic(ControlTarget::Fan, true);
    }
    else if (code == IR_BTN_DOOR_OPEN) {

        applyManualCommand(
            ControlTarget::Door,
            true,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_DOOR_CLOSE) {

        applyManualCommand(
            ControlTarget::Door,
            false,
            ControlSource::IR
        );
    }
    else if (code == IR_BTN_DOOR_AUTO) {

        setAutomatic(ControlTarget::Door, true);
    }
    else {
        Serial.println("IR code not mapped");
    }
}

// 7. Wait for actuator commands before OTA

void Automation::waitForIdle() {
    if (
        automationMutex &&
        xSemaphoreTake(
            automationMutex,
            portMAX_DELAY
        ) == pdTRUE
    ) {
        xSemaphoreGive(automationMutex);
    }
}
