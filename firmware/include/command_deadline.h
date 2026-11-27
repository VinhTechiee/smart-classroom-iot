#pragma once

#include <stdint.h>
#include <sys/time.h>

inline uint64_t epochMillis() {
    timeval now{};
    if (gettimeofday(&now, nullptr) != 0 || now.tv_sec < 1704067200) {
        return 0;
    }
    return uint64_t(now.tv_sec) * 1000 + now.tv_usec / 1000;
}

inline bool validCommandDeadline(uint64_t now, uint64_t expiresAt) {
    return now != 0 && expiresAt > now && expiresAt - now <= 5000;
}
