"""Authenticate an upload with the device's current broker credentials, including revocation."""

from threading import Event

import paho.mqtt.client as mqtt
from fastapi import HTTPException

from app.core.config import settings


def verify_mqtt_login(username: str, password: str) -> None:
    ready = Event()
    accepted = False
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    client.connect_timeout = 3

    def connected(client, userdata, flags, reason_code, properties):
        nonlocal accepted
        accepted = not reason_code.is_failure
        ready.set()

    client.on_connect = connected
    try:
        client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, 10)
        client.loop_start()
        if not ready.wait(5):
            raise HTTPException(status_code=503, detail="MQTT authentication service unavailable")
        if not accepted:
            raise HTTPException(status_code=401, detail="Invalid device credentials",
                                headers={"WWW-Authenticate": "Basic"})
    except OSError:
        raise HTTPException(status_code=503, detail="MQTT authentication service unavailable") from None
    finally:
        client.disconnect()
        client.loop_stop()
