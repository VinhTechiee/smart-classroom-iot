
#pragma once

#include <stdint.h>

struct SensorData {
    float temperature = 0.0f;
    float humidity = 0.0f;
    int light = 0;
    bool motion = false;
    float distance = 0.0f;

    bool dhtValid = false;
    bool lightValid = false;
    bool motionValid = false;
    bool distanceValid = false;

    uint32_t sampledAtMs = 0;

    // Su kien gan cua
    uint32_t nearDoorCount = 0;
    uint32_t lastNearDoorAtMs = 0;
};

struct ActuatorData {
    bool lamp = false;
    bool fan = false;
    bool door = false;

    bool lampKnown = false;
    bool fanKnown = false;
    bool doorKnown = false;

    bool lampAuto = true;
    bool fanAuto = true;
    bool doorAuto = false;
};

struct ClassroomData {
    SensorData sensors;
    ActuatorData actuators;
};

namespace SystemData {

    bool begin();

    ClassroomData getSnapshot();

    void updateSensors(const SensorData& data);

    void updateActuators(const ActuatorData& data);

}
