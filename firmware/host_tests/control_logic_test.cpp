
#include "control_logic.h"
#include "command_deadline.h"
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

    door.reset();
    assert(decide(false, true, 15, 100));
    assert(decide(true, true, 25, 200));
    assert(decide(true, true, 25, 5199));
    assert(!decide(true, true, 25, 5200));
    door.reset();
    assert(decide(true, true, 25, 6000));
    assert(decide(true, false, 0, 10000));
    assert(decide(true, true, 25, 11001));

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

    assert(!MOCK_MODE && !LAMP_LOCAL_AVAILABLE && DOOR_AUTO_AT_BOOT);
    assert(HAS_DHT20 && HAS_LIGHT_SENSOR && HAS_PIR && HAS_ULTRASONIC && HAS_SERVO && HAS_LCD);
    auto lighting = [](bool current, bool motion, bool valid, int raw, int polarity) {
        return desiredLampState(current, motion, valid, raw, polarity, LIGHT_ADC_MAX, 1000, 1200);
    };
    assert(!lighting(false, true, true, 850, 0));
    assert(lighting(false, true, true, 850, 1));
    assert(lighting(false, true, true, 3300, -1));
    assert(!lighting(false, true, true, 850, -1));
    assert(lighting(true, true, true, 1100, 1));
    assert(lighting(true, true, false, 4095, 1));
    assert(!lighting(true, false, true, 850, 1));
    constexpr uint64_t now = 1760000000000;
    assert(!validCommandDeadline(0, now));
    assert(!validCommandDeadline(now, 0));
    assert(!validCommandDeadline(now, now - 1));
    assert(!validCommandDeadline(now, now));
    assert(validCommandDeadline(now, now + 3500));
    assert(validCommandDeadline(now, now + 5000));
    assert(!validCommandDeadline(now, now + 5001));

    std::cout
        << "PASS: door hysteresis/hold, invalid readings, "
        << "timestamp wrap, light polarity/occupancy, command deadlines and config defaults\n";
}
