
#include "control_logic.h"
#include "config.h"
#include "system_data.h"

#include <cassert>
#include <iostream>

int main() {

    DoorCloseTracker door;

    auto decide = [&](
        bool current,
        bool valid,
        float cm,
        uint32_t t
    ) {
        return door.desired(
            current,
            valid,
            cm,
            t,
            DOOR_DISTANCE_CM,
            DOOR_CLOSE_DISTANCE_CM,
            DOOR_HOLD_MS
        );
    };

    assert(decide(false, true, 10, 100));

    assert(decide(true, true, 20, 1000));

    assert(decide(true, false, 0, 10000));

    assert(decide(true, true, 40, 12000));

    assert(decide(true, true, 40, 12000));

    assert(decide(true, true, 40, 16000));

    assert(!decide(true, true, 40, 17000));

    assert(decide(false, true, 10, 18000));

    assert(decide(true, true, 40, 20000));

    assert(decide(true, false, 0, 25000));

    assert(decide(true, true, 40, 26000));

    assert(!decide(true, true, 40, 31000));

    door.reset();

    assert(decide(true, true, 40, UINT32_MAX - 1000));

    assert(!decide(true, true, 40, 4000));

    NearDoorTracker events;

    assert(events.observe(true, 10, 100, 15, 25));

    assert(!events.observe(true, 10, 200, 15, 25));

    assert(!events.observe(false, 0, 300, 15, 25));

    assert(!events.observe(true, 10, 400, 15, 25));

    assert(!events.observe(true, 40, 500, 15, 25));

    assert(events.observe(true, 10, 600, 15, 25));

    assert(
        events.count == 2 &&
        events.lastAt == 600
    );

    ClassroomData data;

    assert(
        !data.sensors.distanceValid &&
        !data.actuators.doorAuto
    );

    assert(MOCK_MODE && !MQTT_EXTENDED_SCHEMA);

    std::cout
        << "PASS: door hysteresis/hold, invalid readings, "
        << "timestamp wrap, event counting, config defaults\n";
}
