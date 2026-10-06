#include <ArduinoJson.h>
#include "config.h"
#include "device_config.h"
#include "command_handler.h"
#include "mqtt_client.h"

static DeviceState led = {
    false, 0,
    "", "",
    0, 0,
    0, false,
    0, 0
};

static DeviceState buzzer = {
    false, 0,
    "", "",
    0, 0,
    0, false,
    0, 0
};

static DeviceState motor = {
    false, 0,
    "", "",
    0, 0,
    0, false,
    0, 0
};

bool DeviceState::compareIntensity(const char* newIntensity)
{
    const char* map[] = {"WEAK", "MEDIUM", "STRONG", "CONSTANT"};

    int currentVal = -1;
    int newVal = -1;

    const int size = sizeof(map) / sizeof(map[0]);

    for (int i = 0; i < size; i++)
    {
        if (strcmp(this->intensity, map[i]) == 0)
            currentVal = i;

        if (strcmp(newIntensity, map[i]) == 0)
            newVal = i;
    }

    // intensity không hợp lệ
    if (currentVal == -1 || newVal == -1)
        return false;

    return currentVal <= newVal;
}


// =========================
// Bắt đầu chạy một device
// =========================

static bool switchDevice(
    DeviceState& device, const DeviceConfig& config,
    const char* requestId,
    unsigned long duration, const char* intensity
)
{
    Intensity val = getIntensity(config, intensity);

    // kiểm tra điều kiện đổi lệnh cho thiết bị active
    if (device.active)
    {
        unsigned long elapsed = millis() - device.startTime;
        if(!device.compareIntensity(intensity)){
            return false;
        }
        sendAcks(
            device.requestId,
            "INTERRUPTED", elapsed, nullptr
        );
    }

    // Ghi đè state cũ
    device.active = true;
    strncpy(
        device.requestId,
        requestId,
        sizeof(device.requestId) - 1
    );

    device.requestId[sizeof(device.requestId) - 1] = '\0';

    device.startTime = millis();
    device.duration = duration;

    device.phaseStart = millis();
    device.outputHigh = true;

    device.startMs = val.start;
    device.endMs = val.end;

    digitalWrite(config.pin, HIGH);

    return true;
}


// =========================
// Cập nhật một device
// =========================

static void updateDevice(
    DeviceState& device,
    const DeviceConfig& config
)
{
    if (!device.active)
        return;

    unsigned long now = millis();

    // Hết thời gian chạy
    if (now - device.startTime >= device.duration)
    {
        digitalWrite(config.pin, LOW);
        device.active = false;
        // gửi ack xong việc
        sendAcks(
            device.requestId,
            "COMPLETED", now - device.startTime, nullptr
        );
        return;
    }

    // HIGH -> LOW
    if (device.outputHigh)
    {
        if (now - device.phaseStart >= device.startMs)
        {
            digitalWrite(config.pin, LOW);

            device.outputHigh = false;
            device.phaseStart = now;
        }
    }

    // LOW -> HIGH
    else
    {
        if (now - device.phaseStart >= device.endMs)
        {
            digitalWrite(config.pin, HIGH);

            device.outputHigh = true;
            device.phaseStart = now;
        }
    }
}


// =========================
// Cập nhật cả 3 device
// =========================

void deviceLoop()
{
    updateDevice(led, ledConfig);
    updateDevice(buzzer, buzzerConfig);
    updateDevice(motor, motorConfig);
}


// =========================
// Command handler
// =========================

// =========================
// Xử lý ON cho một device
// =========================

static void handleDeviceOn(
    DeviceState& device,
    const DeviceConfig& config,
    JsonDocument& doc
)
{
    unsigned long start = millis();
    if (doc["duration"].isNull() || doc["intensity"].isNull()){
        sendAcks(
            doc["request_id"],
            "FAILED", millis() - start, "INVALID_PAYLOAD"
        );
        return;
    }
    

    const char* requestId = doc["request_id"];
    const char* intensity = doc["intensity"];
    unsigned long duration = doc["duration"];

    bool sw = switchDevice(
        device, config, requestId, duration, intensity
    );

    if (!sw) {
        sendAcks(
            requestId,
            "FAILED", millis() - start, "INTENSITY_TOO_LOW"
        );
        return;
    }

    sendAcks(
        requestId,
        "STARTED", millis() - start, nullptr
    );
}

// =========================
// Xử lý OFF cho một device
// =========================

static void handleDeviceOff(
    DeviceState& device,
    const DeviceConfig& config,
    JsonDocument& doc
)
{
    if (device.active)
    {
        unsigned long elapsed = millis() - device.startTime;

        sendAcks(
            device.requestId,
            "INTERRUPTED", elapsed, nullptr
        );
    }

    unsigned long start = millis();
    digitalWrite(config.pin, LOW);
    device.active = false;

    sendAcks(
        doc["request_id"],
        "COMPLETED", millis() - start, nullptr
    );
}

// =========================
// Command handler
// =========================

void runCommand(JsonDocument& doc)
{
    const char* command = doc["command"];
    unsigned long start = millis();
    if (!command){
        sendAcks(
            doc["request_id"],
            "FAILED", millis() - start, "INVALID_COMMAND"
        );
        return;
    }

    // =========================
    // LED
    // =========================

    if (strcmp(command, "LED_ON") == 0){
        handleDeviceOn(led, ledConfig, doc);
        return;
    }

    if (strcmp(command, "LED_OFF") == 0){
        handleDeviceOff(led, ledConfig, doc);
        return;
    }

    // =========================
    // BUZZER
    // =========================

    if (strcmp(command, "BUZZER_ON") == 0){
        handleDeviceOn(buzzer, buzzerConfig, doc);
        return;
    }
        

    if (strcmp(command, "BUZZER_OFF") == 0){
        handleDeviceOff(buzzer, buzzerConfig, doc);
        return;
    }


    // =========================
    // MOTOR
    // =========================

    if (strcmp(command, "MOTOR_ON") == 0){
        handleDeviceOn(motor, motorConfig, doc);
        return;
    }

    if (strcmp(command, "MOTOR_OFF") == 0){
        handleDeviceOff(motor, motorConfig, doc);
        return;
    }


    // =========================
    // Command khác
    // =========================

    sendAcks(
        doc["request_id"],
        "FAILED", millis() - start, "UNKNOWN_COMMAND"
    );

}