#pragma once

#include <PubSubClient.h>
#include <Arduino.h>
#include <cstdint>

extern PubSubClient mqtt;

void startWifi();
void printWifiIP();

void initMqtt();
void runMqtt();

void onMessage(char *topic, byte *payload, unsigned int length);

void sendHeartbeat();
bool sendAcks(
    const char *request_id,
    const char *status, const unsigned long elapsed_ms,
    const char *error
);
// [CONFIG - thêm] Gửi kết quả config lên config/applied; error null nếu thành công.
void sendConfigAck(const char* config_id, const char* status, const char* error);