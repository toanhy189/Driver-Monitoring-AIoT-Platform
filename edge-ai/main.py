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

import cv2
import time
import uuid
import math
import json
from pathlib import Path

import logging

from face_detection import FaceLandmarkDetector
from eye import (
    calculate_average_ear,
    PerclosCalculator,
    EyeClosureTracker,
)

from mqtt_client import MQTTClient
from config import (DEVICE_CODE, EAR_THRESHOLD, PERCLOS_THRESHOLD,
                    FACE_LOSS_RESET_SECONDS, MAX_OBSERVATION_GAP_SECONDS,
                    AI_MODEL_MODE, AI_MODEL_PATH, AI_DEBUG_PREDICTIONS, AI_EYE_CLOSURE_GUARD_ENABLED,
                    AI_EYE_CLOSURE_CALIBRATION,
                    MODEL_VERSION, METRICS_PATH,
                    VIDEO_MAX_CLIP_SECONDS, VIDEO_MAX_CLIP_BYTES, VIDEO_STORAGE_MAX_BYTES, RECORDING_DIR)
from ml.runtime import load_optional_model, fuse_state
from service.eye_closure_guard import EyeClosureGuard
from service.eye_calibration import load_threshold
from head_pose import HeadPoseEstimator, HeadPoseTracker

