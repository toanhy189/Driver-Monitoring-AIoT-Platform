from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.db import engine

from app.models.device import Device
from app.models.telemetry import Telemetry


def save_telemetry(device_code: str, data: dict):
    with Session(engine) as session:
        device = session.exec(
            select(Device).where(
                Device.device_code == device_code
            )
        ).first()

        if not device:
            print(f"Không tìm thấy device: {device_code}")
            return

        telemetry = Telemetry(
            device_id=device.id,
            ear=data.get("ear"),
            perclos=data.get("perclos"),
            driver_state=data.get("driver_state"),  #trạng thái tài xê
            face_detected=data.get("face_detected"),
            head_pose=data.get("head_pose"),
            model_version=data.get("model_version"),
            received_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        session.add(telemetry)
        session.commit()