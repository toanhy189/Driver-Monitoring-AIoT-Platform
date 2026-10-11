import time
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select

from app.core.db import engine
from app.models.command import Command
from app.models.device import Device

COMMAND_TIMEOUT_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 60

def run_background_tasks():
    while True:
        try:
            with Session(engine) as session:
                now = datetime.now(timezone.utc)
                
                # TV2-13: Handle Command Timeout
                timeout_threshold = now - timedelta(seconds=COMMAND_TIMEOUT_SECONDS)
                
                commands_to_timeout = session.exec(
                    select(Command).where(
                        Command.status.in_(["PENDING", "SENT"]),
                        Command.created_at <= timeout_threshold
                    )
                ).all()
                
                for command in commands_to_timeout:
                    command.status = "TIMEOUT"
                    session.add(command)
                    print(f"Command {command.id} marked as TIMEOUT")
                    
                # TV2-15: Handle Device Offline Status due to missed heartbeat
                heartbeat_threshold = now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
                
                devices_to_offline = session.exec(
                    select(Device).where(
                        Device.status == "ONLINE",
                        Device.last_seen <= heartbeat_threshold
                    )
                ).all()
                
                for device in devices_to_offline:
                    device.status = "OFFLINE"
                    session.add(device)
                    print(f"Device {device.device_code} marked as OFFLINE (missed heartbeat)")
                    
                session.commit()
                
        except Exception as e:
            print(f"Background task error: {e}")
            
        time.sleep(10)
