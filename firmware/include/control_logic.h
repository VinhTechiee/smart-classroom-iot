
#pragma once

#include <stdint.h>

struct DoorCloseTracker {
    bool farTracking = false;
    uint32_t farSince = 0;

    bool desired(
        bool current,
        bool valid,
        float cm,
        uint32_t now,
        float openCm,
        float closeCm,
        uint32_t holdMs
    ) {
        if (!valid || cm < closeCm) {
            farTracking = false;
        }

        if (!valid) return current;

        if (cm <= openCm) return true;

        if (cm < closeCm) return current;

        if (!farTracking) {
            farTracking = true;
            farSince = now;
        }

        return (uint32_t)(now - farSince) >= holdMs
            ? false : current;
    }

    void reset() {
        farTracking = false;
    }
};

struct NearDoorTracker {
    bool near = false;
    uint32_t count = 0;
    uint32_t lastAt = 0;

    bool observe(
        bool valid,
        float cm,
        uint32_t now,
        float openCm,
        float closeCm
    ) {
        if (!valid) return false;

        if (cm >= closeCm) {
            near = false;
        }

        if (cm <= openCm && !near) {
            near = true;
            ++count;
            lastAt = now;

            return true;
        }

        return false;
    }
};
