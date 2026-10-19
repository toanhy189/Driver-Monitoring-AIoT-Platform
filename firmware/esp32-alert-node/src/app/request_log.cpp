// [TV1-13 - tệp mới] Lưu tối đa 16 kết quả command trong một blob NVS để chống chạy lặp
// sau MQTT retry/reboot; chỉ ghi lúc bắt đầu, kết thúc, hoặc phục hồi IN_PROGRESS khi boot.
#include <Arduino.h>
#include <Preferences.h>
#include <cstddef>
#include <cstring>
#include <ctime>

#include "request_log.h"
#include "mqtt_client.h"

namespace
{
constexpr size_t LOG_SIZE = 16;
constexpr uint32_t LOG_MAGIC = 0xA1E27C02;
constexpr uint32_t MAX_AGE_SECONDS = 24UL * 60UL * 60UL;
constexpr size_t REQUEST_ID_SIZE = 40;
constexpr size_t ERROR_SIZE = 32;
constexpr char NVS_NAMESPACE[] = "alert";
constexpr char NVS_KEY[] = "reqlog";

struct RequestRecord
{
    char id[REQUEST_ID_SIZE];
    uint32_t hash;
    uint32_t seq;
    uint32_t timestamp;
    uint8_t state;
    char error[ERROR_SIZE];
};

struct RequestLog
{
    uint32_t magic;
    uint32_t nextSequence;
    RequestRecord records[LOG_SIZE];
    uint32_t crc;
};

RequestLog requestLog{};
bool pendingBootAck[LOG_SIZE]{};
uint32_t successfulWriteCount = 0;

uint32_t fnv1a(const void* data, size_t length)
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

uint32_t currentTimestamp()
{
    time_t now = time(nullptr);
    return now > 1700000000 ? static_cast<uint32_t>(now) : 0;
}

uint32_t calculateLogCrc(const RequestLog& log)
{
    return fnv1a(&log, offsetof(RequestLog, crc));
}

bool saveLog()
{
    requestLog.crc = calculateLogCrc(requestLog);

    Preferences preferences;
    if (!preferences.begin(NVS_NAMESPACE, false))
    {
        Serial.println("[REQLOG] NVS open failed");
        return false;
    }

    size_t written = preferences.putBytes(NVS_KEY, &requestLog, sizeof(requestLog));
    preferences.end();
    if (written != sizeof(requestLog))
    {
        Serial.printf("[REQLOG] NVS write incomplete: %u/%u bytes\n",
                      static_cast<unsigned int>(written),
                      static_cast<unsigned int>(sizeof(requestLog)));
        return false;
    }

    ++successfulWriteCount;
    Serial.printf("[REQLOG] flash write #%lu\n",
                  static_cast<unsigned long>(successfulWriteCount));
    return true;
}

RequestRecord* findRecord(const char* id)
{
    if (id == nullptr)
        return nullptr;

    for (RequestRecord& record : requestLog.records)
    {
        if (record.state != REQ_EMPTY && strcmp(record.id, id) == 0)
            return &record;
    }
    return nullptr;
}

RequestRecord* allocateSlot()
{
    RequestRecord* oldest = nullptr;
    for (RequestRecord& record : requestLog.records)
    {
        if (record.state == REQ_EMPTY)
            return &record;
        if (record.state == REQ_IN_PROGRESS)
            continue;
        if (oldest == nullptr || record.seq < oldest->seq)
            oldest = &record;
    }
    return oldest;
}

void purgeExpiredRecords()
{
    uint32_t now = currentTimestamp();
    if (now == 0)
        return;

    for (RequestRecord& record : requestLog.records)
    {
        if (record.state != REQ_EMPTY &&
            record.state != REQ_IN_PROGRESS &&
            record.timestamp != 0 &&
            now >= record.timestamp &&
            now - record.timestamp > MAX_AGE_SECONDS)
        {
            memset(&record, 0, sizeof(record));
        }
    }
}

bool isExpired(const RequestRecord& record, uint32_t now)
{
    return record.state != REQ_EMPTY &&
           record.state != REQ_IN_PROGRESS &&
           record.timestamp != 0 &&
           now != 0 &&
           now >= record.timestamp &&
           now - record.timestamp > MAX_AGE_SECONDS;
}

bool validLog(const RequestLog& log)
{
    if (log.magic != LOG_MAGIC || log.crc != calculateLogCrc(log))
        return false;

    for (const RequestRecord& record : log.records)
    {
        if (record.state == REQ_EMPTY)
            continue;

        if (record.state > REQ_INTERRUPTED ||
            memchr(record.id, '\0', sizeof(record.id)) == nullptr ||
            record.id[0] == '\0' ||
            memchr(record.error, '\0', sizeof(record.error)) == nullptr)
        {
            return false;
        }
    }
    return true;
}
}

uint32_t reqHash(const char* command, unsigned long duration, const char* intensity)
{
    char payload[96];
    int length = snprintf(payload, sizeof(payload), "%s|%lu|%s",
                          command != nullptr ? command : "",
                          duration,
                          intensity != nullptr ? intensity : "");
    if (length < 0)
        return 0;
    size_t boundedLength = static_cast<size_t>(length);
    if (boundedLength >= sizeof(payload))
        boundedLength = sizeof(payload) - 1;
    return fnv1a(payload, boundedLength);
}

