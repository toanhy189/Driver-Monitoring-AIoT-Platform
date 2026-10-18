#include <Arduino.h>

#include "config.h"
// [CONFIG - thêm] Nạp timing/ID đã lưu trước khi khởi động MQTT và phát heartbeat.
#include "config_store.h"
#include "device_config.h"
#include "mqtt_client.h"
#include "command_handler.h"
#include "request_log.h"

#include <esp_system.h>

constexpr unsigned long HEARTBEAT_INTERVAL = 5000;
unsigned long lastHeartbeat = 0;

void heartbeat_loop()
{
    unsigned long now = millis();

    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL)
    {
        lastHeartbeat = now;
        sendHeartbeat();
    }
}

// đọc nút và ghi log Serial, không điều khiển LED, buzzer hay motor.
void button_test()
{
    static int lastState = HIGH;
    int currentState = digitalRead(BUTTON_PIN);

    if (currentState != lastState)
    {
        delay(30); // Chống dội nút đơn giản

        currentState = digitalRead(BUTTON_PIN);

        if (currentState != lastState)
        {
            lastState = currentState;

            if (currentState == LOW)
                Serial.println("[BUTTON] PRESSED");
            else
                Serial.println("[BUTTON] RELEASED");
        }
    }
}

void setup()
{
  Serial.begin(SERIAL_BAUD);
  Serial.printf("[BOOT] reset_reason=%d\n", (int)esp_reset_reason()); //log nguyên nhân reset, để phát hiện reset ngầm
  setupPins();
  // [CONFIG - thêm] Khôi phục NVS; nếu chưa có config thì giữ timing mặc định.
  loadSavedConfig();
  // [TV1-13 - thêm] Nạp nhật ký; lệnh còn IN_PROGRESS từ lần chạy trước thành INTERRUPTED.
  reqLogBegin();

  initMqtt();
  
}

void loop()
{
  runMqtt();
  heartbeat_loop();
  deviceLoop();
  button_test();
}
