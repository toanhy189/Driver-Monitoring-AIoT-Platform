#include <Arduino.h>
#include <cstring>

#include "config.h"
#include "pin_config.h"

DeviceConfig ledConfig = {
    LED_PIN,
    700, 500, 300,
    1000, 500, 300,
    0
};

DeviceConfig buzzerConfig = {
    BUZZER_PIN,
    300, 500, 800,
    1000, 500, 300,
    0
};

DeviceConfig motorConfig = {
    MOTOR_PIN,
    300, 500, 800,
    1000, 500, 300,
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

    return {config.medium_s, config.medium_e};
}

void switch_Device(DeviceConfig config, int duration, const char* intensity)
{
    Intensity val = getIntensity(config, intensity);

    int start = millis();

    while (millis() - start < duration)
    {
        digitalWrite(config.pin, HIGH);
        delay(val.start);

        digitalWrite(config.pin, LOW);
        delay(val.end);
    }
}