#include <Arduino.h>

#include "config.h"
#include "device_config.h"
#include "mqtt_client.h"
#include "command_handler.h"

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

void setup()
{
  Serial.begin(SERIAL_BAUD);
  setupPins();

  initMqtt();
  
}

void loop()
{
  runMqtt();
  heartbeat_loop();
  deviceLoop();
}
