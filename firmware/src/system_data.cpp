
#include "system_data.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

static ClassroomData classroomData;
static SemaphoreHandle_t dataMutex = nullptr;

bool SystemData::begin() {
    if (dataMutex != nullptr) {
        return true;
    }

    dataMutex = xSemaphoreCreateMutex();

    if (dataMutex != nullptr) {
        return true;
    }
    else {
        return false;
    }
}

ClassroomData SystemData::getSnapshot() {
    ClassroomData snapshot;

    if (dataMutex != nullptr) {
        if (xSemaphoreTake(dataMutex, portMAX_DELAY) == pdTRUE) {
            snapshot = classroomData;
            xSemaphoreGive(dataMutex);
        }
    }

    return snapshot;
}

void SystemData::updateSensors(const SensorData& data) {
    if (dataMutex != nullptr) {
        if (xSemaphoreTake(dataMutex, portMAX_DELAY) == pdTRUE) {
            classroomData.sensors = data;
            xSemaphoreGive(dataMutex);
        }
    }
}

void SystemData::updateActuators(const ActuatorData& data) {
    if (dataMutex != nullptr) {
        if (xSemaphoreTake(dataMutex, portMAX_DELAY) == pdTRUE) {
            classroomData.actuators = data;
            xSemaphoreGive(dataMutex);
        }
    }
}
