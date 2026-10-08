import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
import paho.mqtt.publish as mqtt_publish

from app.api.deps import require_operator
from app.core.config import settings
from app.core.db import get_session
from app.models.config import Config
from app.models.device import Device
from app.models.user import User
from app.services.audit_service import log_action

router = APIRouter(
    prefix="/configs",
    tags=["configs"],
)

class ConfigUpdateRequest(BaseModel):
    desired_config: dict

@router.get("/{device_code}")
def get_config(
    device_code: str,
    current_user: Annotated[User, Depends(require_operator)],
    session: Session = Depends(get_session),
):
    device = session.exec(select(Device).where(Device.device_code == device_code)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    config = session.exec(select(Config).where(Config.device_id == device.id)).first()
    if not config:
        return {"device_code": device_code, "desired_config": None, "applied_config": None}
        
    return {
        "device_code": device_code,
        "desired_config": config.desired_config,
        "applied_config": config.applied_config,
        "updated_at": config.updated_at
    }

@router.post("/{device_code}")
def update_config(
    device_code: str,
    data: ConfigUpdateRequest,
    current_user: Annotated[User, Depends(require_operator)],
    session: Session = Depends(get_session),
):
    device = session.exec(select(Device).where(Device.device_code == device_code)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    if not device.mqtt_username or not device.mqtt_password:
        raise HTTPException(status_code=400, detail="Device MQTT credentials not provisioned")

    config = session.exec(select(Config).where(Config.device_id == device.id)).first()
    if not config:
        config = Config(device_id=device.id, desired_config=data.desired_config)
        session.add(config)
    else:
        config.desired_config = data.desired_config
        session.add(config)
        
    log_action(
        session=session,
        user_id=current_user.id,
        action="UPDATE_CONFIG",
        entity_type="Config",
        entity_id=str(config.id) if config.id else None,
        details={"device_code": device_code, "desired_config": data.desired_config}
    )
        
    session.commit()
    session.refresh(config)
    
    # Publish to MQTT
    topic = f"driver/{device_code}/config/update"
    payload = json.dumps(data.desired_config)
    
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 5)
        client.publish(topic, payload)
        client.disconnect()
    except Exception as e:
        return {
            "message": "Config saved but MQTT publish failed",
            "error": str(e)
        }

    return {
        "message": "Config updated and published successfully",
        "desired_config": config.desired_config
    }
