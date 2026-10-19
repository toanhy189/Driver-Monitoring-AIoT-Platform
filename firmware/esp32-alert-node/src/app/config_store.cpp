// [CONFIG - tệp mới] Quản lý vòng đời config: kiểm tra payload, lưu NVS có CRC,
// khôi phục sau reboot và chỉ xác nhận APPLIED sau khi lưu thành công.
#include <Arduino.h>
#include <Preferences.h>
#include <cstddef>
#include <cstring>

#include "config_store.h"
#include "device_config.h"
#include "mqtt_client.h"

namespace
{
constexpr int ON_MIN_MS = 50;
constexpr int ON_MAX_MS = 5000;
constexpr int OFF_MIN_MS = 50;
constexpr int OFF_MAX_MS = 10000;
// [CONFIG - thêm] Dấu nhận dạng giúp loại dữ liệu NVS sai định dạng/phiên bản.
constexpr uint32_t CONFIG_MAGIC = 0xA1E27C01;
constexpr char NVS_NAMESPACE[] = "alert";
constexpr char NVS_KEY[] = "cfg";
constexpr size_t CONFIG_ID_SIZE = 40;

// [CONFIG - thêm] Bản lưu cố định gồm ID, timing và CRC; không lưu con trỏ/JSON động vào NVS.
struct StoredConfig
{
    uint32_t magic;
    char configId[40];
    DeviceTimingSet timings;
    uint32_t crc;
};

char activeConfigId[CONFIG_ID_SIZE] = "default";

// [CONFIG - thêm] CRC32 kiểu FNV-1a để phát hiện bản ghi NVS bị hỏng.
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

uint32_t calculateConfigCrc(const StoredConfig& config)
{
    return calculateCrc(&config, offsetof(StoredConfig, crc));
}

bool validTimings(const DeviceTimingSet& timings)
{
    // Kiểm tra lại dữ liệu đọc từ NVS trước khi cho phép áp dụng vào phần cứng.
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

void applyStoredConfig(const StoredConfig& config)
{
    // RAM và config_id chỉ đổi sau khi bản ghi đã được kiểm tra hoặc lưu thành công.
    applyDeviceTimings(config.timings);
    memcpy(activeConfigId, config.configId, sizeof(activeConfigId));
}

bool saveConfig(const StoredConfig& config)
{
    // [CONFIG - thêm] Ghi cấu hình dạng nhị phân và báo lỗi rõ nếu NVS không ghi đủ dữ liệu.
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

bool parseConfig(JsonDocument& doc, StoredConfig& result, const char** errorCode)
{
    // [CONFIG - thêm] Parse vào bản tạm; không đụng config đang chạy nếu bất kỳ trường nào sai.
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

    memset(&result, 0, sizeof(result));
    result.magic = CONFIG_MAGIC;
    memcpy(result.configId, configId, configIdLength + 1);
    result.timings = timings;
    result.crc = calculateConfigCrc(result);
    return true;
}
}

bool loadSavedConfig()
{
    // [CONFIG - thêm] Khôi phục config sau setupPins(); nếu thiếu/hỏng thì giữ mặc định biên dịch sẵn.
    Preferences preferences;
    // Mở read-write để namespace chưa tồn tại ở lần boot đầu được xem là chưa có config.
    if (!preferences.begin(NVS_NAMESPACE, false))
    {
        Serial.println("[CONFIG] NVS unavailable; using compiled defaults");
        return false;
    }

    StoredConfig config{};
    size_t storedSize = preferences.getBytes(NVS_KEY, &config, sizeof(config));
    preferences.end();

    if (storedSize == 0)
    {
        Serial.println("[CONFIG] No saved config; using compiled defaults");
        return false;
    }

    bool idTerminated = memchr(config.configId, '\0', sizeof(config.configId)) != nullptr;
    if (storedSize != sizeof(config) ||
        config.magic != CONFIG_MAGIC ||
        !idTerminated ||
        config.configId[0] == '\0' ||
        !validTimings(config.timings) ||
        config.crc != calculateConfigCrc(config))
    {
        Serial.println("[CONFIG] Saved config invalid; using compiled defaults");
        return false;
    }

    applyStoredConfig(config);
    Serial.printf("[CONFIG] loaded config_id=%s\n", activeConfigId);
    return true;
}

const char* currentConfigId()
{
    // [CONFIG - thêm] Dùng chung ID đang áp dụng cho heartbeat và ACK config.
    return activeConfigId;
}

void onConfigMessage(JsonDocument& doc)
{
    // [CONFIG - thêm] Config ID trùng được xác nhận lại mà không ghi flash lần nữa.
    const char* incomingId = doc["config_id"].is<const char*>()
                                 ? doc["config_id"].as<const char*>()
                                 : nullptr;
    if (incomingId != nullptr && strcmp(incomingId, activeConfigId) == 0)
    {
        sendConfigAck(incomingId, "APPLIED", nullptr);
        return;
    }

    StoredConfig candidate{};
    const char* errorCode = nullptr;
    if (!parseConfig(doc, candidate, &errorCode))
    {
        sendConfigAck(incomingId, "REJECTED", errorCode);
        return;
    }

    if (!saveConfig(candidate))
    {
        sendConfigAck(candidate.configId, "REJECTED", "STORAGE_ERROR");
        return;
    }

    // Ghi NVS trước; chỉ sau đó mới đổi RAM và gửi APPLIED.
    applyStoredConfig(candidate);
    sendConfigAck(candidate.configId, "APPLIED", nullptr);
}
