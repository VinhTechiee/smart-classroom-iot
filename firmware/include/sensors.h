
#pragma once

#include <stdint.h>
#include "system_data.h"

namespace Sensors {

    bool begin();

    bool isI2CReady();

    SensorData read();

    bool readDHT20(float& temperature, float& humidity);

    bool readLight(int& light);

    bool readMotion(bool& motion);

    bool readDistance(float& distance);

    bool readIR(uint64_t& code);

}
