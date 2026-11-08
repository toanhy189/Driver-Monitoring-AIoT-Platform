// [CONFIG - W4-TV1-01] Quản lý vòng đời config: kiểm tra payload, lưu NVS có CRC & metadata,
// xét tương thích bản NVS cũ (V1 -> V2), kiểm tra phiên bản cũ và so sánh nội dung cho ID trùng.
#include <Arduino.h>
#include <Preferences.h>
#include <cstddef>
#include <cstring>
#include <ctime>

#include "config_store.h"
#include "device_config.h"
#include "mqtt_client.h"

namespace
{
constexpr int ON_MIN_MS = 50;
constexpr int ON_MAX_MS = 5000;
constexpr int OFF_MIN_MS = 50;
constexpr int OFF_MAX_MS = 10000;

// [W4-TV1-01] Định danh bản ghi NVS cũ (V1) và mới (V2)
constexpr uint32_t CONFIG_MAGIC_V1 = 0xA1E27C01;
constexpr uint32_t CONFIG_MAGIC_V2 = 0xA1E27C02;

constexpr char NVS_NAMESPACE[] = "alert";
constexpr char NVS_KEY[] = "cfg";
constexpr size_t CONFIG_ID_SIZE = 40;

// Bản lưu NVS cũ (V1) không có metadata revision / appliedAt
struct StoredConfigV1
{
    uint32_t magic;
    char configId[40];
    DeviceTimingSet timings;
    uint32_t crc;
};

// [W4-TV1-01] Bản lưu NVS mới (V2) có metadata revision & appliedAt
struct StoredConfigV2
{
    uint32_t magic;
    char configId[40];
    uint32_t revision;
    uint32_t appliedAt;
    DeviceTimingSet timings;
    uint32_t crc;
};

char activeConfigId[CONFIG_ID_SIZE] = "default";
uint32_t activeRevision = 0;
DeviceTimingSet activeTimings{};

// CRC kiểu FNV-1a
uint32_t calculateCrc(const void* data, size_t length)
{
    const uint8_t* bytes = static_cast<const uint8_t*>(data);
    uint32_t hash = 2166136261u;
    while (length-- > 0)
    {
        hash ^= *bytes++;
        hash *= 16777619u;
    }
    return hash;
}

uint32_t calculateConfigCrcV1(const StoredConfigV1& config)
{
    return calculateCrc(&config, offsetof(StoredConfigV1, crc));
}

uint32_t calculateConfigCrcV2(const StoredConfigV2& config)
{
    return calculateCrc(&config, offsetof(StoredConfigV2, crc));
}

bool validTimings(const DeviceTimingSet& timings)
{
    for (const auto& device : timings.values)
    {
        for (const DeviceTiming& timing : device)
        {
            if (timing.onMs < ON_MIN_MS || timing.onMs > ON_MAX_MS ||
                timing.offMs < OFF_MIN_MS || timing.offMs > OFF_MAX_MS)
            {
                return false;
            }
        }
    }
    return true;
}

bool timingsEqual(const DeviceTimingSet& a, const DeviceTimingSet& b)
{
    return memcmp(&a, &b, sizeof(DeviceTimingSet)) == 0;
}

uint32_t getCurrentTimestamp()
{
    time_t now = time(nullptr);
    return now > 1700000000 ? static_cast<uint32_t>(now) : static_cast<uint32_t>(millis() / 1000);
}

void applyStoredConfig(const StoredConfigV2& config)
{
    applyDeviceTimings(config.timings);
    memcpy(activeConfigId, config.configId, sizeof(activeConfigId));
    activeRevision = config.revision;
    activeTimings = config.timings;
}

bool saveConfig(const StoredConfigV2& config)
{
    Preferences preferences;
    if (!preferences.begin(NVS_NAMESPACE, false))
    {
        Serial.println("[CONFIG] NVS open failed while saving");
        return false;
    }

    size_t written = preferences.putBytes(NVS_KEY, &config, sizeof(config));
    preferences.end();
    if (written != sizeof(config))
    {
        Serial.printf("[CONFIG] NVS write incomplete: %u/%u bytes\n",
                      static_cast<unsigned int>(written),
                      static_cast<unsigned int>(sizeof(config)));
        return false;
    }
    return true;
}

bool parseConfig(JsonDocument& doc, StoredConfigV2& result, const char** errorCode)
{
    if (!doc["config_id"].is<const char*>())
    {
        *errorCode = "INVALID_CONFIG_ID";
        return false;
    }

    const char* configId = doc["config_id"].as<const char*>();
    size_t configIdLength = strlen(configId);
    if (configIdLength == 0 || configIdLength >= sizeof(result.configId))
    {
        *errorCode = "INVALID_CONFIG_ID";
        return false;
    }

    DeviceTimingSet timings{};
    if (!parseDeviceTimings(doc["timings"].as<JsonVariantConst>(), timings, errorCode))
        return false;

    // Lấy revision nếu có (hỗ trợ cả revision lẫn version)
    uint32_t revision = 0;
    if (doc["revision"].is<uint32_t>())
    {
        revision = doc["revision"].as<uint32_t>();
    }
    else if (doc["version"].is<uint32_t>())
    {
        revision = doc["version"].as<uint32_t>();
    }

    memset(&result, 0, sizeof(result));
    result.magic = CONFIG_MAGIC_V2;
    memcpy(result.configId, configId, configIdLength + 1);
    result.revision = revision;
    result.appliedAt = getCurrentTimestamp();
    result.timings = timings;
    result.crc = calculateConfigCrcV2(result);
    return true;
}
}

