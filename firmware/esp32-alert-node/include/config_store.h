#pragma once

#include <ArduinoJson.h>
#include <cstdint>

// [CONFIG - W4-TV1-01] Quản lý vòng đời cấu hình, lưu trữ NVS có metadata và kiểm tra phiên bản.
bool loadSavedConfig();
void onConfigMessage(JsonDocument& doc);
const char* currentConfigId();
uint32_t currentConfigRevision();
