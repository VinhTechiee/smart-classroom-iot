
#pragma once

#include <stdint.h>
#include "system_data.h"

enum class ControlTarget {
    Lamp,
    Fan,
    Door
};

enum class ControlSource {
    Web,
    MQTT,
    IR
};

struct ControlResult {
    bool ok = false;
    bool actualState = false;
    bool stateKnown = false;
};

namespace Automation {

    bool begin();

    void update();

    ControlResult applyManualCommand(
        ControlTarget target,
        bool state,
        ControlSource source
    );

    bool setAutomatic(
        ControlTarget target,
        bool enabled
    );

    void handleIR(uint64_t code);

    void waitForIdle();
}
