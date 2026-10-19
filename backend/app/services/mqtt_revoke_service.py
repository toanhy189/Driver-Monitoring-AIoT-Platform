"""Immediately disconnect and remove a device's MQTT identity."""

from app.services.mqtt_provision_service import DEVICE_CODE
from app.services.mqtt_security import BrokerSecurity
from app.core.config import settings


def revoke_device(device_code: str) -> dict[str, object]:
    if not DEVICE_CODE.fullmatch(device_code):
        raise ValueError("Invalid device code for MQTT topic")
    if device_code in {settings.MQTT_USERNAME, settings.MQTT_ADMIN_USERNAME}:
        raise ValueError("Reserved MQTT account name")
    with BrokerSecurity() as broker:
        if device_code == settings.AI_MQTT_USERNAME:
            # Keeping the disabled account stops bootstrap from recreating it.
            broker.command("disableClient", username=device_code)
            return {"username": device_code, "revoked": True}
        if broker.has_client(device_code):
            broker.delete_client(device_code)
        role = f"device:{device_code}"
        if broker.has_role(role):
            broker.delete_role(role)
    return {"username": device_code, "revoked": True}
