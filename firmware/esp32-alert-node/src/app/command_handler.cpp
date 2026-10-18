#include <ArduinoJson.h>
#include "config.h"
#include "device_config.h"
#include "command_handler.h"
#include "mqtt_client.h"
#include "request_log.h"

// thêm 2 hằng số phục vụ validate
constexpr unsigned long MAX_DURATION_MS = 60000;  // chưa chốt với BE
constexpr size_t MAX_REQUEST_ID_LEN = 39;         // UUID 36 ký tự; cần khớp bản ghi NVS ở TV1-13

static DeviceState led = {
    false, 0,
    "", "",
    0, 0, 0,
    0, false,
    0, 0
};

static DeviceState buzzer = {
    false, 0,
    "", "",
    0, 0, 0,
    0, false,
    0, 0
};

static DeviceState motor = {
    false, 0,
    "", "",
    0, 0, 0,
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

static bool isValidIntensity(const char* intensity){
    if (intensity == nullptr)
        return false;

    return strcmp(intensity, "WEAK") == 0
        || strcmp(intensity, "MEDIUM") == 0
        || strcmp(intensity, "STRONG") == 0
        || strcmp(intensity, "CONSTANT") == 0;
}

// =========================
// Bắt đầu chạy một device
// =========================

static bool switchDevice(
    DeviceState& device, const DeviceConfig& config,
    const char* requestId, uint32_t requestHash,
    unsigned long duration, const char* intensity,
    const char** errorCode
)
{
    Intensity val = getIntensity(config, intensity);
    // [CONFIG - thêm] Hiện timing đã chụp cho lệnh này để kiểm thử config đang áp dụng.
    Serial.printf("[CMD] %s on=%d off=%d\n", intensity, val.start, val.end);

    // [TV1-13 - thêm] Lưu IN_PROGRESS bền vững trước khi có thể bật đầu ra.
    if (!reqLogStart(requestId, requestHash))
    {
        *errorCode = "STORAGE_ERROR";
        return false;
    }

    // kiểm tra điều kiện đổi lệnh cho thiết bị active
    if (device.active)
    {
        if(!device.compareIntensity(intensity)){
            *errorCode = reqLogFinish(requestId, requestHash, REQ_FAILED, "BUSY")
                             ? "BUSY"
                             : "STORAGE_ERROR";
            return false;
        }
        unsigned long elapsed = millis() - device.startTime;
        bool interruptionLogged = reqLogFinish(
            device.requestId, device.reqHash, REQ_INTERRUPTED, nullptr
        );
        sendAcks(device.requestId,
                 interruptionLogged ? "INTERRUPTED" : "FAILED",
                 elapsed,
                 interruptionLogged ? nullptr : "STORAGE_ERROR");
    }

    // Ghi đè state cũ
    device.active = true;
    strncpy(
        device.requestId,
        requestId,
        sizeof(device.requestId) - 1
    );

    device.requestId[sizeof(device.requestId) - 1] = '\0';
//thêm phần lưu intensity
strncpy(device.intensity, intensity, sizeof(device.intensity) - 1);
device.intensity[sizeof(device.intensity) - 1] = '\0';
device.reqHash = requestHash;

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
        // [TV1-13 - thêm] Ghi trạng thái cuối một lần; không ghi nhật ký trong các nhịp HIGH/LOW.
        bool completionLogged = reqLogFinish(
            device.requestId, device.reqHash, REQ_COMPLETED, nullptr
        );
        sendAcks(device.requestId,
                 completionLogged ? "COMPLETED" : "FAILED",
                 now - device.startTime,
                 completionLogged ? nullptr : "STORAGE_ERROR");
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
    JsonDocument& doc,
    uint32_t requestHash
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
    
/*
    const char* requestId = doc["request_id"];
    const char* intensity = doc["intensity"];
    unsigned long duration = doc["duration"];
*/
//thêm kiểm tra giá trị
const char* requestId = doc["request_id"].as<const char*>();
const char* intensity = doc["intensity"].as<const char*>();

bool ok = requestId != nullptr
       && requestId[0] != '\0'
       && strlen(requestId) <= MAX_REQUEST_ID_LEN
       && doc["duration"].is<unsigned long>()
       && isValidIntensity(intensity);

unsigned long duration = ok ? doc["duration"].as<unsigned long>() : 0;
if (!ok || duration == 0 || duration > MAX_DURATION_MS)
{
    sendAcks(requestId, "FAILED", millis() - start, "INVALID_PAYLOAD");
    return;
}
// hết phần thêm/sửa

    const char* errorCode = nullptr;
    bool sw = switchDevice(
        device, config, requestId, requestHash, duration, intensity, &errorCode
    );

    if (!sw) {
        sendAcks(
            requestId,
            "FAILED", millis() - start, errorCode
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
    JsonDocument& doc,
    uint32_t requestHash
)
{
    unsigned long start = millis();
    const char* requestId = doc["request_id"].as<const char*>();
    bool logStarted = reqLogStart(requestId, requestHash);
    bool wasActive = device.active;
    unsigned long elapsed = millis() - device.startTime;

    // [TV1-13 - thêm] OFF luôn tắt tải để đảm bảo an toàn, kể cả khi NVS không ghi được.
    digitalWrite(config.pin, LOW);
    device.active = false;

    if (wasActive)
    {
        bool interruptionLogged = reqLogFinish(
            device.requestId, device.reqHash, REQ_INTERRUPTED, nullptr
        );
        sendAcks(device.requestId,
                 interruptionLogged ? "INTERRUPTED" : "FAILED",
                 elapsed,
                 interruptionLogged ? nullptr : "STORAGE_ERROR");
    }

    if (!logStarted)
    {
        sendAcks(requestId, "FAILED", millis() - start, "STORAGE_ERROR");
        return;
    }

    bool completionLogged = reqLogFinish(requestId, requestHash, REQ_COMPLETED, nullptr);
    sendAcks(requestId,
             completionLogged ? "COMPLETED" : "FAILED",
             millis() - start,
             completionLogged ? nullptr : "STORAGE_ERROR");
}

// =========================
// Command handler
// =========================

void runCommand(JsonDocument& doc)
{
    const char* command = doc["command"];
    unsigned long start = millis();
    if (!command)
    {
        sendAcks(
            doc["request_id"],
            "FAILED", millis() - start, "INVALID_COMMAND"
        );
        return;
    }

    const char* requestId = doc["request_id"].is<const char*>()
                                ? doc["request_id"].as<const char*>()
                                : nullptr;
    if (requestId == nullptr || requestId[0] == '\0' ||
        strlen(requestId) > MAX_REQUEST_ID_LEN)
    {
        sendAcks(requestId, "FAILED", millis() - start, "INVALID_PAYLOAD");
        return;
    }

    bool isKnownCommand =
        strcmp(command, "LED_ON") == 0 || strcmp(command, "LED_OFF") == 0 ||
        strcmp(command, "BUZZER_ON") == 0 || strcmp(command, "BUZZER_OFF") == 0 ||
        strcmp(command, "MOTOR_ON") == 0 || strcmp(command, "MOTOR_OFF") == 0;
    if (!isKnownCommand)
    {
        sendAcks(requestId, "FAILED", millis() - start, "UNKNOWN_COMMAND");
        return;
    }

    unsigned long duration = doc["duration"].is<unsigned long>()
                                 ? doc["duration"].as<unsigned long>()
                                 : 0;
    const char* intensity = doc["intensity"].is<const char*>()
                                ? doc["intensity"].as<const char*>()
                                : "";
    uint32_t requestHash = reqHash(command, duration, intensity);
    // [TV1-13 - thêm] Tin nhắn lặp trả ACK theo bản ghi, không chạy lại tải.
    if (reqLogHandleDuplicate(requestId, requestHash))
        return;

    // =========================
    // LED
    // =========================

    if (strcmp(command, "LED_ON") == 0){
        handleDeviceOn(led, ledConfig, doc, requestHash);
        return;
    }

    if (strcmp(command, "LED_OFF") == 0){
        handleDeviceOff(led, ledConfig, doc, requestHash);
        return;
    }

    // =========================
    // BUZZER
    // =========================

    if (strcmp(command, "BUZZER_ON") == 0){
        handleDeviceOn(buzzer, buzzerConfig, doc, requestHash);
        return;
    }
        

    if (strcmp(command, "BUZZER_OFF") == 0){
        handleDeviceOff(buzzer, buzzerConfig, doc, requestHash);
        return;
    }


    // =========================
    // MOTOR
    // =========================

    if (strcmp(command, "MOTOR_ON") == 0){
        handleDeviceOn(motor, motorConfig, doc, requestHash);
        return;
    }

    if (strcmp(command, "MOTOR_OFF") == 0){
        handleDeviceOff(motor, motorConfig, doc, requestHash);
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