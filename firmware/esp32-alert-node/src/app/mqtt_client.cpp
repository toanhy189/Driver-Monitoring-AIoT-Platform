#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#include "config.h"
#include "mqtt_client.h"
#include "command_handler.h"

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

void initMqtt(){
    Serial.println("[BOOT] alert-01 started.");
    startWifi();
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMessage);
    lastMqttAttempt = millis();
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

            char offlineMessage[128];
            snprintf(
                offlineMessage,
                sizeof(offlineMessage),
                "{\"device_code\":\"%s\",\"status\":\"OFFLINE\",\"firmware_version\":\"%s\"}",
                DEVICE_CODE,
                FIRMWARE_VERSION
            );

            // Hỗ trợ broker có hoặc không có tài khoản của TV2.
            bool connected = MQTT_USER[0] != '\0'
                                ? mqtt.connect(DEVICE_CODE, MQTT_USER, MQTT_PASSWORD,
                                                STATUS_TOPIC, 1, true, offlineMessage)
                                : mqtt.connect(DEVICE_CODE,
                                                STATUS_TOPIC, 1, true, offlineMessage);
            // connect có thể chờ mạng: tính lần thử sau từ lúc connect kết thúc.
            lastMqttAttempt = millis();

            if (connected)
            {
                char onlineMessage[128];
                snprintf(
                    onlineMessage,
                    sizeof(onlineMessage),
                    "{\"device_code\":\"%s\",\"status\":\"ALIVE\",\"firmware_version\":\"%s\"}",
                    DEVICE_CODE,
                    FIRMWARE_VERSION
                );

                Serial.println("connected");
                bool subscribed = mqtt.subscribe(COMMAND_TOPIC);
                bool published = mqtt.publish(STATUS_TOPIC, onlineMessage);
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

    //Thông báo lại đã nhận được CMD
    sendAcks(doc["request_id"], "ACKNOWLEDGED", 0, nullptr);

    runCommand(doc);

}

void sendHeartbeat(){
    JsonDocument response;
    response["device_code"] = DEVICE_CODE;
    response["status"] = "ALIVE";
    response["firmware_version"] = FIRMWARE_VERSION;

    serializeJson(response, Serial);
    Serial.println();

    char buffer[128];
    serializeJson(response, buffer);

    mqtt.publish(STATUS_TOPIC, buffer);
}

void sendAcks(
    const char *request_id,
    const char *status, const unsigned long elapsed_ms,
    const char *error
)
{
    Serial.println("===================");
    Serial.println("[MQTT] Send ACK:");

    JsonDocument response;
    response["request_id"] = request_id;
    response["device_code"] = DEVICE_CODE;
    response["status"] = status;
    response["elapsed_ms"] = elapsed_ms;
    response["error"] = error;
    serializeJsonPretty(response, Serial);

    char buffer[512];
    serializeJson(response, buffer);
    Serial.println();

    mqtt.publish(ACK_TOPIC, buffer);

    Serial.println("===================");
    Serial.println();
}
