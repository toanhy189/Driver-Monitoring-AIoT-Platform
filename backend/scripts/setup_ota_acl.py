"""Add exact OTA topics to existing alert-device roles without enabling clients or changing passwords."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session,select
from app.core.db import engine
from app.models.device import Device
from app.services.mqtt_security import BrokerSecurity,device_acls,backend_acls

with Session(engine) as db:
    devices=db.exec(select(Device).where(Device.device_type=="ALERT_NODE",Device.lifecycle_state!="DECOMMISSIONED")).all()
    with BrokerSecurity() as broker:
        if broker.has_role("backend"):broker.command("modifyRole",rolename="backend",acls=backend_acls())
        updated=[]
        for device in devices:
            role="device:"+device.device_code
            if broker.has_role(role):
                broker.command("modifyRole",rolename=role,acls=device_acls(device.device_code));updated.append(device.device_code)
    print("Updated OTA permissions for existing alert roles:",", ".join(updated))
