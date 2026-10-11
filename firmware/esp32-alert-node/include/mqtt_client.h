#pragma once

#include <PubSubClient.h>
#include <Arduino.h>

extern PubSubClient mqtt;

void startWifi();
void printWifiIP();

void initMqtt();
void runMqtt();

void onMessage(char *topic, byte *payload, unsigned int length);

void sendHeartbeat();
void sendAcks(
    const char *request_id,
    const char *status, const unsigned long elapsed_ms,
    const char *error
);