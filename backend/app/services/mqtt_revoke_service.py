from pathlib import Path
import re
import subprocess


MOSQUITTO_PASSWD = Path(r"D:\Mosquitto\mosquitto_passwd.exe")
PASSWD_FILE = Path(r"D:\Mosquitto\config\passwd")
ACL_FILE = Path(r"D:\Mosquitto\config\acl")


def revoke_device(device_code: str) -> dict:
    """
    Xóa MQTT username/password và ACL của device.
    """

    # 1. Xóa user khỏi passwd
    result = subprocess.run(
        [
            str(MOSQUITTO_PASSWD),
            "-D",
            str(PASSWD_FILE),
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
    if ACL_FILE.exists():
        content = ACL_FILE.read_text(
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

        ACL_FILE.write_text(
            new_content,
            encoding="utf-8",
        )

    return {
        "username": device_code,
        "revoked": True,
    }