#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"

#if __has_include("network_config.h")
#include "network_config.h"
#else
#include "network_config.example.h"
#endif

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
// [BACKOFF - thêm] 3,5 giây, nhỉnh hơn thời gian connect thất bại đo được (~3 giây).
constexpr uint32_t MQTT_BACKOFF_INITIAL_MS = 3500;
// [BACKOFF - cần xác nhận] Trần 30 giây cần được đối chiếu với SLA phục hồi của backend.
constexpr uint32_t MQTT_BACKOFF_MAX_MS = 30000;
uint32_t mqttBackoffMs = MQTT_BACKOFF_INITIAL_MS;
bool wifiWasConnected = false;
bool mqttTestLedTimed = false;
unsigned long mqttTestLedStartedAt = 0;
unsigned long mqttTestLedDuration = 0;

// Khởi động với tất cả đầu ra tắt. Chỉ bài thử được chọn mới bật tải.
void setupPins()
{
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(MOTOR_PIN, LOW);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(MOTOR_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
}

void testLed()
{
    digitalWrite(LED_PIN, HIGH);
    Serial.println("LED ON");
    delay(500);
    digitalWrite(LED_PIN, LOW);
    Serial.println("LED OFF");
    delay(500);
}

void testButton()
{
    bool pressed = digitalRead(BUTTON_PIN) == LOW;
    digitalWrite(LED_PIN, pressed ? HIGH : LOW);
    Serial.println(pressed ? "PRESSED" : "RELEASED");
    delay(150);
}

void testBuzzer()
{
    digitalWrite(BUZZER_PIN, HIGH);
    Serial.println("BUZZER ON");
    delay(300);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("BUZZER OFF");
    delay(2000);
}
/*
void testMotor()
{
    digitalWrite(MOTOR_PIN, HIGH);
    Serial.println("MOTOR ON");
    delay(400);
    digitalWrite(MOTOR_PIN, LOW);
    Serial.println("MOTOR OFF");
    delay(2500);
}
*/

void testMotor()
{
    digitalWrite(MOTOR_PIN, LOW);
    Serial.printf("[MOTOR] Before ON: GPIO%d=%d\n",
                  MOTOR_PIN, digitalRead(MOTOR_PIN));
    delay(500);

    digitalWrite(MOTOR_PIN, HIGH);
    Serial.printf("[MOTOR] ON: GPIO%d=%d, t=%lu ms\n",
                  MOTOR_PIN, digitalRead(MOTOR_PIN), millis());

    delay(400);

    digitalWrite(MOTOR_PIN, LOW);
    Serial.printf("[MOTOR] OFF: GPIO%d=%d, t=%lu ms\n",
                  MOTOR_PIN, digitalRead(MOTOR_PIN), millis());

    delay(2500);
}


void printWifiIP()
{
    Serial.print("[WIFI] Connected; IP = ");
    Serial.println(WiFi.localIP());
}

void startWifi()
{
#if !__has_include("network_config.h")
    Serial.println("[CONFIG] Copy include/network_config.example.h to network_config.h and fill in your network settings");
#endif
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiAttempt = millis();
    Serial.println("[WIFI] Connecting");
}

// Bài Wi-Fi riêng: hết 20 giây thì báo lỗi, không chờ vô hạn.
void testWifi()
{
    startWifi();
    unsigned long started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT_MS)
    {
        Serial.print(".");
        delay(500);
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED)
    {
        printWifiIP();
    }
    else
    {
        Serial.println("[WIFI] Timeout; check SSID/password/hotspot");
    }
}

void onMessage(char *topic, byte *payload, unsigned int length)
{
    Serial.print("[MQTT] Topic: ");
    Serial.println(topic);
    Serial.print("[MQTT] Received: ");
    // Payload có thể không kết thúc bằng null: đọc đúng length byte.
    String command = "";
    for (unsigned int i = 0; i < length; ++i)
    {
        command += (char)payload[i];
    }
    Serial.println(command);

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload, length);
    bool isJson = !error;
    if (isJson)
    {
        const char *jsonCommand = doc["command"];
        command = jsonCommand ? jsonCommand : "";
    }

    if (command == "LED_ON")
    {
        if (isJson && !doc["duration"].isNull())
        {
            if (!doc["duration"].is<unsigned long>() ||
                doc["duration"].as<unsigned long>() == 0 ||
                doc["duration"].as<unsigned long>() > 60000)
            {
                Serial.println("[TEST] Invalid LED duration (expected 1-60000 ms)");
                return;
            }
            mqttTestLedTimed = true;
            mqttTestLedStartedAt = millis();
            mqttTestLedDuration = doc["duration"].as<unsigned long>();
        }
        else
        {
            mqttTestLedTimed = false;
        }
        digitalWrite(LED_PIN, HIGH);
        Serial.println("[TEST] LED ON");
    }
    else if (command == "LED_OFF")
    {
        mqttTestLedTimed = false;
        digitalWrite(LED_PIN, LOW);
        Serial.println("[TEST] LED OFF");
    }
    else if (isJson)
    {
        Serial.println("[TEST] Unsupported or missing command");
    }
    else
    {
        Serial.println("[TEST] Unsupported command or invalid JSON");
    }
}

void updateMqttTestLed()
{
    if (mqttTestLedTimed && millis() - mqttTestLedStartedAt >= mqttTestLedDuration)
    {
        mqttTestLedTimed = false;
        digitalWrite(LED_PIN, LOW);
        Serial.println("[TEST] LED OFF (duration elapsed)");
    }
}

