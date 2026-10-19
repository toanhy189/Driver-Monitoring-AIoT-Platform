"""Install the Backend and Edge AI MQTT accounts after the broker starts."""

import time

from app.core.config import settings
from app.services.mqtt_security import BrokerSecurity, backend_acls, vision_acls


def ensure_identity(broker: BrokerSecurity, username: str, password: str,
                    role: str, acls: list[dict]):
    if not broker.has_role(role):
        broker.create_role(role, acls)
    else:
        # Update existing installations without resetting passwords or enabling revoked clients.
        broker.command("modifyRole", rolename=role, acls=acls)
    if not broker.has_client(username):
        broker.create_client(username, password, role)


def setup() -> None:
    if not all((settings.MQTT_USERNAME, settings.MQTT_PASSWORD,
                settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD)):
        raise RuntimeError("Run deployment/mqtt/prepare_env.py to create MQTT credentials")

    for attempt in range(15):
        try:
            with BrokerSecurity() as broker:
                broker.command("setDefaultACLAccess", acls=[
                    {"acltype": "publishClientSend", "allow": False},
                    {"acltype": "publishClientReceive", "allow": False},
                    {"acltype": "subscribe", "allow": False},
                    {"acltype": "unsubscribe", "allow": True},
                ])
                ensure_identity(broker, settings.MQTT_USERNAME, settings.MQTT_PASSWORD,
                                "backend", backend_acls())
                ensure_identity(broker, settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD,
                                "edge-ai", vision_acls(settings.AI_DEVICE_CODE, legacy=True))
                return
        except (ConnectionError, OSError):
            if attempt == 14:
                raise
            time.sleep(1)


if __name__ == "__main__":
    setup()
    print("MQTT broker accounts and ACL are ready")
