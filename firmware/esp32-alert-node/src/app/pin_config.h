#ifndef PIN_CONFIG_H
#define PIN_CONFIG_H

struct DeviceConfig
{
    int pin;
    int weak_s, medium_s, strong_s;
    int weak_e, medium_e, strong_e;
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

void switch_Device(DeviceConfig config, int duration, const char* intensity);

#endif