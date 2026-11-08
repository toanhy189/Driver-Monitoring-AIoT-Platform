"""Four guided eye measurements; local numeric data only, no MQTT or video."""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
import uuid

from config import DEVICE_CODE
from service.eye_calibration import analyze, PHASES, DURATION


def cue(frequency):
    def play():
        try:
            import winsound
            winsound.Beep(frequency, 180)
        except (ImportError, RuntimeError, OSError):
            pass
    threading.Thread(target=play, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("glasses", "no-glasses"), required=True)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="Check command/config without opening camera")
    args = parser.parse_args()
    if args.check:
        print(json.dumps({"camera_opened": False, "network_started": False,
                          "phases": list(PHASES), "seconds_per_phase": DURATION,
                          "automatic_activation": False}))
        return
    import cv2
    from eye import LEFT_EYE, RIGHT_EYE, calculate_ear
    from face_detection import FaceLandmarkDetector
    from head_pose import HeadPoseEstimator
    output = args.output or (Path(__file__).resolve().parent / "ml-runs" / "eye-calibration" /
                             (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]))
    output.mkdir(parents=True, exist_ok=False)
    title = "Eye calibration (local only)"
    camera = cv2.VideoCapture(args.camera)
    detector = None
    phases = {}
    phase = None
    starts = None
    phase_rows = []
    completed = False
    try:
        if not camera.isOpened():
            raise RuntimeError("Cannot open camera; close the driver-monitor window first")
        detector = FaceLandmarkDetector()
        head = HeadPoseEstimator()
        cv2.namedWindow(title)
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Camera read failed; partial measurements are not accepted")
            now = time.monotonic()
            faces = detector.process(frame)
            ear = left = right = None
            if faces:
                size = (frame.shape[1], frame.shape[0])
                left = calculate_ear(faces[0], LEFT_EYE, size)
                right = calculate_ear(faces[0], RIGHT_EYE, size)
                pose = head.estimate(faces[0], size)
                if (pose is not None and all(math.isfinite(v) for v in
                        (left, right, pose["yaw"], pose["pitch"]))):
                    ear = (left+right)/2
                else:
                    left = right = None
            if phase is not None:
                elapsed = now-starts
                if 0 <= elapsed <= DURATION:
                    phase_rows.append({"phase": phase, "elapsed_s": elapsed,
                                       "ear": ear, "left_ear": left, "right_ear": right})
                if elapsed > DURATION:
                    phases[phase] = phase_rows
                    phase = None
                    cue(600)
                    if len(phases) == len(PHASES):
                        completed = True
                        break
                else:
                    text = f"{phase}: " + (f"GET READY {-elapsed:.1f}s" if elapsed < 0
                                            else f"MEASURING {DURATION-elapsed:.1f}s")
                    cv2.putText(frame, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 255, 255), 2)
            if phase is None:
                text = f"Press {len(phases)+1}: {PHASES[len(phases)]} (5s); Q cancels"
                cv2.putText(frame, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
            reading = "NO VALID FACE" if ear is None else f"EAR {ear:.3f}  L {left:.3f}  R {right:.3f}"
            cv2.putText(frame, reading, (12, 65), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
            cv2.imshow(title, frame)
            key = cv2.waitKey(1) & 0xff
            if key in (ord("q"), 27) or cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                break
            if phase is None and key == ord(str(len(phases)+1)):
                phase = PHASES[len(phases)]
                starts = time.monotonic()+2.0  # Time to act before measurement starts.
                phase_rows = []
                cue(900)
    finally:
        camera.release()
        if detector is not None:
            detector.close()
        cv2.destroyAllWindows()
        if phase is not None and phase_rows:
            phases[phase] = phase_rows
        with (output / "observations.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=("phase", "elapsed_s", "ear", "left_ear", "right_ear"))
            writer.writeheader()
            for rows in phases.values():
                writer.writerows(rows)
        report = analyze(phases, DEVICE_CODE, args.condition, capture_completed=completed)
        report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "reason": report.get("reason"),
                          "candidate_threshold": report.get("candidate_threshold"),
                          "report": str(output / "report.json"), "threshold_applied": False}))


if __name__ == "__main__":
    main()
