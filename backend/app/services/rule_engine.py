from sqlmodel import Session, select
from datetime import datetime, timezone
from app.core.db import engine
from app.models.alert import Alert
from app.models.device import Device

def evaluate_telemetry(device_code: str, payload: dict):
    """
    Skeleton Rule Engine: 
    Evaluate incoming telemetry data and trigger actions if necessary.
    """
    # Example Rule: If driver is sleeping, create an ALERT
    is_sleeping = payload.get("is_sleeping")
    sleep_score = payload.get("sleep_score", 0)
    
    if is_sleeping or sleep_score > 80:
        create_alert(
            device_code=device_code, 
            alert_type="SLEEP_DETECTED",
            description=f"Driver sleep detected. Score: {sleep_score}"
        )

def create_alert(device_code: str, alert_type: str, description: str):
    with Session(engine) as session:
        device = session.exec(select(Device).where(Device.device_code == device_code)).first()
        if not device:
            print(f"RULE ENGINE: Bỏ qua cảnh báo vì thiết bị {device_code} chưa được đăng ký trong Database!", flush=True)
            return
            
        alert = Alert(
            device_id=device.id,
            alert_type=alert_type,
            description=description,
            status="NEW"
        )
        session.add(alert)
        session.commit()
        print(f"RULE ENGINE: Alert generated for {device_code} -> {alert_type}")
