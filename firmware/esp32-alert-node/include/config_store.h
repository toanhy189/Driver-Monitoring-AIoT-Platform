#pragma once

#include <ArduinoJson.h>

// [CONFIG - tệp mới] Giao diện lưu/khôi phục cấu hình và xử lý config nhận từ MQTT.
// Nạp NVS lúc khởi động; chỉ báo APPLIED sau khi config hợp lệ đã lưu và áp dụng.
bool loadSavedConfig();
void onConfigMessage(JsonDocument& doc);
const char* currentConfigId();
