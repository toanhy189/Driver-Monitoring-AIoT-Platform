from pathlib import Path
import secrets
import string
import subprocess

MOSQUITTO_PASSWD = Path(r"D:\Mosquitto\mosquitto_passwd.exe")
PASSWD_FILE = Path(r"D:\Mosquitto\config\passwd")
ACL_FILE = Path(r"D:\Mosquitto\config\acl")


def generate_password(length: int = 16) -> str:
    characters = string.ascii_letters + string.digits
    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


def provision_device(device_code: str) -> dict:
    username = device_code
    password = generate_password()

    # Thêm/cập nhật username vào passwd
    result = subprocess.run(
        [
            str(MOSQUITTO_PASSWD),
            "-b",
            str(PASSWD_FILE),
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

    if ACL_FILE.exists():
        existing_acl = ACL_FILE.read_text(
            encoding="utf-8"
        )

    # Tránh thêm trùng
    if f"user {username}" not in existing_acl:
        acl_block = (
            f"user {username}\n"
            f"\n"
            f"topic write driver/{device_code}/telemetry\n"
            f"topic read driver/{device_code}/command\n"
            f"\n"
        )

        with ACL_FILE.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(acl_block)

    return {
        "username": username,
        "password": password,
    }