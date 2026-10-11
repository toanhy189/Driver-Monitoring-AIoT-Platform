"""
Chức năng chính:
- Phát hiện khuôn mặt và tính EAR.
- Tính PERCLOS và theo dõi thời gian mắt nhắm.
- Ước lượng hướng đầu và xác định DISTRACTED.
- Xác định driver_state: ATTENTIVE / DISTRACTED / DROWSY / UNKNOWN.
- Gửi telemetry định kỳ qua MQTT.
- Gửi event khi trạng thái thay đổi.
- Gửi DROWSY_THRESHOLD_REACHED khi DROWSY liên tục >= 3 giây.
"""
import uuid

import cv2
import time
from datetime import datetime, timezone

from face_detection import FaceLandmarkDetector

from drowsiness import (
    calculate_average_ear,
    PerclosCalculator,
    EyeClosureTracker
)

from mqtt_client import MQTTClient

from config import (
    DEVICE_ID,
    EAR_THRESHOLD,
    PERCLOS_THRESHOLD,
    MODEL_VERSION
)

from head_pose import (
    HeadPoseEstimator,
    HeadPoseTracker
)


def main():

    # =========================
    # CAMERA
    # =========================

    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Không thể mở webcam.")
        return

    # =========================
    # FACE LANDMARK
    # =========================

    detector = FaceLandmarkDetector()

    # =========================
    # PERCLOS
    # =========================
    '''
    perclos_calculator = PerclosCalculator(
            ear_threshold=EAR_THRESHOLD
        )
    '''
    
    perclos_calculator = PerclosCalculator(
        ear_threshold=EAR_THRESHOLD,
        window_seconds=10.0,
        warmup_seconds=10.0
    )

    eye_tracker = EyeClosureTracker(
        ear_threshold=EAR_THRESHOLD
    )

    # =========================
    # MQTT
    # =========================

    mqtt_client = MQTTClient()

    last_mqtt_time = 0
    MQTT_INTERVAL = 1.0  # gửi MQTT mỗi 1 giây
    # Theo dõi trạng thái hiện tại để phát event khi driver_state thay đổi
    last_driver_state = None

    # Thời điểm bắt đầu trạng thái hiện tại
    state_since = None

    # =========================
    # DROWSY RULE EVENT
    # =========================
    # Thời điểm bắt đầu một episode DROWSY liên tục
    drowsy_since = None

    # Đảm bảo mỗi episode DROWSY chỉ gửi 1 rule event
    drowsy_event_sent = False

    # Ngưỡng thời gian DROWSY để kích hoạt Rule của TV2
    DROWSY_EVENT_DURATION_MS = 3000

    # Theo dõi thời gian mắt mở liên tục để xác nhận đã hồi phục khỏi DROWSY
    eyes_open_since = None

    # Mắt phải mở liên tục ít nhất 1 giây mới được xem là đã hồi phục
    EYES_OPEN_RECOVERY_SECONDS = 1.0

    # =========================
    # HEAD POSE
    # =========================

    head_pose = HeadPoseEstimator()

    head_pose_tracker = HeadPoseTracker(
        yaw_threshold=0.20,
        pitch_threshold=0.05,
        calibration_seconds=5.0,
        distracted_duration=2.0
    )

    # =========================
    # MAIN LOOP
    # =========================

    try:

        while True:

            ret, frame = cap.read()

            if not ret:
                print("Không thể đọc webcam.")
                break

        #    frame_height, frame_width = frame.shape[:2]

            faces = detector.process(frame)

            if faces:

                face_landmarks = faces[0]

                # =========================
                # EAR
                # =========================

                ear = calculate_average_ear(
                    face_landmarks
                )
                eye_status = eye_tracker.update(ear)

                # =========================
                # PERCLOS
                # =========================
                perclos = perclos_calculator.update(
                    ear
                )

                if perclos is None:
                    print(
                        f"EAR={ear:.3f}, PERCLOS={perclos}"
                    )

                    perclos_text = "WARMUP"

                else:

                    perclos_text = f"{perclos:.3f}"
                # =========================
                # POSE
                # =========================
                pose = head_pose.estimate(face_landmarks)
                pose_status = head_pose_tracker.update(pose)
                
                print( #xem trạng thái head pose để debug 
                    "calibrating=", pose_status["calibrating"],
                    "valid=", pose_status["valid"],
                    "deviated=", pose_status["is_deviated"],
                    "distracted=", pose_status["is_distracted"]
                )

                if pose is not None:
                    yaw = pose["yaw"]
                    pitch = pose["pitch"]
                    roll = pose["roll"]
                else:
                    yaw = None
                    pitch = None
                    roll = None
                
                # =========================
                # DRIVER STATE
                # =========================

                current_time = time.monotonic()

                # Theo dõi thời gian mắt mở liên tục.
                # Dùng để xác nhận driver đã hồi phục sau trạng thái DROWSY.
                if eye_status["is_closed"]:
                    eyes_open_since = None
                else:
                    if eyes_open_since is None:
                        eyes_open_since = current_time

                eyes_open_duration = (
                    current_time - eyes_open_since
                    if eyes_open_since is not None
                    else 0.0
                )

                # Chỉ xem là đã hồi phục khi mắt mở liên tục đủ thời gian yêu cầu.
                eyes_recovered = (
                    eyes_open_duration >= EYES_OPEN_RECOVERY_SECONDS
                )

                # Xác định trạng thái theo thứ tự:
                # 1. DROWSY: PERCLOS cao và mắt chưa hồi phục.
                # 2. DISTRACTED: đầu lệch khỏi tư thế bình thường đủ lâu.
                # 3. ATTENTIVE: khuôn mặt hợp lệ, đã calibration và không thuộc 2 trường hợp trên.
                # 4. UNKNOWN: chưa đủ dữ liệu để xác định trạng thái.
                if (
                    perclos is not None
                    and perclos > PERCLOS_THRESHOLD
                    and not eyes_recovered
                ):
                    driver_state = "DROWSY"

                elif pose_status["is_distracted"]:
                    driver_state = "DISTRACTED"

                elif (
                    pose_status["valid"]
                    and not pose_status["calibrating"]
                ):
                    driver_state = "ATTENTIVE"

                else:
                    driver_state = "UNKNOWN"
                    
                # =========================
                # DROWSY RULE EVENT 
                # =========================

                current_time = time.monotonic()

                if driver_state == "DROWSY":

                    # Bắt đầu một episode DROWSY mới
                    if drowsy_since is None:
                        drowsy_since = current_time
                        drowsy_event_sent = False

                    # Tính thời gian DROWSY liên tục của episode hiện tại
                    drowsy_duration_ms = (
                        current_time - drowsy_since
                    ) * 1000

                    # Khi DROWSY liên tục >= 3 giây:
                    # gửi 1 event cho TV2 để kiểm tra Rule.
                    if (
                        drowsy_duration_ms >= DROWSY_EVENT_DURATION_MS
                        and not drowsy_event_sent
                    ):
                        event = {
                            "event_id": str(uuid.uuid4()),
                            "device_id": DEVICE_ID,
                            "timestamp": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "model_version": MODEL_VERSION,
                            "event_type": "DROWSY_THRESHOLD_REACHED",
                            "state": "DROWSY",
                            "state_duration_ms": round(
                                drowsy_duration_ms
                            )
                        }
                        mqtt_client.publish_event(event)
                            # Đánh dấu episode này đã gửi event,
                            # tránh gửi lặp lại ở các frame tiếp theo.
                        drowsy_event_sent = True

                    else:
                        # Driver đã thoát DROWSY -> kết thúc episode hiện tại.
                        # Episode DROWSY tiếp theo sẽ được tính lại từ đầu.
                        drowsy_since = None
                        drowsy_event_sent = False

                    # =========================
                    # DRIVER STATE EVENT
                    # =========================

                    current_time = time.monotonic()

                    # Lưu trạng thái đầu tiên, chưa phát event vì chưa có trạng thái trước đó.
                    if last_driver_state is None:
                        last_driver_state = driver_state
                        state_since = current_time

                    # Chỉ phát event khi trạng thái thực sự thay đổi.
                    elif driver_state != last_driver_state:

                        # Lưu trạng thái vừa kết thúc và thời gian trạng thái đó kéo dài.
                        previous_state = last_driver_state
                        previous_state_duration = current_time - state_since

                        event = {
                            "event_id": str(uuid.uuid4()),
                            "device_id": DEVICE_ID,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "model_version": MODEL_VERSION,
                            "event_type": "STATE_CHANGED",

                            # Trạng thái trước khi thay đổi
                            "previous_state": previous_state,

                            # Trạng thái mới
                            "state": driver_state,

                            # Thời gian trạng thái trước đã duy trì
                            "previous_state_duration_ms": round(
                                previous_state_duration * 1000
                            )
                        }

                        mqtt_client.publish_event(event)

                        # Cập nhật trạng thái mới để theo dõi episode tiếp theo.
                        last_driver_state = driver_state
                        state_since = current_time

                # =========================
                # TELEMETRY
                # =========================

                
                current_time = time.time()

                if current_time - last_mqtt_time >= MQTT_INTERVAL:
                    # Telemetry gửi định kỳ cho TV2/frontend.
                    # Khác với event: telemetry là dữ liệu trạng thái hiện tại,
                    # không phải tín hiệu kích hoạt Rule.
                    telemetry = {
                        "device_id": DEVICE_ID,
                        "timestamp": datetime.now(timezone.utc).isoformat(),

                        "ear": round(ear, 3),
                        "perclos": round(perclos, 3) if perclos is not None else None,

                        "eye_closed": eye_status["is_closed"],
                        "closed_duration_ms": round(
                            eye_status["closed_duration_ms"], 1
                        ),

                        "driver_state": driver_state,

                        "head_pose": {
                            "yaw": round(yaw, 3) if yaw is not None else None,
                            "pitch": round(pitch, 3) if pitch is not None else None,
                            "roll": round(roll, 1) if roll is not None else None,
                            "yaw_diff": round(
                                pose_status["yaw_diff"], 3
                            ) if pose_status["yaw_diff"] is not None else None,
                            "pitch_diff": round(
                                pose_status["pitch_diff"], 3
                            ) if pose_status["pitch_diff"] is not None else None
                        }
                    }
                    mqtt_client.publish_telemetry(telemetry)

                    last_mqtt_time = current_time

                # =========================
                # HIỂN THỊ
                # =========================
                cv2.putText(
                    frame,
                    f"Eye closed: {eye_status['is_closed']}",
                    (30, 145),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    f"Closed: {eye_status['closed_duration_ms']:.0f} ms",
                    (30, 180),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )


                cv2.putText(
                    frame,
                    f"EAR: {ear:.3f}",
                    (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    f"PERCLOS: {perclos_text}",
                    (30, 75),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    f"STATE: {driver_state}",
                    (30, 110),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

                if pose is not None:

                    cv2.putText(
                        frame,
                        f"Yaw ratio: {yaw:.3f}",
                        (30, 315),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2
                    )

                    cv2.putText(
                        frame,
                        f"Pitch ratio: {pitch:.3f}",
                        (30, 350),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2
                    )

                    cv2.putText(
                        frame,
                        f"Roll: {roll:.1f}",
                        (30, 385),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2
                    )

                    if pose_status["calibrating"]:

                        cv2.putText(
                            frame,
                            "HEAD CALIBRATING...",
                            (30, 420),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 255),
                            2
                        )

                    else:

                        cv2.putText(
                            frame,
                            "HEAD CALIBRATED",
                            (30, 420),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0),
                            2
                        )
                    if not pose_status["calibrating"]:

                        cv2.putText(
                            frame,
                            f"Yaw diff: {pose_status['yaw_diff']:.3f}",
                            (30, 455),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2
                        )

                        cv2.putText(
                            frame,
                            f"Pitch diff: {pose_status['pitch_diff']:.3f}",
                            (30, 490),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2
                        )

                        cv2.putText(
                            frame,
                            f"Head deviation: "
                            f"{pose_status['deviation_duration']:.1f}s",
                            (30, 525),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2
                        )
                # =========================
                # LANDMARKS
                # =========================

                h, w, _ = frame.shape

                for landmark in face_landmarks:

                    x = int(landmark.x * w)
                    y = int(landmark.y * h)

                    cv2.circle(
                        frame,
                        (x, y),
                        1,
                        (0, 255, 0),
                        -1
                    )

            # =========================
            # NO FACE
            # =========================

            if not faces:
                # Không phát hiện khuôn mặt -> không đủ dữ liệu để xác định trạng thái.
                driver_state = "UNKNOWN"

                # Kết thúc episode DROWSY hiện tại.
                # Không được tiếp tục tính DROWSY khi không nhìn thấy mặt.
                drowsy_since = None
                drowsy_event_sent = False

            # =========================
            # HIỂN THỊ WEBCAM
            # =========================

            cv2.imshow(
                "Drowsiness Detection",
                frame
            )

            # Q để thoát
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:

        cap.release()

        detector.close()

        mqtt_client.close()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()