from sqlmodel import Session, select

from app.core.db import engine

from app.models.device import Device
from app.models.telemetry import Telemetry


def save_telemetry(data: dict):
    with Session(engine) as session:
        device_code = data.get("device_code")
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
            angle_x=data.get("angle_x"),
            angle_y=data.get("angle_y"),
            angle_z=data.get("angle_z"),
            confidence=data.get("confidence"),
        )

        session.add(telemetry)
        session.commit()