"""
Chức năng chính:
- Phát hiện khuôn mặt và tính EAR.
- Tính PERCLOS và theo dõi thời gian mắt nhắm.
- Ước lượng hướng đầu và xác định DISTRACTED.
- Xác định driver_state: ATTENTIVE / DISTRACTED / DROWSY / UNKNOWN.
- Gửi telemetry định kỳ qua MQTT.
- Gửi event khi trạng thái thay đổi.
- Gửi THRESHOLD_REACHED khi liên tục state trên x giây.
"""

import json

import cv2
import time
import uuid

from datetime import datetime, timezone

import logging

from face_detection import FaceLandmarkDetector
from eye import (
    calculate_average_ear,
    PerclosCalculator,
    EyeClosureTracker,
)

from mqtt_client import MQTTClient
from config import DEVICE_CODE, EAR_THRESHOLD, EVENT_TOPIC, MODEL_VERSION, PERCLOS_THRESHOLD, TELEMETRY_TOPIC
from head_pose import HeadPoseEstimator, HeadPoseTracker

from edge_queue import init_db, add_to_queue


# =========================
# CONFIGURATION
# =========================

CAMERA_INDEX = 0
MAX_CAMERA_FAILURES = 5

MQTT_INTERVAL = 1.0

EYES_OPEN_RECOVERY_SECONDS = 1.0

YAW_THRESHOLD = 0.20
PITCH_THRESHOLD = 0.05
CALIBRATION_SECONDS = 5.0
DISTRACTED_DURATION_SECONDS = 2.0

CONFIRM_SECONDS = {
    "ATTENTIVE": 1.0,
    "DISTRACTED": 0.3,
    "DROWSY": 0.5,
    "UNKNOWN": 0.5,
}

THRESHOLD_SECONDS = {
    "DROWSY": 3.0,
    "DISTRACTED": 3.0,
}

# DEBUG OVERLAY
font = cv2.FONT_HERSHEY_SIMPLEX
x = 15
y = 25
line_height = 25
font_scale = 0.55
thickness = 1

# =========================
# OFFLINE QUEUE
# =========================
if not init_db():
    raise RuntimeError("Cannot initialize SQLite offline queue")

logger = logging.getLogger(__name__)

def send_message(mqtt_client, topic, data):
    """Lưu message trước, sau đó thử gửi qua MQTT."""
    message_id = data.get("message_id") or str(uuid.uuid4())
    data["message_id"] = message_id

    payload = json.dumps(data)

    # Lưu vào SQLite trước khi gửi
    if not add_to_queue(message_id, topic, payload):
        logger.error("Message was not saved; skipping publish")
        return False

    # Một worker gửi từ SQLite; kết nối lại vẫn dùng nguyên message_id.
    # True chỉ xác nhận đã xếp hàng, không có nghĩa BE đã lưu.
    mqtt_client.notify_queue()
    return True


# =========================
# UTILITY FUNCTIONS
# =========================

