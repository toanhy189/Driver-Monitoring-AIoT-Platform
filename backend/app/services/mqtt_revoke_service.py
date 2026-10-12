from pathlib import Path
import re
import subprocess

from app.core.config import settings


def _paths():
    if not all((settings.MOSQUITTO_PASSWD_BIN, settings.MOSQUITTO_PASSWD_FILE,
                settings.MOSQUITTO_ACL_FILE)):
        raise RuntimeError("Broker credential management is not configured")
    return (Path(settings.MOSQUITTO_PASSWD_BIN),
            Path(settings.MOSQUITTO_PASSWD_FILE),
            Path(settings.MOSQUITTO_ACL_FILE))


def revoke_device(device_code: str) -> dict:
    """
    Xóa MQTT username/password và ACL của device.
    """

    mosquitto_passwd, passwd_file, acl_file = _paths()
    # 1. Xóa user khỏi passwd
    result = subprocess.run(
        [
            str(mosquitto_passwd),
            "-D",
            str(passwd_file),
            device_code,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to revoke MQTT credential: {result.stderr}"
        )

    # 2. Xóa ACL của device
    if acl_file.exists():
        content = acl_file.read_text(
            encoding="utf-8"
        )

        pattern = (
            rf"(?ms)^user {re.escape(device_code)}\r?\n"
            rf"(?:\r?\n)?"
            rf"(?:topic[^\r\n]*\r?\n)+"
            rf"(?:\r?\n)?"
        )

        new_content = re.sub(
            pattern,
            "",
            content,
        )

        acl_file.write_text(
            new_content,
            encoding="utf-8",
        )

    return {
        "username": device_code,
        "revoked": True,
    }
