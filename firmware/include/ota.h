
#pragma once

namespace FirmwareOTA {

    void begin();

    void update();

    bool isUpdating();
    bool startUpdate();
    void finishUpdate();

}

#if defined(SMART_CLASSROOM_COREIOT_OTA)
namespace CoreIotOTA {
    void begin();
}
#endif
