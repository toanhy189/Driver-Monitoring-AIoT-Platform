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
bool wifiWasConnected = false;

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

void testMotor()
{
    digitalWrite(MOTOR_PIN, HIGH);
    Serial.println("MOTOR ON");
    delay(400);
    digitalWrite(MOTOR_PIN, LOW);
    Serial.println("MOTOR OFF");
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

    if (command == "LED_ON")
    {
        digitalWrite(LED_PIN, HIGH);
        Serial.println("[TEST] LED ON");
    }
    else if (command == "LED_OFF")
    {
        digitalWrite(LED_PIN, LOW);
        Serial.println("[TEST] LED OFF");
    }

    // Tuần 1 chỉ in lệnh, kể cả BUZZER_TEST; không bật tải qua MQTT.
}

void runMqtt()
{
    if (WiFi.status() != WL_CONNECTED)
    {
        if (wifiWasConnected)
        {
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
        wifiWasConnected = true;
        printWifiIP();
    }

    if (!mqtt.connected())
    {
        if (millis() - lastMqttAttempt >= RETRY_INTERVAL_MS)
        {
            Serial.print("[MQTT] connecting...");
            // Hỗ trợ broker có hoặc không có tài khoản của TV2.
            bool connected = MQTT_USER[0] != '\0'
                                 ? mqtt.connect(DEVICE_CODE, MQTT_USER, MQTT_PASSWORD)
                                 : mqtt.connect(DEVICE_CODE);
            // connect có thể chờ mạng: tính lần thử sau từ lúc connect kết thúc.
            lastMqttAttempt = millis();
            if (connected)
            {
                Serial.println("connected");
                bool subscribed = mqtt.subscribe(COMMAND_TOPIC);
                bool published = mqtt.publish(STATUS_TOPIC, "ONLINE");
                Serial.printf("[MQTT] subscribe=%s, publish=%s\n",
                              subscribed ? "OK" : "FAIL", published ? "OK" : "FAIL");
            }
            else
            {
                Serial.printf("failed rc=%d\n", mqtt.state());
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
        runMqtt();
        break;
    }
}
