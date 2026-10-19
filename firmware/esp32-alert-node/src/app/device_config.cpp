#include <Arduino.h>
#include <cstring>

#include "config.h"
#include "device_config.h"

// Khởi động với tất cả đầu ra tắt
void setupPins()
{
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(MOTOR_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
 //đổi thứ tự pinMode(...) và   digitalWrite(...) 
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(MOTOR_PIN, LOW);

}


DeviceConfig ledConfig = {
    LED_PIN,
    700, 500, 300, 1000,
    1000, 500, 300, 0,
    0
};

DeviceConfig buzzerConfig = {
    BUZZER_PIN,
    300, 500, 800, 1000,
    1000, 500, 300, 0,
    0
};

DeviceConfig motorConfig = {
    MOTOR_PIN,
    300, 500, 800, 1000,
    1000, 500, 300, 0,
    0
};

namespace
{
// [CONFIG - thêm] Giới hạn on_ms/off_ms theo hợp đồng config đã chốt với TV2.
constexpr int MIN_ON_MS = 50;
constexpr int MAX_ON_MS = 5000;
constexpr int MIN_OFF_MS = 50;
constexpr int MAX_OFF_MS = 10000;

bool readTiming(
    JsonVariantConst outputTimings,
    const char* level,
    DeviceTiming& timing,
    const char** errorCode
)
{
    // Kiểm tra kiểu số nguyên và giới hạn trước khi ghi vào bản cấu hình tạm.
    JsonVariantConst pair = outputTimings[level];
    if (!pair.is<JsonObjectConst>())
    {
        *errorCode = "INVALID_TIMINGS";
        return false;
    }

    JsonVariantConst onValue = pair["on_ms"];
    if (!onValue.is<int>())
    {
        *errorCode = "INVALID_ON_MS";
        return false;
    }
    int newOnMs = onValue.as<int>();
    if (newOnMs < MIN_ON_MS || newOnMs > MAX_ON_MS)
    {
        *errorCode = "ON_MS_OUT_OF_RANGE";
        return false;
    }

    JsonVariantConst offValue = pair["off_ms"];
    if (!offValue.is<int>())
    {
        *errorCode = "INVALID_OFF_MS";
        return false;
    }
    int newOffMs = offValue.as<int>();
    if (newOffMs < MIN_OFF_MS || newOffMs > MAX_OFF_MS)
    {
        *errorCode = "OFF_MS_OUT_OF_RANGE";
        return false;
    }

    timing.onMs = newOnMs;
    timing.offMs = newOffMs;
    return true;
}

bool readOutputTimings(
    JsonVariantConst timings,
    const char* output,
    DeviceTiming (&values)[3],
    const char** errorCode
)
{
    // [CONFIG - thêm] Bắt buộc đủ mức 1/2/3; lần lượt ánh xạ sang WEAK/MEDIUM/STRONG.
    JsonVariantConst outputTimings = timings[output];
    if (!outputTimings.is<JsonObjectConst>())
    {
        *errorCode = "INVALID_TIMINGS";
        return false;
    }

    return readTiming(outputTimings, "1", values[0], errorCode) &&
           readTiming(outputTimings, "2", values[1], errorCode) &&
           readTiming(outputTimings, "3", values[2], errorCode);
}

void setConfigTimings(
    DeviceConfig& config,
    const DeviceTiming (&values)[3]
)
{
    config.weak_s = values[0].onMs;
    config.medium_s = values[1].onMs;
    config.strong_s = values[2].onMs;
    config.weak_e = values[0].offMs;
    config.medium_e = values[1].offMs;
    config.strong_e = values[2].offMs;
}
}

bool parseDeviceTimings(
    JsonVariantConst timings,
    DeviceTimingSet& result,
    const char** errorCode
)
{
    // Chỉ trả bản tạm hoàn chỉnh khi cả 3 tải x 3 mức đều hợp lệ.
    if (!timings.is<JsonObjectConst>())
    {
        *errorCode = "INVALID_TIMINGS";
        return false;
    }

    DeviceTimingSet candidate{};
    if (!readOutputTimings(timings, "led", candidate.values[0], errorCode) ||
        !readOutputTimings(timings, "buzzer", candidate.values[1], errorCode) ||
        !readOutputTimings(timings, "motor", candidate.values[2], errorCode))
    {
        return false;
    }

    result = candidate;
    return true;
}

void applyDeviceTimings(const DeviceTimingSet& timings)
{
    // [CONFIG - thêm] Chỉ gọi sau validate và lưu NVS; CONSTANT giữ nguyên giá trị firmware.
    setConfigTimings(ledConfig, timings.values[0]);
    setConfigTimings(buzzerConfig, timings.values[1]);
    setConfigTimings(motorConfig, timings.values[2]);
}

Intensity getIntensity(DeviceConfig config, const char* intensity)
{
    if (strcmp(intensity, "WEAK") == 0)
        return {config.weak_s, config.weak_e};

    if (strcmp(intensity, "MEDIUM") == 0)
        return {config.medium_s, config.medium_e};

    if (strcmp(intensity, "STRONG") == 0)
        return {config.strong_s, config.strong_e};

    if (strcmp(intensity, "CONSTANT") == 0)
        return {config.constant_s, config.constant_e};

    return {config.medium_s, config.medium_e};
}
