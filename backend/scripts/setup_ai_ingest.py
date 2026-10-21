"""Check AI ingest or explicitly apply its additive migrations, broker setup and device registration."""

import argparse
import json
from pathlib import Path
import sys

import psycopg
from sqlalchemy.engine import make_url
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings
from app.core.db import engine
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.services.ai_readiness import broker_readiness, database_readiness
from app.services.device_auth import verify_mqtt_login
from app.services.mqtt_bootstrap import setup
from app.services.mqtt_security import BrokerSecurity


def apply(username: str):
    # Validate the administrator and any existing identity before changing this deployment.
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == username)).first()
        if admin is None or admin.role not in {"Admin", "ADMIN"}:
            raise RuntimeError("--assign-user must identify an existing Admin account")
        device = session.exec(select(Device).where(Device.device_code == settings.AI_DEVICE_CODE)).first()
        if device and (device.device_type != "VISION_NODE" or device.lifecycle_state != "ACTIVE"):
            raise RuntimeError("Existing AI device is not an active Vision Node; resolve its lifecycle through the device API")
        if device and device.mqtt_username not in {None, settings.AI_MQTT_USERNAME}:
            raise RuntimeError("Existing AI device uses another MQTT identity")
    with BrokerSecurity() as broker:
        for name in (settings.MQTT_USERNAME, settings.AI_MQTT_USERNAME):
            if broker.has_client(name):
                client = broker.command("getClient", username=name).get("client", {})
                if client.get("disabled"):
                    raise RuntimeError("A configured broker identity was revoked; setup will not enable it")
    address = make_url(str(settings.DATABASE_URL))
    with psycopg.connect(host=address.host, port=address.port or 5432, dbname=address.database,
                         user=address.username, password=address.password, connect_timeout=5, autocommit=True) as connection:
        for name in ("migration_fe_be_week2.sql", "migration_be_week3.sql", "migration_ai_videos.sql"):
            connection.execute((ROOT / "database" / name).read_text(encoding="utf-8"))
    setup()  # Updates the existing backend/edge-ai roles; does not reset account passwords.
    verify_mqtt_login(settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD)
    verify_mqtt_login(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == username)).one()
        device = session.exec(select(Device).where(Device.device_code == settings.AI_DEVICE_CODE)).first()
        if device is None:
            device = Device(device_code=settings.AI_DEVICE_CODE, model="Edge Vision", name="Edge AI",
                            device_type="VISION_NODE", lifecycle_state="ACTIVE", status="OFFLINE",
                            mqtt_username=settings.AI_MQTT_USERNAME)
            session.add(device)
            session.flush()
        else:
            device.mqtt_username = settings.AI_MQTT_USERNAME
            session.add(device)
        assignment = session.exec(select(UserDevice).where(UserDevice.user_id == admin.id,
                                    UserDevice.device_id == device.id, UserDevice.unassigned_at.is_(None))).first()
        if assignment is None:
            session.add(UserDevice(user_id=admin.id, device_id=device.id))
        session.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply migrations, update broker roles and register the configured Vision Node")
    parser.add_argument("--assign-user", help="Existing Admin username receiving access to this Vision Node")
    args = parser.parse_args()
    if args.apply:
        if not args.assign_user:
            parser.error("--apply requires --assign-user")
        apply(args.assign_user)
    result = {**database_readiness(), **broker_readiness()}
    print(json.dumps(result, indent=2))
    return 0 if result["database_ready"] and result["broker_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
