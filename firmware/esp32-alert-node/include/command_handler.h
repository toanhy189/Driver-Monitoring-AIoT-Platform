#pragma once
#include <ArduinoJson.h>
#include <cstdint>
#include "device_config.h"

struct DeviceState
{
    bool active;
    int pin;
    
    char requestId[64];
    char intensity[32];
    // [TV1-13 - thêm] Hash payload đi cùng request_id để ghi đúng kết quả vào NVS.
    uint32_t reqHash;

    unsigned long startTime, duration;

    unsigned long phaseStart;
    bool outputHigh;

    int startMs, endMs;

    bool compareIntensity(const char* intensity);
};

// quyết định xem ghi đè lệnh k
// !!! đang có khai báo khác trong hàm thật ở .cpp
static void switchDevice(
 /*DeviceState& device, const DeviceConfig& config,
    unsigned long duration, const char* intensity*/   
);

// update state của 1 device
static void updateDevice(
    DeviceState& device, const DeviceConfig& config
);

// update state của các device, dùng trong loop() của main.cpp
void deviceLoop();

// bật tắt device
static void handleDeviceOn(
    DeviceState& device,
    const DeviceConfig& config,
    JsonDocument& doc
);
static void handleDeviceOff(
    DeviceState& device,
    const DeviceConfig& config,
    JsonDocument& doc
);

// onMessage() gọi cái này
void runCommand(JsonDocument& doc);
