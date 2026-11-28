
#pragma once

#include "system_data.h"

namespace Actuators {

    bool begin();

    bool setLamp(bool state);

    bool setFan(bool state);

    bool setDoor(bool state);

    void updateLCD(const ClassroomData& data);
    void updateWarningLED(const ClassroomData& data);

}
