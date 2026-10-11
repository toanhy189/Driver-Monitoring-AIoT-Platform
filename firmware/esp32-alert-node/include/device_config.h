#pragma once

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

extern DeviceConfig ledConfig;
extern DeviceConfig buzzerConfig;
extern DeviceConfig motorConfig;

Intensity getIntensity(DeviceConfig config, const char* intensity);

