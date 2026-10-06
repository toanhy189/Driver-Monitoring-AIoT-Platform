#include <Arduino.h>
#include <cstring>

#include "config.h"
#include "device_config.h"

// Khởi động với tất cả đầu ra tắt
void setupPins()
{
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(MOTOR_PIN, LOW);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(MOTOR_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
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

