import json
import time
import paho.mqtt.client as mqtt

from backend.app.core.config import settings


MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT

DEVICE_CODE = "alert-01"
COMMAND_TOPIC = f"driver/{DEVICE_CODE}/command"


def publish_command(request_id, command, duration=None, intensity=None):
    payload = {
        "request_id": request_id,
        "device_code": DEVICE_CODE,
        "command": command
    }

    if duration is not None:
        payload["duration"] = duration

    if intensity is not None:
        payload["intensity"] = intensity

    device.publish(
        topic=COMMAND_TOPIC,
        payload=json.dumps(payload)
    )

    print(f"→ {request_id}: {payload}")


# =========================
# COMPLETED
# =========================

def test_completed():
    print("\n===== TEST COMPLETED =====")

    publish_command("cmd-001", "LED_ON", 5000, "STRONG")
    time.sleep(6)


# =========================
# INTERRUPTED
# =========================

def test_interrupted():
    print("\n===== TEST INTERRUPTED =====")

    publish_command("cmd-002", "LED_ON", 5000, "STRONG")
    time.sleep(2)

    publish_command("cmd-003", "LED_OFF")
    time.sleep(1)


# =========================
# INVALID COMMAND
# =========================

def test_missing_command():
    print("\n===== TEST MISSING COMMAND =====")

    device.publish(
        topic=COMMAND_TOPIC,
        payload=json.dumps({
            "request_id": "cmd-004",
            "device_code": DEVICE_CODE
        })
    )

    time.sleep(1)


# =========================
# INVALID PAYLOAD - thiếu duration, intensity
def test_missing_duration():
    print("\n===== TEST MISSING DURATION =====")

    publish_command("cmd-005", "LED_ON", intensity="STRONG")
    time.sleep(1)

def test_missing_intensity():
    print("\n===== TEST MISSING INTENSITY =====")

    publish_command("cmd-006", "LED_ON", duration=5000)
    time.sleep(1)
# =========================


# =========================
# INTENSITY TOO LOW
# =========================

def test_intensity_too_low():
    print("\n===== TEST INTENSITY TOO LOW =====")

    # Command hiện tại: STRONG
    publish_command("cmd-007", "LED_ON", 10000, "STRONG")
    time.sleep(2)

    # Command mới: WEAK -> phải FAILED
    publish_command("cmd-008", "LED_ON", 5000, "WEAK")
    time.sleep(1)

    # Dọn command cũ
    publish_command("cmd-009", "LED_OFF")
    time.sleep(1)


# =========================
# CÙNG INTENSITY
# =========================

def test_same_intensity():
    print("\n===== TEST SAME INTENSITY =====")

    publish_command("cmd-010", "LED_ON", 10000, "MEDIUM")
    time.sleep(2)

    # MEDIUM >= MEDIUM
    # => INTERRUPTED cmd-010
    # => STARTED cmd-011
    publish_command("cmd-011", "LED_ON", 5000, "MEDIUM")
    time.sleep(6)


# =========================
# INTENSITY CAO HƠN
# =========================

def test_higher_intensity():
    print("\n===== TEST HIGHER INTENSITY =====")

    publish_command("cmd-012", "LED_ON", 10000, "WEAK")
    time.sleep(2)

    # STRONG > WEAK
    # => INTERRUPTED cmd-012
    # => STARTED cmd-013
    publish_command("cmd-013", "LED_ON", 5000, "STRONG")
    time.sleep(6)


# =========================
# UNKNOWN COMMAND
# =========================

def test_unknown_command():
    print("\n===== TEST UNKNOWN COMMAND =====")

    publish_command("cmd-014", "LED_BLINK")
    time.sleep(1)


# =========================
# BUZZER
# =========================

def test_buzzer():
    print("\n===== TEST BUZZER =====")

    publish_command("cmd-015", "BUZZER_ON", 3000, "MEDIUM")
    time.sleep(4)


# =========================
# MOTOR
# =========================

def test_motor():
    print("\n===== TEST MOTOR =====")

    publish_command("cmd-016", "MOTOR_ON", 3000, "WEAK")
    time.sleep(4)


# =========================
# OFF KHI KHÔNG ACTIVE
# =========================

def test_off_when_inactive():
    print("\n===== TEST OFF INACTIVE =====")

    publish_command("cmd-017", "LED_OFF")
    time.sleep(1)


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    print(f"Publishing topic: '{COMMAND_TOPIC}'")

    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    device.connect(MQTT_HOST, MQTT_PORT, 60)
    device.loop_start()

    test_completed()
    test_interrupted()

    test_missing_command()
    test_missing_duration()
    test_missing_intensity()

    test_intensity_too_low()
    test_same_intensity()
    test_higher_intensity()

    test_unknown_command()

    test_buzzer()
    test_motor()

    test_off_when_inactive()

    device.loop_stop()
    device.disconnect()