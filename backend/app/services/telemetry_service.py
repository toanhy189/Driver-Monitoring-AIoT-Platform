from datetime import datetime, timezone
import logging

from sqlmodel import Session, select

from app.core.db import engine

from app.models.device import Device
from app.models.telemetry import Telemetry

logger = logging.getLogger(__name__)


def save_telemetry(device_code: str, data: dict):
    with Session(engine) as session:
        device = session.exec(
            select(Device).where(
                Device.device_code == device_code
            )
        ).first()

        if not device:
            # Print cu khong co schema; thay bang log co event va metadata toi thieu.
            logger.warning(
                "Telemetry source device was not found",
                extra={"event": "telemetry_device_not_found", "device_code": device_code},
            )
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