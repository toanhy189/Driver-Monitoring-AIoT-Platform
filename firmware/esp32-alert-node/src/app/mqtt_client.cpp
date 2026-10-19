#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <cstring>
#include <ctime>

#include "config.h"
// [CONFIG - thêm] Định tuyến config qua kho NVS riêng, tách khỏi luồng lệnh thiết bị.
#include "config_store.h"
#include "mqtt_client.h"
#include "command_handler.h"
#include "request_log.h"

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
bool ntpConfigured = false;
bool timeSyncReported = false;

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

void initMqtt()
{
    Serial.println("[BOOT] alert-01 started.");
    startWifi();
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMessage);
    lastMqttAttempt = millis();

    mqtt.setSocketTimeout(3);   // giây
    mqtt.setKeepAlive(15);
    // [CONFIG - sửa] Payload đủ 3 tải x 3 mức cần buffer 1024 byte, lớn hơn mặc định 256.
    if (!mqtt.setBufferSize(1024))
    {
        Serial.println("[MQTT] Failed to allocate 1024-byte buffer");
    }
}

static void handleConfigUpdate(byte* payload, unsigned int length)
{
    // Parse theo đúng số byte MQTT; JSON hỏng bị từ chối, không làm đổi config đang dùng.
    JsonDocument doc;
    DeserializationError parseError = deserializeJson(doc, payload, length);
    if (parseError)
    {
        Serial.printf("[CONFIG] Invalid JSON: %s\n", parseError.c_str());
        sendConfigAck(nullptr, "REJECTED", "INVALID_JSON");
        return;
    }

    onConfigMessage(doc);
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
        if (!ntpConfigured)
        {
            configTime(0, 0, "pool.ntp.org", "time.nist.gov");
            ntpConfigured = true;
            Serial.println("[TIME] SNTP configured");
        }
    }

    time_t currentTime = time(nullptr);
    if (!timeSyncReported && currentTime > 1700000000)
    {
        timeSyncReported = true;
        Serial.printf("[TIME] SNTP synchronized epoch=%lu\n",
                      static_cast<unsigned long>(currentTime));
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
                char onlineMessage[192];
                // Báo ID đang dùng ngay cả trước heartbeat định kỳ đầu tiên.
                snprintf(
                    onlineMessage,
                    sizeof(onlineMessage),
                    "{\"device_code\":\"%s\",\"status\":\"ALIVE\",\"firmware_version\":\"%s\",\"config_id\":\"%s\"}",
                    DEVICE_CODE,
                    FIRMWARE_VERSION,
                    currentConfigId()
                );

                Serial.println("connected");
                bool commandSubscribed = mqtt.subscribe(COMMAND_TOPIC, 1);
                // [CONFIG - thêm] QoS 1 nhận config retained ngay khi subscribe/reconnect.
                bool configSubscribed = mqtt.subscribe(CONFIG_TOPIC, 1);
                bool published = mqtt.publish(STATUS_TOPIC, onlineMessage, true);//thêm 'true'
                Serial.printf("[MQTT] subscribe command=%s config=%s, publish=%s\n",
                              commandSubscribed ? "OK" : "FAIL",
                              configSubscribed ? "OK" : "FAIL",
                              published ? "OK" : "FAIL");
                // [TV1-13 - thêm] Phát lại ACK INTERRUPTED cho lệnh đang chạy dở trước reboot.
                reqLogPublishPending();
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

    // [CONFIG - thêm] Định tuyến theo topic trước; config không đi vào command ACK/handler.
    if (strcmp(topic, CONFIG_TOPIC) == 0)
    {
        Serial.println("[CONFIG] Received update");
        handleConfigUpdate(payload, length);
        return;
    }
    if (strcmp(topic, COMMAND_TOPIC) != 0)
    {
        Serial.println("[MQTT] Ignoring message on unexpected topic");
        return;
    }

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
    // [CONFIG - thêm] Backend có thể đối chiếu config thiết bị đang thực sự chạy.
    response["config_id"] = currentConfigId();

    serializeJson(response, Serial);
    Serial.println();

    // [CONFIG - sửa] Tăng buffer để chứa thêm config_id trong heartbeat.
    char buffer[192];
    serializeJson(response, buffer);

    mqtt.publish(STATUS_TOPIC, buffer);
}

void sendConfigAck(const char* config_id, const char* status, const char* error)
{
    // [CONFIG - thêm] Phản hồi APPLIED/REJECTED cùng ID và mã lỗi trên config/applied.
    JsonDocument response;
    if (config_id != nullptr)
        response["config_id"] = config_id;
    response["device_code"] = DEVICE_CODE;
    response["status"] = status;
    if (error != nullptr)
        response["error"] = error;

    char buffer[256];
    size_t length = serializeJson(response, buffer, sizeof(buffer));
    if (length == 0)
    {
        Serial.println("[CONFIG] Failed to serialize config response");
        return;
    }

    if (!mqtt.publish(CONFIG_APPLIED_TOPIC, buffer))
    {
        Serial.printf("[CONFIG] Failed to publish %s for config_id=%s\n",
                      status,
                      config_id != nullptr ? config_id : "(missing)");
        return;
    }

    Serial.printf("[CONFIG] %s config_id=%s%s%s\n",
                  status,
                  config_id != nullptr ? config_id : "(missing)",
                  error != nullptr ? " error=" : "",
                  error != nullptr ? error : "");
}

bool sendAcks(
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

    bool published = mqtt.publish(ACK_TOPIC, buffer);
    if (!published)
        Serial.println("[MQTT] Failed to publish command ACK");

    Serial.println("===================");
    Serial.println();
    return published;
}
