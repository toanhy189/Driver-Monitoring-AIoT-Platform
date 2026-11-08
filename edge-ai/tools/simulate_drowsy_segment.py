"""Giả lập Edge-AI không camera, chạy code thật của edge-ai/ để tạo một đoạn:
ATTENTIVE -> DROWSY (STATE_CHANGED -> THRESHOLD_REACHED) -> ATTENTIVE (upload video DROWSY)."""

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
WORKDIR = Path(tempfile.mkdtemp(prefix="sim-edge-"))
os.environ.setdefault("AI_QUEUE_DB", str(WORKDIR / "queue.db"))
os.chdir(WORKDIR)  # upload.py ghi video vào ./recordings (đường dẫn tương đối)
sys.path.insert(0, str(EDGE))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import config  # noqa: E402
import edge_queue  # noqa: E402
from mqtt_client import MQTTClient  # noqa: E402
from service.message.publisher import publish_event, publish_telemetry  # noqa: E402
from service.utils import current_timestamp  # noqa: E402
from service.video.upload import create_video_writer, upload_video  # noqa: E402

FPS = 20
COLORS = {"ATTENTIVE": (60, 160, 60), "DROWSY": (40, 40, 200), "DISTRACTED": (0, 140, 220)}


class FakeCamera:
    def get(self, prop):
        return float(FPS)


def load_main_logic():
    """Lấy nguyên hàm trạng thái và hằng số thật từ main.py mà không import cv2/mediapipe."""
    tree = ast.parse((EDGE / "main.py").read_text(encoding="utf-8"))
    wanted = {"update_confirmed_state", "check_threshold_events"}
    names = {"CONFIRM_SECONDS", "THRESHOLD_SECONDS"}
    body, constants = [], {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            body.append(node)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    scope = {"time": time, "uuid": uuid, "current_timestamp": current_timestamp}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(EDGE / "main.py"), "exec"), scope)
    return scope, constants


def make_frame(state, t):
    frame = np.full((480, 640, 3), COLORS.get(state, (80, 80, 80)), dtype=np.uint8)
    cv2.putText(frame, f"{state}  t={t:5.1f}s", (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    return frame


def to_h264(path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[SIM] Không có ffmpeg, giữ nguyên mp4v (trình duyệt có thể không phát được)")
        return
    out = path + ".h264.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", path, "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
    os.replace(out, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attentive", type=float, default=2.0, help="giây ở trạng thái ATTENTIVE trước")
    parser.add_argument("--drowsy", type=float, default=5.0, help="giây ở trạng thái DROWSY (>= 3.5 để có cảnh báo)")
    parser.add_argument("--recover", type=float, default=2.0, help="giây ATTENTIVE sau (>= 1.2 để đóng video DROWSY)")
    parser.add_argument("--h264", action="store_true", help="chuyển video sang H.264 bằng ffmpeg trước khi upload")
    args = parser.parse_args()

    logic, constants = load_main_logic()
    state = {"candidate_state": None, "candidate_since": None, "confirmed_state": None, "state_since": None,
             "confirm_seconds": constants["CONFIRM_SECONDS"], "threshold_seconds": constants["THRESHOLD_SECONDS"],
             "threshold_since": {"DROWSY": None, "DISTRACTED": None},
             "threshold_event_sent": {"DROWSY": False, "DISTRACTED": False},
             "event_sequence": 0, "segment_message_id": None}

    assert edge_queue.init_db(), "Không khởi tạo được SQLite queue"
    mq = MQTTClient()
    deadline = time.monotonic() + 10
    while not mq.connected and time.monotonic() < deadline:
        time.sleep(0.1)
    if not mq.connected:
        sys.exit("[SIM] Không kết nối được broker. Kiểm tra AI_MQTT_* và MQTT_PORT trong .env, và `dc ps`.")

    camera = FakeCamera()
    writer = path = None
    rec_state, rec_msg = "UNKNOWN", None
    uploads, warned = [], False

    def close_and_upload():
        nonlocal writer, path
        if writer is None:
            return
        writer.release()
        writer = None
        if args.h264:
            to_h264(path)
        ok = upload_video(path, config.DEVICE_CODE, rec_state, rec_msg)
        uploads.append((rec_state, rec_msg, ok))
        print(f"[SIM] upload video {rec_state} (message_id={rec_msg}) -> {'OK' if ok else 'THẤT BẠI'}", flush=True)
        path = None

    start = last_tel = time.monotonic()
    for driver_state, seconds in (("ATTENTIVE", args.attentive), ("DROWSY", args.drowsy), ("ATTENTIVE", args.recover)):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            now = time.monotonic()
            frame = make_frame(driver_state, now - start)
            event = logic["update_confirmed_state"](driver_state, state, config.DEVICE_CODE)
            if event is not None:
                close_and_upload()
                rec_state, rec_msg = event["state"], event["message_id"]
                writer, path = create_video_writer(frame, rec_state, camera)
                if writer is None:
                    print("[SIM] CẢNH BÁO: không tạo được VideoWriter", flush=True)
                print(f"[SIM] STATE_CHANGED -> {rec_state} (message_id={rec_msg})", flush=True)
            publish_event(mq, event)
            for threshold in logic["check_threshold_events"](state, config.DEVICE_CODE):
                publish_event(mq, threshold)
                link = threshold.get("state_event_id")
                print(f"[SIM] {threshold['event_type']} (state_event_id={link})", flush=True)
                if link is None and not warned:
                    warned = True
                    print("[SIM] CẢNH BÁO: threshold event KHÔNG có state_event_id -> main.py chưa áp dụng mục 3.1", flush=True)
            if writer is not None:
                writer.write(frame)
            if now - last_tel >= 1.0:
                last_tel = now
                ear = 0.12 if driver_state == "DROWSY" else 0.30
                publish_telemetry(mq, state, True, ear, 0.35 if driver_state == "DROWSY" else 0.05,
                                  ear < 0.2, {"yaw": 0.0, "pitch": 0.0, "roll": 0.0})
            time.sleep(1 / FPS)

    close_and_upload()
    deadline = time.monotonic() + 20
    while edge_queue.get_queue() and time.monotonic() < deadline:
        time.sleep(0.2)
    pending = len(edge_queue.get_queue())
    mq.close()
    print(f"\n[SIM] Xong. Video upload: {uploads}")
    print(f"[SIM] Tin nhắn chưa được BE xác nhận (SAVED): {pending}")


if __name__ == "__main__":
    main()
