import secrets
import string
import subprocess
from pathlib import Path

from app.core.config import settings

def _paths():
    if not all((settings.MOSQUITTO_PASSWD_BIN, settings.MOSQUITTO_PASSWD_FILE,
                settings.MOSQUITTO_ACL_FILE)):
        raise RuntimeError("Broker credential management is not configured")
    return (Path(settings.MOSQUITTO_PASSWD_BIN),
            Path(settings.MOSQUITTO_PASSWD_FILE),
            Path(settings.MOSQUITTO_ACL_FILE))


def generate_password(length: int = 16) -> str:
    characters = string.ascii_letters + string.digits
    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


def provision_device(device_code: str) -> dict:
    mosquitto_passwd, passwd_file, acl_file = _paths()
    username = device_code
    password = generate_password()

    # Thêm/cập nhật username vào passwd
    result = subprocess.run(
        [
            str(mosquitto_passwd),
            "-b",
            str(passwd_file),
            username,
            password,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create MQTT credential: {result.stderr}"
        )

    # Đọc ACL hiện tại
    existing_acl = ""

    if acl_file.exists():
        existing_acl = acl_file.read_text(
            encoding="utf-8"
        )

    # Tránh thêm trùng
    if f"user {username}" not in existing_acl:
        acl_block = (
            f"user {username}\n"
            f"\n"
            f"topic write driver/{device_code}/telemetry\n"
            f"topic write driver/{device_code}/status\n"
            f"topic write driver/{device_code}/ack\n"
            f"topic write driver/{device_code}/heartbeat\n"
            f"topic write driver/{device_code}/config/applied\n"
            f"topic read driver/{device_code}/command\n"
            f"topic read driver/{device_code}/config/update\n"
            f"\n"
        )

        with acl_file.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(acl_block)

    return {
        "username": username,
        "password": password,
    }
