#pragma once

// Copy thành network_config.h rồi điền thông tin thật.
// network_config.h được Git bỏ qua; file mẫu chỉ chứa giá trị minh họa.
constexpr char WIFI_SSID[] = "TEN_HOTSPOT";
constexpr char WIFI_PASSWORD[] = "MAT_KHAU";
constexpr char MQTT_HOST[] = "192.168.137.1"; // Thay bằng IP laptop TV2.
constexpr int MQTT_PORT = 1883;

// Để trống nếu broker không yêu cầu tài khoản.
constexpr char MQTT_USER[] = "";
constexpr char MQTT_PASSWORD[] = "";