from edge_queue import init_db
from service.message.publisher import publish_event, publish_telemetry
from service.video.upload import create_video_writer, recorded_bytes
from service.video.worker import VideoUploadWorker
from service.local_alert import LocalAlertWorker
from service.alert_policy import AlertPolicy
from service.runtime_metrics import RuntimeMetrics
from service.observation import ObservationContinuity
from service.utils import current_timestamp, draw_text


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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# =========================
# UTILITY FUNCTIONS
# =========================

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

    # Khởi tạo trạng thái xác nhận lần đầu và tạo event.
    if state_data["confirmed_state"] is None:
        state_data["confirmed_state"] = candidate
        state_data["state_since"] = now

        event = {
            "message_id": str(uuid.uuid4()),
            "sequence_number": state_data["event_sequence"],
            "device_code": device_code,
            "timestamp": current_timestamp(),
            "event_type": "STATE_CHANGED",
            "previous_state": None,
            "state": candidate,
        }

        state_data["event_sequence"] += 1
        return event

    # Trạng thái không thay đổi.
    if candidate == state_data["confirmed_state"]:
        return None

    previous_state = state_data["confirmed_state"]

    event = {
        "message_id": str(uuid.uuid4()),
        "sequence_number": state_data["event_sequence"],
        "device_code": device_code,
        "timestamp": current_timestamp(),
        "event_type": "STATE_CHANGED",
        "previous_state": previous_state,
        "state": candidate
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

def create_session_ended_event(state_data, device_code):
    """Tạo event khi phiên Edge AI kết thúc."""
    event = {
        "message_id": str(uuid.uuid4()),
        "sequence_number": state_data["event_sequence"],
        "device_code": device_code,
        "timestamp": current_timestamp(),
        "event_type": "SESSION_ENDED",
        "final_state": state_data["confirmed_state"],
    }

    state_data["event_sequence"] += 1
    return event

# =========================
# MAIN
# =========================

def main():
    global y  # Dùng biến toàn cục để vẽ overlay

    camera = None
    mqtt_client = None
    session_started = False
    detector = None
    video_worker = None
    local_alert = None
    eye_guard = None

    video_writer = None
    active_video_path = None
    recording_state = "UNKNOWN"
    recording_message_id = None
    clip_started_at = None
    next_recording_attempt_at = 0.0
    policy = None
    metrics = RuntimeMetrics(METRICS_PATH)
    last_metrics_at = 0.0

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

    try:
        drowsiness_model = load_optional_model(AI_MODEL_MODE, AI_MODEL_PATH)
        state_data["model_version"] = (drowsiness_model.model_version
                                       if drowsiness_model is not None else MODEL_VERSION)
        logger.info("AI classifier: %s", state_data["model_version"])
        if drowsiness_model is not None and AI_EYE_CLOSURE_GUARD_ENABLED:
            guard_threshold = (load_threshold(AI_EYE_CLOSURE_CALIBRATION, DEVICE_CODE)
                               if AI_EYE_CLOSURE_CALIBRATION else EAR_THRESHOLD)
            eye_guard = EyeClosureGuard(ear_threshold=guard_threshold,
                                        max_gap_seconds=MAX_OBSERVATION_GAP_SECONDS)
            logger.info("AI fusion: %s; EAR threshold %.4f; closure >=1s, recovery >=1s; experimental",
                        eye_guard.VERSION, eye_guard.ear_threshold)
        policy = AlertPolicy(DEVICE_CODE, state_data["model_version"], max_gap=MAX_OBSERVATION_GAP_SECONDS)
        state_data["session_id"] = policy.session_id
        if not init_db():
            raise RuntimeError("Cannot initialize SQLite queues")
        video_worker = VideoUploadWorker()
        video_worker.start()
        local_alert = LocalAlertWorker()
        local_alert.start()

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
        continuity = ObservationContinuity(
            eye_tracker, perclos_calculator, head_pose_tracker, state_data,
            reset_seconds=FACE_LOSS_RESET_SECONDS,
            max_gap_seconds=MAX_OBSERVATION_GAP_SECONDS,
        )

        # Khởi tạo MQTT.
        mqtt_client = MQTTClient(model_version=state_data["model_version"])
        session_started = True

        print("[INFO] Hệ thống phát hiện buồn ngủ đã khởi động.")
        print("[INFO] Nhấn Q để thoát.")

        camera_failures = 0
        last_mqtt_time = 0.0

        eyes_open_since = None

        while True:
            success, frame = camera.read()

            if not success:
                local_alert.cancel()
                for event in policy.update("UNKNOWN", valid=False):
                    local_alert.notify(event)
                    publish_event(mqtt_client, event)
                continuity.update(False)
                if eye_guard is not None:
                    eye_guard.reset()
                if drowsiness_model is not None:
                    drowsiness_model.update(time.monotonic())
                eyes_open_since = None
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
            loop_started = time.perf_counter()
            frame_time = time.monotonic()
            frame_observed_at = current_timestamp()

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

            landmark_started = time.perf_counter()
            faces = detector.process(frame)
            metrics.observe("landmarks", (time.perf_counter()-landmark_started)*1000)
            if faces:
                frame_size = (frame.shape[1], frame.shape[0])
                ear = calculate_average_ear(faces[0], frame_size)
                pose = head_pose.estimate(faces[0], frame_size)
                if (not math.isfinite(ear) or pose is None
                        or not all(math.isfinite(pose[k]) for k in ("yaw", "pitch"))):
                    # Degenerate landmarks are missing observations, not open eyes.
                    faces, ear, pose = [], None, None
            if continuity.update(bool(faces), frame_time):
                eyes_open_since = None
                if eye_guard is not None:
                    eye_guard.reset()

            if faces:
                face_detected = True
                face = faces[0]

                # ---------------------------------
                # 2. EYE / EAR / PERCLOS
                # ---------------------------------

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

            decision_started = time.perf_counter()
            if drowsiness_model is not None:
                binary_prediction = drowsiness_model.update(frame_time, ear, pose)
                closure_risk = eye_guard.update(frame_time, ear) if eye_guard is not None else False
                driver_state = fuse_state(binary_prediction, pose_status, eye_closure_risk=closure_risk)
                metrics.observe("estimator", drowsiness_model.last_inference_ms)
                if AI_DEBUG_PREDICTIONS and drowsiness_model.last_diagnostics:
                    logger.info("ML diagnostic: %s", json.dumps(drowsiness_model.last_diagnostics,
                                                               sort_keys=True, allow_nan=False))
            metrics.observe("ml_update_and_fusion", (time.perf_counter()-decision_started)*1000)

            # ---------------------------------
            # 5. CONFIRM STATE
            # ---------------------------------

            policy_gap_ms = None
            if AI_DEBUG_PREDICTIONS and policy.last_update is not None:
                policy_gap_ms = (frame_time - policy.last_update) * 1000
            events = policy.update(driver_state, valid=face_detected, now=frame_time,
                                   observed_at=frame_observed_at)
            state_data["confirmed_state"] = policy.state
            state_data["candidate_state"] = policy.candidate
            state_data["observed_at"] = policy.observed_at
            state_data["episode_id"] = policy.episode_id
            if policy.suspended or policy.candidate not in {"DROWSY", "DISTRACTED"}:
                local_alert.cancel()
            if (video_writer is not None and clip_started_at is not None and
                    (frame_time - clip_started_at >= VIDEO_MAX_CLIP_SECONDS or
                     recorded_bytes(active_video_path) >= VIDEO_MAX_CLIP_BYTES) and
                    not any(event["event_type"] == "STATE_CHANGED" for event in events)):
                events.append(policy.rotate_clip())
            if (video_writer is None and policy.state is not None and frame_time >= next_recording_attempt_at
                    and not any(event["event_type"] == "STATE_CHANGED" for event in events)):
                events.append(policy.rotate_clip())
            for event in events:
                if event["event_type"] == "STATE_CHANGED":
                    if video_writer is not None:
                        video_writer.release()
                        video_writer = None
                        if active_video_path is not None:
                            video_worker.enqueue(recording_message_id, active_video_path,
                                                 DEVICE_CODE, recording_state)
                    active_video_path = None
                    recording_state = event["state"]
                    recording_message_id = event["message_id"]
                    try:
                        video_writer, active_video_path = create_video_writer(frame, recording_state, camera)
                    except OSError:
                        logger.exception("Recording unavailable; camera and warnings continue")
                        video_writer, active_video_path = None, None
                    clip_started_at = frame_time
                    next_recording_attempt_at = frame_time + 5
                    event["recording_status"] = "RECORDING" if video_writer is not None else "UNAVAILABLE"
                local_alert.notify(event)
                publish_event(mqtt_client, event)

            # ---------------------------------
            # 7. MQTT TELEMETRY
            # ---------------------------------

            if frame_time - last_mqtt_time >= MQTT_INTERVAL:
                if AI_DEBUG_PREDICTIONS:
                    diagnostic = {"observed_at": frame_observed_at, "face_detected": face_detected,
                        "ear": ear, "eye_closure_risk": bool(eye_guard and eye_guard.active),
                        "eye_guard_threshold": eye_guard.ear_threshold if eye_guard else None,
                        "raw_state": driver_state, "policy_candidate": policy.candidate,
                        "confirmed_state": policy.state, "frame_gap_ms": policy_gap_ms,
                        "head": pose_status, "ml_last_snapshot_quality":
                            getattr(getattr(drowsiness_model, "window", None), "last_quality_reason", None)}
                    logger.info("AI observation: %s", json.dumps(diagnostic, sort_keys=True, allow_nan=False))
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
            y = draw_text(frame, f"UTC: {frame_observed_at}", y)
            if drowsiness_model is not None:
                y = draw_text(frame, f"Model: {state_data['model_version']}", y)
                if AI_DEBUG_PREDICTIONS and drowsiness_model.last_score is not None:
                    score_text = (f"{drowsiness_model.kind.upper()} score: {drowsiness_model.last_score:.3f}"
                                  f" / threshold: {drowsiness_model.threshold:.3f}")
                    y = draw_text(frame, score_text, y)
            if eye_guard is not None:
                y = draw_text(frame, f"Eye guard (<{eye_guard.ear_threshold:.3f}): " +
                              ("CLOSED RISK" if eye_guard.active else "observing"), y)

            if face_detected:
                y = draw_text(frame, f"EAR: {ear:.3f}", y)
                y = draw_text(frame, perclos_text, y)
                y = draw_text(frame, f"Candidate: {driver_state}", y)
                eye_label = f"Eye feature (<{EAR_THRESHOLD:.2f})" if eye_guard else "Eye closed"
                y = draw_text(frame, f"{eye_label}: {eye_closed}", y)

                if eye_status is not None:
                    y = draw_text(
                        frame,
                        f"Feature closed: {eye_status['closed_duration_ms']:.0f} ms",
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

            metrics.observe("frame_processing", (time.perf_counter()-loop_started)*1000)
            metrics.frame()
            if frame_time - last_metrics_at >= 10:
                try:
                    metrics.write(timestamp=current_timestamp(), session_id=policy.session_id,
                                  model_version=state_data["model_version"])
                except OSError:
                    logger.exception("Cannot write runtime measurements")
                last_metrics_at = frame_time
            cv2.imshow("Drowsiness Detection", frame)

            if video_writer is not None:
                video_writer.write(frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n[INFO] Người dùng dừng chương trình.")

    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise

    finally:
        # Persist the final clip without waiting for an HTTP upload on exit.
        if video_writer is not None:
            video_writer.release()
            video_writer = None

            if active_video_path is not None:
                video_worker.enqueue(recording_message_id, active_video_path,
                                     DEVICE_CODE, recording_state)

        if local_alert is not None:
            local_alert.stop()
        if video_worker is not None:
            video_worker.stop()

        # Gửi event kết thúc phiên trước khi đóng MQTT.
        if session_started and mqtt_client is not None:
            try:
                event = policy.end()
                publish_event(mqtt_client, event)
            except Exception as exc:
                logger.error("Cannot publish SESSION_ENDED: %s", exc)

        # Giải phóng các tài nguyên khác.
        if camera is not None:
            camera.release()

        if detector is not None:
            detector.close()

        cv2.destroyAllWindows()

        if mqtt_client is not None:
            try:
                mqtt_client.close()
            except Exception as exc:
                logger.error("MQTT close error: %s", exc)

        print("[INFO] Đã dừng hệ thống.")


def check_runtime():
    """Load native vision/model code without a webcam, network or user queue writes."""
    import json
    import sqlite3
    import numpy as np
    from ml.runtime import DrowsinessModel
    from service.alert_policy import POLICY_VERSION
    with sqlite3.connect(":memory:") as connection:
        connection.execute("SELECT 1").fetchone()
    detector = FaceLandmarkDetector()
    try:
        detector.process(np.zeros((64, 64, 3), dtype=np.uint8))
    finally:
        detector.close()
    model = DrowsinessModel(AI_MODEL_PATH) if AI_MODEL_MODE == "ml" else None
    guard_threshold = None
    if model is not None and AI_EYE_CLOSURE_GUARD_ENABLED:
        guard_threshold = (load_threshold(AI_EYE_CLOSURE_CALIBRATION, DEVICE_CODE)
                           if AI_EYE_CLOSURE_CALIBRATION else EAR_THRESHOLD)
    print(json.dumps({"status": "OK", "camera_opened": False, "network_started": False,
        "model_version": model.model_version if model else MODEL_VERSION,
        "eye_guard_enabled": guard_threshold is not None, "eye_guard_threshold": guard_threshold,
        "policy_version": POLICY_VERSION}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Driver monitoring Edge AI")
    parser.add_argument("--check", action="store_true", help="Check native dependencies without camera/network")
    if parser.parse_args().check:
        check_runtime()
    else:
        main()