void reqLogBegin()
{
    memset(&requestLog, 0, sizeof(requestLog));
    memset(pendingBootAck, 0, sizeof(pendingBootAck));
    successfulWriteCount = 0;

    RequestLog loaded{};
    Preferences preferences;
    bool loadedFromNvs = false;
    if (preferences.begin(NVS_NAMESPACE, true))
    {
        size_t storedSize = preferences.getBytes(NVS_KEY, &loaded, sizeof(loaded));
        preferences.end();
        loadedFromNvs = storedSize == sizeof(loaded) && validLog(loaded);
    }

    if (!loadedFromNvs)
    {
        requestLog.magic = LOG_MAGIC;
        requestLog.nextSequence = 1;
        Serial.println("[REQLOG] empty/invalid, start fresh");
        return;
    }

    requestLog = loaded;
    bool changed = false;
    for (size_t index = 0; index < LOG_SIZE; ++index)
    {
        RequestRecord& record = requestLog.records[index];
        if (record.state == REQ_IN_PROGRESS)
        {
            record.state = REQ_INTERRUPTED;
            strlcpy(record.error, "REBOOTED", sizeof(record.error));
            record.timestamp = currentTimestamp();
            pendingBootAck[index] = true;
            changed = true;
            Serial.printf("[REQLOG] %s was IN_PROGRESS -> INTERRUPTED\n", record.id);
        }
    }

    if (changed && !saveLog())
        Serial.println("[REQLOG] Could not persist boot recovery state");
}

bool reqLogHandleDuplicate(const char* id, uint32_t hash)
{
    RequestRecord* record = findRecord(id);
    if (record == nullptr)
        return false;

    // Let reqLogStart purge and replace expired records in the same NVS write.
    if (isExpired(*record, currentTimestamp()))
        return false;

    if (record->hash != hash)
    {
        sendAcks(id, "FAILED", 0, "DUPLICATE_ID_MISMATCH");
        return true;
    }

    switch (record->state)
    {
    case REQ_IN_PROGRESS:
        sendAcks(id, "STARTED", 0, nullptr);
        break;
    case REQ_COMPLETED:
        sendAcks(id, "COMPLETED", 0, nullptr);
        break;
    case REQ_INTERRUPTED:
        sendAcks(id, "INTERRUPTED", 0, record->error[0] != '\0' ? record->error : nullptr);
        break;
    default:
        sendAcks(id, "FAILED", 0, record->error[0] != '\0' ? record->error : nullptr);
        break;
    }
    return true;
}

bool reqLogStart(const char* id, uint32_t hash)
{
    if (id == nullptr || id[0] == '\0' || strlen(id) >= REQUEST_ID_SIZE)
    {
        return false;
    }

    RequestLog previous = requestLog;
    purgeExpiredRecords();
    if (findRecord(id) != nullptr)
    {
        requestLog = previous;
        return false;
    }

    RequestRecord* record = allocateSlot();
    if (record == nullptr)
    {
        requestLog = previous;
        return false;
    }

    memset(record, 0, sizeof(*record));
    strlcpy(record->id, id, sizeof(record->id));
    record->hash = hash;
    record->state = REQ_IN_PROGRESS;
    record->seq = requestLog.nextSequence++;
    record->timestamp = currentTimestamp();

    if (saveLog())
        return true;

    requestLog = previous;
    return false;
}

bool reqLogFinish(const char* id, uint32_t hash, ReqState state, const char* error)
{
    RequestRecord* record = findRecord(id);
    // Chỉ cho phép một chuyển trạng thái cuối từ IN_PROGRESS; ngăn ghi đè kết quả đã chốt.
    if (record == nullptr || record->hash != hash ||
        record->state != REQ_IN_PROGRESS ||
        state < REQ_COMPLETED || state > REQ_INTERRUPTED)
    {
        Serial.printf("[REQLOG] Cannot finish request_id=%s state=%u\n",
                      id != nullptr ? id : "(missing)",
                      static_cast<unsigned int>(state));
        return false;
    }

    RequestLog previous = requestLog;
    record->state = static_cast<uint8_t>(state);
    record->timestamp = currentTimestamp();
    strlcpy(record->error, error != nullptr ? error : "", sizeof(record->error));

    if (saveLog())
        return true;

    requestLog = previous;
    record = findRecord(id);
    if (record != nullptr)
    {
        record->state = REQ_FAILED;
        record->timestamp = currentTimestamp();
        strlcpy(record->error, "STORAGE_ERROR", sizeof(record->error));
    }
    Serial.printf("[REQLOG] Failed to persist final state for request_id=%s\n", id);
    return false;
}

void reqLogPublishPending()
{
    for (size_t index = 0; index < LOG_SIZE; ++index)
    {
        if (!pendingBootAck[index])
            continue;

        RequestRecord& record = requestLog.records[index];
        if (sendAcks(record.id, "INTERRUPTED", 0, "REBOOTED"))
            pendingBootAck[index] = false;
    }
}