def current_timestamp():
    """Lấy thời gian UTC theo định dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def update_confirmed_state(driver_state, state_data, device_code):
    """
    Xác nhận trạng thái sau một khoảng thời gian ổn định.
    Tạo STATE_CHANGED event khi trạng thái xác nhận thay đổi.
    """
    now = time.monotonic()

    if driver_state != state_data["candidate_state"]:
        state_data["candidate_state"] = driver_state
        state_data["candidate_since"] = now

    candidate = state_data["candidate_state"]
    candidate_since = state_data["candidate_since"]

    if candidate_since is None:
        return None

    confirm_seconds = state_data["confirm_seconds"][candidate]

    if now - candidate_since < confirm_seconds:
        return None

    # Khởi tạo trạng thái xác nhận lần đầu.
    if state_data["confirmed_state"] is None:
        state_data["confirmed_state"] = candidate
        state_data["state_since"] = now
        return None

    # Trạng thái không thay đổi.
    if candidate == state_data["confirmed_state"]:
        return None

    previous_state = state_data["confirmed_state"]
    previous_duration = now - state_data["state_since"]

    event = {
        "message_id": str(uuid.uuid4()),
        "sequence_number": state_data["event_sequence"],
        "device_code": device_code,
        "timestamp": current_timestamp(),
        "event_type": "STATE_CHANGED",
        "model_version": MODEL_VERSION,
        "previous_state": previous_state,
        "state": candidate,
        "previous_state_duration_ms": round(
            previous_duration * 1000
        ),
    }

    state_data["event_sequence"] += 1
    state_data["confirmed_state"] = candidate
    state_data["state_since"] = now

    return event


def check_threshold_events(state_data, device_code):
    """
    Phát một threshold event khi trạng thái DROWSY hoặc DISTRACTED
    được duy trì đủ lâu.

    Thời gian chỉ được tính khi candidate_state và confirmed_state
    cùng là trạng thái đang xét.
    """
    now = time.monotonic()
    confirmed_state = state_data["confirmed_state"]
    candidate_state = state_data["candidate_state"]

    events = []

    for state, threshold_seconds in state_data[
        "threshold_seconds"
    ].items():

        # Không tiếp tục tính nếu trạng thái hiện tại đang chuyển đổi.
        if (
            confirmed_state != state
            or candidate_state != state
        ):
            state_data["threshold_since"][state] = None
            state_data["threshold_event_sent"][state] = False
            continue

        if state_data["threshold_since"][state] is None:
            state_data["threshold_since"][state] = now

        duration = now - state_data["threshold_since"][state]

        if (
            duration >= threshold_seconds
            and not state_data["threshold_event_sent"][state]
        ):
            event = {
                "message_id": str(uuid.uuid4()),
                "sequence_number": state_data["event_sequence"],
                "device_code": device_code,
                "timestamp": current_timestamp(),
                "event_type": f"{state}_THRESHOLD_REACHED",
                "model_version": MODEL_VERSION,
                "state": state,
                "state_duration_ms": round(duration * 1000),
            }

            events.append(event)
            state_data["event_sequence"] += 1
            state_data["threshold_event_sent"][state] = True

    return events


def determine_driver_state(
    perclos,
    pose_status,
    eyes_recovered,
):
    """Xác định trạng thái ứng viên của người lái."""

    # Ưu tiên phát hiện buồn ngủ.
    if (
        perclos is not None
        and perclos > PERCLOS_THRESHOLD
        and not eyes_recovered
    ):
        return "DROWSY"

    # Phát hiện quay đầu hoặc nhìn lệch kéo dài.
    if pose_status and pose_status.get("is_distracted", False):
        return "DISTRACTED"

    # Chỉ coi là tỉnh táo khi head pose hợp lệ và đã hiệu chuẩn.
    if (
        pose_status
        and pose_status.get("valid", False)
        and not pose_status.get("calibrating", True)
    ):
        return "ATTENTIVE"

    return "UNKNOWN"


def publish_event(mqtt_client, event):
    """Gửi event lên MQTT."""
    if event is None:
        return

    try:
        send_message(mqtt_client, EVENT_TOPIC, event)

    except Exception as exc:
        print(f"[MQTT] Không gửi được event: {exc}")


def publish_telemetry(
    mqtt_client, state_data, face_detected,
    ear, perclos, eye_closed, pose,
):
    """Gửi telemetry định kỳ, kể cả khi không phát hiện khuôn mặt."""

    confirmed_state = state_data["confirmed_state"] or "UNKNOWN"

    head_pose_data = {
        "yaw": None,
        "pitch": None,
        "roll": None,
    }

    if pose is not None:
        head_pose_data = {
            "yaw": pose.get("yaw"),
            "pitch": pose.get("pitch"),
            "roll": pose.get("roll"),
        }

    payload = {
        "message_id": str(uuid.uuid4()),
        "device_code": DEVICE_CODE,
        "model_version": MODEL_VERSION,
        "timestamp": current_timestamp(),
        "driver_state": confirmed_state,
        "candidate_state": state_data["candidate_state"],
        "face_detected": face_detected,
        "ear": ear,
        "perclos": perclos,
        "eyes_closed": eye_closed,
        "head_pose": head_pose_data,
    }

    try:
        send_message(mqtt_client, TELEMETRY_TOPIC, payload)

    except Exception as exc:
        print(f"[MQTT] Không gửi được telemetry: {exc}")


def draw_text(frame, text, y, color=(0, 255, 0)):
    cv2.putText(
        frame,
        str(text),
        (15, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        1,
        cv2.LINE_AA
    )
    return y + 25

# =========================
# MAIN
# =========================

def main():
    global y  # Dùng biến toàn cục để vẽ overlay

    # Trạng thái dùng cho debounce và event.
    state_data = {
        "candidate_state": None,
        "candidate_since": None,
        "confirmed_state": None,
        "state_since": None,

        "confirm_seconds": CONFIRM_SECONDS,

        "threshold_seconds": THRESHOLD_SECONDS,
        "threshold_since": {
            "DROWSY": None,
            "DISTRACTED": None,
        },
        "threshold_event_sent": {
            "DROWSY": False,
            "DISTRACTED": False,
        },

        "event_sequence": 0,
    }

    camera = None
    mqtt_client = None
    detector = None

    try:
        # Khởi tạo camera.
        camera = cv2.VideoCapture(CAMERA_INDEX)

        if not camera.isOpened():
            raise RuntimeError("Không thể mở camera.")

        # Khởi tạo các thành phần xử lý hình ảnh.
        detector = FaceLandmarkDetector()

        perclos_calculator = PerclosCalculator(
            window_seconds=10.0,
            warmup_seconds=10.0,
        )

        eye_tracker = EyeClosureTracker()

        head_pose = HeadPoseEstimator()

        head_pose_tracker = HeadPoseTracker(
            yaw_threshold=YAW_THRESHOLD,
            pitch_threshold=PITCH_THRESHOLD,
            calibration_seconds=CALIBRATION_SECONDS,
            distracted_duration=DISTRACTED_DURATION_SECONDS,
        )

        # Khởi tạo MQTT.
        mqtt_client = MQTTClient()

        print("[INFO] Hệ thống phát hiện buồn ngủ đã khởi động.")
        print("[INFO] Nhấn Q để thoát.")

        camera_failures = 0
        last_mqtt_time = 0.0

        eyes_open_since = None

        while True:
            success, frame = camera.read()

            if not success:
                camera_failures += 1
                print(
                    f"[CAMERA] Không đọc được frame "
                    f"({camera_failures}/{MAX_CAMERA_FAILURES})."
                )

                if camera_failures >= MAX_CAMERA_FAILURES:
                    print("[CAMERA] Dừng do camera liên tục gặp lỗi.")
                    mqtt_client.publish_status("CAMERA_ERROR")
                    break

                time.sleep(0.1)
                continue

            camera_failures = 0
            frame_time = time.monotonic()

            # Giá trị mặc định cho frame không có khuôn mặt.
            face_detected = False
            face = None
            ear = None
            perclos = None
            perclos_text = "PERCLOS: WARMING UP"
            eye_closed = None
            eye_status = None
            pose = None
            pose_status = None
            yaw = None
            pitch = None
            roll = None
            eyes_recovered = False

            # ---------------------------------
            # 1. FACE DETECTION
            # ---------------------------------

            faces = detector.process(frame)

            if faces:
                face_detected = True
                face = faces[0]

                # ---------------------------------
                # 2. EYE / EAR / PERCLOS
                # ---------------------------------

                ear = calculate_average_ear(face)

                eye_status = eye_tracker.update(ear)
                eye_closed = eye_status["is_closed"]

                perclos = perclos_calculator.update(ear)

                if eye_closed:
                    eyes_open_since = None
                elif eyes_open_since is None:
                    eyes_open_since = frame_time

                eyes_open_duration = (
                    frame_time - eyes_open_since
                    if eyes_open_since is not None
                    else 0.0
                )

                eyes_recovered = (
                    eyes_open_duration >= EYES_OPEN_RECOVERY_SECONDS
                )

                # ---------------------------------
                # 3. HEAD POSE
                # ---------------------------------

                pose = head_pose.estimate(face)
                pose_status = head_pose_tracker.update(pose)
                if pose is not None:
                    yaw = pose.get("yaw")
                    pitch = pose.get("pitch")
                    roll = pose.get("roll")

                # ---------------------------------
                # 4. RAW DRIVER STATE
                # ---------------------------------

                driver_state = determine_driver_state(
                    perclos=perclos,
                    pose_status=pose_status,
                    eyes_recovered=eyes_recovered,
                )

                # Debug thông tin head pose.
                # print(
                #     "calibrating=", pose_status.get("calibrating"),
                #     "valid=", pose_status.get("valid"),
                #     "deviated=", pose_status.get("is_deviated"),
                #     "distracted=", pose_status.get("is_distracted"),
                # )

                perclos_text = (
                    f"PERCLOS: {perclos:.3f}"
                    if perclos is not None
                    else "PERCLOS: WARMING UP"
                )

            else:
                # Không có khuôn mặt
                driver_state = "UNKNOWN"
                eyes_open_since = None

            # ---------------------------------
            # 5. CONFIRM STATE
            # ---------------------------------

            state_event = update_confirmed_state(
                driver_state,
                state_data,
                DEVICE_CODE,
            )

            publish_event(mqtt_client, state_event)

            # ---------------------------------
            # 6. THRESHOLD EVENTS
            # ---------------------------------

            threshold_events = check_threshold_events(
                state_data,
                DEVICE_CODE,
            )

            for event in threshold_events:
                publish_event(mqtt_client, event)

            # ---------------------------------
            # 7. MQTT TELEMETRY
            # ---------------------------------

            if frame_time - last_mqtt_time >= MQTT_INTERVAL:
                publish_telemetry(
                    mqtt_client=mqtt_client,
                    state_data=state_data,
                    face_detected=face_detected,
                    ear=ear,
                    perclos=perclos,
                    eye_closed=eye_closed,
                    pose=pose,
                )

                last_mqtt_time = frame_time

           
            # ---------------------------------
            # 8. DISPLAY
            # ---------------------------------

            y = 25

            display_state = (
                state_data["confirmed_state"] or "INITIALIZING"
            )

            y = draw_text(frame, f"State: {display_state}", y)

            if face_detected:
                y = draw_text(frame, f"EAR: {ear:.3f}", y)
                y = draw_text(frame, perclos_text, y)
                y = draw_text(frame, f"Candidate: {driver_state}", y)
                y = draw_text(frame, f"Eye closed: {eye_closed}", y)

                if eye_status is not None:
                    y = draw_text(
                        frame,
                        f"Closed: {eye_status['closed_duration_ms']:.0f} ms",
                        y
                    )

                if yaw is not None:
                    y = draw_text(frame, f"Yaw ratio: {yaw:.3f}", y)

                if pitch is not None:
                    y = draw_text(frame, f"Pitch ratio: {pitch:.3f}", y)

                if roll is not None:
                    y = draw_text(frame, f"Roll: {roll:.1f}", y)

                if pose_status is not None:
                    if pose_status.get("calibrating", True):
                        y = draw_text(
                            frame,
                            "HEAD CALIBRATING...",
                            y,
                            (0, 255, 255)
                        )
                    else:
                        y = draw_text(frame, "HEAD CALIBRATED", y)

                        for key, label in [
                            ("yaw_diff", "Yaw diff"),
                            ("pitch_diff", "Pitch diff"),
                            ("deviation_duration", "Head deviation"),
                        ]:
                            value = pose_status.get(key)

                            if value is not None:
                                if key == "deviation_duration":
                                    text = f"{label}: {value:.1f}s"
                                else:
                                    text = f"{label}: {value:.3f}"

                                y = draw_text(
                                    frame,
                                    text,
                                    y,
                                    (255, 255, 255)
                                )
            else:
                y = draw_text(
                    frame,
                    "No face detected",
                    y,
                    (0, 165, 255)
                )

            cv2.imshow("Drowsiness Detection", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n[INFO] Người dùng dừng chương trình.")

    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise

    finally:
        # Giải phóng tài nguyên kể cả khi chương trình gặp lỗi.
        if camera is not None:
            camera.release()

        cv2.destroyAllWindows()

        if mqtt_client is not None:
            try:
                mqtt_client.close()
            except Exception as exc:
                print(f"[MQTT] Lỗi khi đóng kết nối: {exc}")

        print("[INFO] Đã dừng hệ thống.")


if __name__ == "__main__":
    main()
