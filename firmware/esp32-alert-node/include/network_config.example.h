#pragma once

// Copy file này thành network_config.h (đã được .gitignore bỏ qua) rồi điền thông tin thật.
// W4-TV1-04: Cấu hình IP LAN và cổng 1884, tài khoản riêng được provision.
// KHÔNG dùng "localhost" hoặc "127.0.0.1" trên ESP32 vì ESP32 là thiết bị độc lập trong mạng.

constexpr char WIFI_SSID[] = "TEN_WIFI_HOAC_HOTSPOT";
constexpr char WIFI_PASSWORD[] = "MAT_KHAU_WIFI";

// Thay bằng IP LAN thực tế của máy chủ MQTT Broker (ví dụ: 192.168.2.100 hoặc 192.168.137.1)
constexpr char MQTT_HOST[] = "192.168.2.100"; 
constexpr int MQTT_PORT = 1884; // Cổng 1884 theo yêu cầu W4-TV1-04

// Tài khoản được provision cho alert-01
constexpr char MQTT_USER[] = "alert-01";
constexpr char MQTT_PASSWORD[] = "alert01_secret";
