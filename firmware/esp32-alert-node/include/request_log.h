#pragma once

#include <Arduino.h>

// [TV1-13 - tệp mới] Giao diện nhật ký chống xử lý lặp, lưu request_id/hash/trạng thái vào NVS.
enum ReqState : uint8_t
{
    REQ_EMPTY = 0,
    REQ_IN_PROGRESS = 1,
    REQ_COMPLETED = 2,
    REQ_FAILED = 3,
    REQ_INTERRUPTED = 4
};

void reqLogBegin();
uint32_t reqHash(const char* command, unsigned long duration, const char* intensity);
bool reqLogHandleDuplicate(const char* id, uint32_t hash);
bool reqLogStart(const char* id, uint32_t hash);
bool reqLogFinish(const char* id, uint32_t hash, ReqState state, const char* error);
void reqLogPublishPending();