// [W4-TV1-01] Nạp cấu hình từ NVS, xét tính tương thích ngược với bản ghi V1
bool loadSavedConfig()
{
    Preferences preferences;
    if (!preferences.begin(NVS_NAMESPACE, false))
    {
        Serial.println("[CONFIG] NVS unavailable; using compiled defaults");
        return false;
    }

    uint8_t buffer[sizeof(StoredConfigV2)]{};
    size_t storedSize = preferences.getBytes(NVS_KEY, buffer, sizeof(buffer));
    preferences.end();

    if (storedSize == 0)
    {
        Serial.println("[CONFIG] No saved config; using compiled defaults");
        return false;
    }

    // 1. Thử nạp định dạng V2 (mới có metadata)
    if (storedSize == sizeof(StoredConfigV2))
    {
        StoredConfigV2 configV2{};
        memcpy(&configV2, buffer, sizeof(StoredConfigV2));

        bool idTerminated = memchr(configV2.configId, '\0', sizeof(configV2.configId)) != nullptr;
        if (configV2.magic == CONFIG_MAGIC_V2 &&
            idTerminated &&
            configV2.configId[0] != '\0' &&
            validTimings(configV2.timings) &&
            configV2.crc == calculateConfigCrcV2(configV2))
        {
            applyStoredConfig(configV2);
            Serial.printf("[CONFIG] Loaded V2 config_id=%s revision=%lu\n",
                          activeConfigId, static_cast<unsigned long>(activeRevision));
            return true;
        }
    }

    // 2. Thử nạp định dạng V1 (tương thích ngược với bản ghi cũ trong Flash)
    if (storedSize == sizeof(StoredConfigV1))
    {
        StoredConfigV1 configV1{};
        memcpy(&configV1, buffer, sizeof(StoredConfigV1));

        bool idTerminated = memchr(configV1.configId, '\0', sizeof(configV1.configId)) != nullptr;
        if (configV1.magic == CONFIG_MAGIC_V1 &&
            idTerminated &&
            configV1.configId[0] != '\0' &&
            validTimings(configV1.timings) &&
            configV1.crc == calculateConfigCrcV1(configV1))
        {
            // Nâng cấp lên V2 và lưu lại metadata
            StoredConfigV2 upgraded{};
            upgraded.magic = CONFIG_MAGIC_V2;
            memcpy(upgraded.configId, configV1.configId, sizeof(upgraded.configId));
            upgraded.revision = 1;
            upgraded.appliedAt = getCurrentTimestamp();
            upgraded.timings = configV1.timings;
            upgraded.crc = calculateConfigCrcV2(upgraded);

            applyStoredConfig(upgraded);
            saveConfig(upgraded);
            Serial.printf("[CONFIG] Migrated legacy V1 config_id=%s to V2 format\n", activeConfigId);
            return true;
        }
    }

    Serial.println("[CONFIG] Saved config invalid/corrupted; using compiled defaults");
    return false;
}

const char* currentConfigId()
{
    return activeConfigId;
}

uint32_t currentConfigRevision()
{
    return activeRevision;
}

// [W4-TV1-01 & W4-TV1-02] Xử lý cấu hình nhận từ MQTT
void onConfigMessage(JsonDocument& doc)
{
    const char* incomingId = doc["config_id"].is<const char*>()
                                 ? doc["config_id"].as<const char*>()
                                 : nullptr;

    StoredConfigV2 candidate{};
    const char* errorCode = nullptr;
    if (!parseConfig(doc, candidate, &errorCode))
    {
        sendConfigAck(incomingId, "REJECTED", errorCode);
        return;
    }

    // [W4-TV1-01] Xử lý khi ID trùng với config đang áp dụng: so sánh nội dung
    if (incomingId != nullptr && strcmp(incomingId, activeConfigId) == 0)
    {
        if (timingsEqual(candidate.timings, activeTimings))
        {
            // Nội dung hoàn toàn trùng khớp: xác nhận lại không ghi Flash
            Serial.println("[CONFIG] Duplicate config_id received with identical timings");
            sendConfigAck(incomingId, "APPLIED", nullptr);
            return;
        }
        else
        {
            // Trùng ID nhưng nội dung timing khác nhau: từ chối do xung đột
            Serial.println("[CONFIG] Duplicate config_id with conflicting timings detected!");
            sendConfigAck(incomingId, "REJECTED", "DUPLICATE_ID_MISMATCH");
            return;
        }
    }

    // [W4-TV1-01] Kiểm tra phiên bản cũ: từ chối nếu revision nhỏ hơn hoặc bằng revision đang chạy
    if (candidate.revision > 0 && activeRevision > 0 && candidate.revision <= activeRevision)
    {
        Serial.printf("[CONFIG] Stale revision rejected: incoming=%lu, active=%lu\n",
                      static_cast<unsigned long>(candidate.revision),
                      static_cast<unsigned long>(activeRevision));
        sendConfigAck(candidate.configId, "REJECTED", "STALE_REVISION");
        return;
    }

    // Lưu vào Flash NVS
    if (!saveConfig(candidate))
    {
        sendConfigAck(candidate.configId, "REJECTED", "STORAGE_ERROR");
        return;
    }

    // [W4-TV1-02] Cập nhật RAM (applyDeviceTimings):
    // Lệnh đang chạy vẫn giữ timing đã chụp trong DeviceState. Lệnh tiếp theo sẽ nhận timing mới này.
    applyStoredConfig(candidate);
    Serial.printf("[CONFIG] Applied new config_id=%s revision=%lu\n",
                  activeConfigId, static_cast<unsigned long>(activeRevision));
    sendConfigAck(candidate.configId, "APPLIED", nullptr);
}
