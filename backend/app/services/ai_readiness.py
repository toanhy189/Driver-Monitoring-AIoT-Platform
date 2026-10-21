"""Read-only checks for the AI ingest deployment; never expose credentials."""

from sqlalchemy import inspect
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models.device import Device
from app.services.mqtt_security import BrokerSecurity, backend_acls, vision_acls


def database_readiness() -> dict:
    required = {"ai_events", "ai_message_receipts", "rule_bindings", "ai_videos"}
    missing = sorted(required - set(inspect(engine).get_table_names()))
    with Session(engine) as session:
        device = session.exec(select(Device).where(Device.device_code == settings.AI_DEVICE_CODE)).first()
    source_ok = bool(device and device.device_type == "VISION_NODE" and device.lifecycle_state == "ACTIVE")
    return {"missing_tables": missing, "device_code": settings.AI_DEVICE_CODE,
            "device_registered": device is not None, "source_ready": source_ok,
            "database_ready": not missing and source_ok}


def broker_readiness() -> dict:
    missing = []
    disabled = []
    with BrokerSecurity() as broker:
        for role, username, expected in (
            ("backend", settings.MQTT_USERNAME, backend_acls()),
            ("edge-ai", settings.AI_MQTT_USERNAME, vision_acls(settings.AI_DEVICE_CODE, legacy=True)),
        ):
            client = broker.command("getClient", username=username).get("client", {})
            if client.get("disabled"):
                disabled.append(role)
            if role not in {item["rolename"] for item in client.get("roles", [])}:
                missing.append({"role": role, "reason": "ACCOUNT_ROLE_MISMATCH"})
            actual = broker.command("getRole", rolename=role).get("role", {}).get("acls", [])
            allowed = {(item["acltype"], item["topic"]) for item in actual if item.get("allow")}
            for item in expected:
                if (item["acltype"], item["topic"]) not in allowed:
                    missing.append({"role": role, "type": item["acltype"], "topic": item["topic"]})
    return {"missing_permissions": missing, "disabled_accounts": disabled,
            "broker_ready": not missing and not disabled}
