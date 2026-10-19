"""Create one MQTT identity and a narrow role for each registered device."""

import re
import secrets

from app.core.config import settings
from app.services.mqtt_security import BrokerSecurity, device_acls


DEVICE_CODE = re.compile(r"[A-Za-z0-9_-]+\Z")


def provision_device(device_code: str) -> dict[str, str]:
    if not DEVICE_CODE.fullmatch(device_code):
        raise ValueError("Invalid device code for MQTT topic")
    if device_code in {settings.MQTT_USERNAME, settings.MQTT_ADMIN_USERNAME}:
        raise ValueError("Reserved MQTT account name")

    if device_code == settings.AI_MQTT_USERNAME:
        with BrokerSecurity() as broker:
            if not broker.has_client(device_code):
                raise RuntimeError("Edge AI MQTT account is not initialized")
        return {"username": device_code, "password": settings.AI_MQTT_PASSWORD}

    password = secrets.token_urlsafe(24)
    role = f"device:{device_code}"
    with BrokerSecurity() as broker:
        # A previous request may have reached the broker but failed before DB commit.
        if broker.has_client(device_code):
            broker.delete_client(device_code)
        if broker.has_role(role):
            broker.delete_role(role)
        broker.create_role(role, device_acls(device_code))
        try:
            broker.create_client(device_code, password, role)
        except Exception:
            broker.delete_role(role)
            raise
    return {"username": device_code, "password": password}