// [KIEM THU WIFI - them]
// Gửi ký tự 'd' trong Serial Monitor để ngắt Wi-Fi riêng của ESP32.
// AP vẫn hoạt động; runMqtt() sẽ ghi wifi_lost và tự thử kết nối lại.
void handleSerialWifiTest()
{
    if (!Serial.available())
        return;

    char command = Serial.read();
    if (command != 'd' && command != 'D')
        return;

    if (WiFi.status() == WL_CONNECTED)
    {
        Serial.printf("[TEST] Ngắt Wi-Fi riêng ESP32, t=%lu\n", millis());
        WiFi.disconnect(false, false);
    }
    else
    {
        Serial.println("[TEST] Wi-Fi chưa kết nối; bỏ qua lệnh.");
    }
}

void runMqtt()
{
    if (WiFi.status() != WL_CONNECTED)
    {
        if (wifiWasConnected)
        {
            Serial.printf("[T] wifi_lost   t=%lu\n", millis());
            wifiWasConnected = false;
            wifiClient.stop();
            Serial.println("[WIFI] Disconnected");
        }
        if (millis() - lastWifiAttempt >= RETRY_INTERVAL_MS)
        {
            lastWifiAttempt = millis();
            Serial.println("[WIFI] retry");
            WiFi.reconnect();
        }
        delay(10);
        return;
    }

    if (!wifiWasConnected)
    {
        Serial.printf("[T] wifi_up     t=%lu\n", millis());
        wifiWasConnected = true;
        printWifiIP();
    }

    if (!mqtt.connected())
    {
        // [BACKOFF - sửa] Wi-Fi vẫn thử lại theo chu kỳ cố định; MQTT dùng thời gian chờ tăng dần.
        if (millis() - lastMqttAttempt >= mqttBackoffMs)
        {
            Serial.print("[MQTT] connecting...");
            unsigned long t0 = millis();
            // Hỗ trợ broker có hoặc không có tài khoản của TV2.
            bool connected = MQTT_USER[0] != '\0'
                                 ? mqtt.connect(DEVICE_CODE, MQTT_USER, MQTT_PASSWORD)
                                 : mqtt.connect(DEVICE_CODE);
            Serial.printf("[T] mqtt_connect %s took=%lu ms\n",
                          connected ? "OK" : "FAIL", millis() - t0);
            // connect có thể chờ mạng: tính lần thử sau từ lúc connect kết thúc.
            lastMqttAttempt = millis();
            if (connected)
            {
                // [BACKOFF - thêm] Đặt lại thời gian chờ ban đầu sau khi kết nối thành công.
                mqttBackoffMs = MQTT_BACKOFF_INITIAL_MS;
                Serial.println("connected");
                Serial.printf("[MQTT] backoff reset=%lu ms\n",
                              static_cast<unsigned long>(mqttBackoffMs));
                bool s1 = mqtt.subscribe(COMMAND_TOPIC, 1);
                bool s2 = mqtt.subscribe(CONFIG_TOPIC, 1);
                bool published = mqtt.publish(STATUS_TOPIC, "ONLINE");
                Serial.printf("[MQTT] subscribe cmd=%s cfg=%s\n",
                              s1 ? "OK" : "FAIL", s2 ? "OK" : "FAIL");
                Serial.printf("[MQTT] publish=%s\n", published ? "OK" : "FAIL");
            }
            else
            {
                Serial.printf("failed rc=%d\n", mqtt.state());
                // [BACKOFF - thêm] Chờ sau khi connect kết thúc; tăng gấp đôi, thêm jitter, chặn ở trần.
                uint32_t nextBackoffMs = mqttBackoffMs * 2UL + random(0, 500);
                mqttBackoffMs = nextBackoffMs < MQTT_BACKOFF_MAX_MS
                                    ? nextBackoffMs
                                    : MQTT_BACKOFF_MAX_MS;
                Serial.printf("[MQTT] retry in=%lu ms\n",
                              static_cast<unsigned long>(mqttBackoffMs));
            }
        }
        delay(10);
        return;
    }

    mqtt.loop();
}

void setup()
{
    Serial.begin(SERIAL_BAUD);
    setupPins();

    switch (TEST_MODE)
    {
    case TestMode::Led:
        Serial.println("[BOOT] LED test (D26)");
        break;
    case TestMode::Button:
        Serial.println("[BOOT] Button test (D27 -> LED D26)");
        break;
    case TestMode::Buzzer:
        Serial.println("[BOOT] Active buzzer test (D25)");
        break;
    case TestMode::Motor:
        Serial.println("[BOOT] Motor test (D33)");
        break;
    case TestMode::Wifi:
        Serial.println("[BOOT] Wi-Fi test");
        testWifi();
        break;
    case TestMode::Mqtt:
        Serial.println("[BOOT] alert-01 started (MQTT test)");
        startWifi();
        mqtt.setServer(MQTT_HOST, MQTT_PORT);
        mqtt.setCallback(onMessage);
        lastMqttAttempt = millis();
        break;
    }
}

void loop()
{
    switch (TEST_MODE)
    {
    case TestMode::Led:
        testLed();
        break;
    case TestMode::Button:
        testButton();
        break;
    case TestMode::Buzzer:
        testBuzzer();
        break;
    case TestMode::Motor:
        testMotor();
        break;
    case TestMode::Wifi:
        delay(10); // Bài Wi-Fi chạy một lần trong setup; nhấn EN để thử lại.
        break;
    case TestMode::Mqtt:
        // [KIỂM THỬ WI-FI - thêm] Xử lý lệnh 'd' trước khi kiểm tra trạng thái Wi-Fi.
        handleSerialWifiTest();
        runMqtt();
        updateMqttTestLed();
        break;
    }
}
