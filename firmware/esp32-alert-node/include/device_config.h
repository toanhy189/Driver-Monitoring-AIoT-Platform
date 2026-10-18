#pragma once

#include <ArduinoJson.h>

void setupPins();

struct DeviceConfig
{
    int pin;
    int weak_s, medium_s, strong_s, constant_s;
    int weak_e, medium_e, strong_e, constant_e;
    int offset;
};

struct Intensity
{
    int start;
    int end;
};

struct DeviceTiming
{
    // Timing cho một mức; onMs/offMs là thời gian bật/tắt theo mili giây.
    int32_t onMs;
    int32_t offMs;
};

struct DeviceTimingSet
{
    // Thứ tự thiết bị: LED, buzzer, motor; thứ tự mức: WEAK, MEDIUM, STRONG.
    DeviceTiming values[3][3];
};

extern DeviceConfig ledConfig;
extern DeviceConfig buzzerConfig;
extern DeviceConfig motorConfig;

Intensity getIntensity(DeviceConfig config, const char* intensity);
// [CONFIG - thêm] Parse/validate vào bản tạm; lỗi thì không thay đổi cấu hình đang chạy.
bool parseDeviceTimings(JsonVariantConst timings, DeviceTimingSet& result, const char** errorCode);
// [CONFIG - thêm] Chép timing đã hợp lệ vào cấu hình RAM mà lệnh mới sẽ sử dụng.
void applyDeviceTimings(const DeviceTimingSet& timings);
