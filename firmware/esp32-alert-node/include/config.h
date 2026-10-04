#pragma once

// Chọn một bài thử, sau đó Build và Upload lại.
enum class TestMode
{
  Led,    // Mục 4: LED D26 chớp 500 ms.
  Button, // Mục 5: nút D27 điều khiển LED D26.
  Buzzer, // Mục 6.2: buzzer active D25 kêu 300 ms.
  Motor,  // Mục 6.3: motor D33 rung 400 ms.
  Wifi,   // Mục 7: kết nối Wi-Fi, chờ tối đa 20 giây.
  Mqtt    // Mục 8: nhận/in lệnh, gửi ONLINE.
};

constexpr TestMode TEST_MODE = TestMode::Wifi;

constexpr int LED_PIN = 26;
constexpr int BUTTON_PIN = 27;
constexpr int BUZZER_PIN = 25;
constexpr int MOTOR_PIN = 33;
constexpr unsigned long SERIAL_BAUD = 115200;
constexpr unsigned long WIFI_TIMEOUT_MS = 20000;
constexpr unsigned long RETRY_INTERVAL_MS = 5000;

constexpr char DEVICE_ID[] = "alert-01";
constexpr char COMMAND_TOPIC[] = "driver/alert-01/command";
constexpr char STATUS_TOPIC[] = "driver/alert-01/status";
