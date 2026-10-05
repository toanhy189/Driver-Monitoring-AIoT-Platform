#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "pin_config.h"

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

const char* run_command(JsonDocument doc)
{
    const char* command = doc["command"];
    if (doc["duration"].isNull() || doc["intensity"].isNull())
    {
        return "INVALID_PAYLOAD";
    }
    const int duration = doc["duration"];
    const char* intensity = doc["intensity"];

    if (strcmp(command, "LED_ON") == 0)
    {
        switch_Device(ledConfig, duration, intensity);
        return "EXECUTED";
    }
    else if (strcmp(command, "LED_OFF") == 0)
    {
        digitalWrite(LED_PIN, LOW);
        return "EXECUTED";
    }
    else if (strcmp(command, "BUZZER_ON") == 0)
    {
        switch_Device(buzzerConfig, duration, intensity);
        return "EXECUTED";
    }
    else if (strcmp(command, "BUZZER_OFF") == 0)
    {
        digitalWrite(BUZZER_PIN, LOW);
        return "EXECUTED";
    }
    else if (strcmp(command, "MOTOR_ON") == 0)
    {
        switch_Device(motorConfig, duration, intensity);
        return "EXECUTED";
    }
    else if (strcmp(command, "MOTOR_OFF") == 0)
    {
        digitalWrite(MOTOR_PIN, LOW);
        return "EXECUTED";
    }

    return "UNKNOWN_COMMAND";
}

void onMessage(char *topic, byte *payload, unsigned int length)
{
  Serial.print("[MQTT] Topic: ");
  Serial.println(topic);

  // Payload có thể không kết thúc bằng null: đọc đúng length byte.
  String message = "";
  for (unsigned int i = 0; i < length; ++i)
  {
    message += (char)payload[i];
  }
  Serial.print("[MQTT] Received: ");
  Serial.println(message);

  // Tách JSON
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, message);
  if (error)
  {
    Serial.println("[MQTT] Invalid JSON");
    return;
  }

  const char* result = run_command(doc);
  mqtt.publish("driver/alert-01/response", result);

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

void printWifiIP()
{
    Serial.print("[WIFI] Connected; IP = ");
    Serial.println(WiFi.localIP());
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
                          ? mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD)
                          : mqtt.connect(DEVICE_ID);
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

  Serial.println("[BOOT] alert-01 started.");
  startWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  lastMqttAttempt = millis();
  
}

void loop()
{
  runMqtt();
}
