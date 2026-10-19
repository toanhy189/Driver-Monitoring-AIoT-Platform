#!/bin/sh
set -eu

if [ ! -f /mosquitto/data/dynamic-security.json ]; then
    mosquitto_ctrl dynsec init /mosquitto/data/dynamic-security.json "$MQTT_ADMIN_USERNAME" "$MQTT_ADMIN_PASSWORD"
    chown 1883:1883 /mosquitto/data/dynamic-security.json
fi
