"""Private interactive webcam trial. No MQTT, HTTP, queue workers or actuators."""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import cv2

from config import AI_MULTISIGNAL_BUNDLE, FACE_LOSS_RESET_SECONDS, MAX_OBSERVATION_GAP_SECONDS
from eye import calculate_average_ear, EyeClosureTracker, PerclosCalculator
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseEstimator, HeadPoseTracker
from ml.multisignal_runtime import load_multisignal_model
from service.alert_policy import AlertPolicy
from service.multisignal_diagnostics import decision_reason
from service.observation import ObservationContinuity

PHASES = (
    ("1", "OPEN_NATURAL", 25, "Look forward, eyes open, blink naturally"),
    ("2", "CLOSED", 8, "Keep eyes closed until the ending beep"),
    ("3", "OPEN_RECOVERY", 15, "Open eyes, look forward"),
    ("4", "TALK", 12, "Talk normally, do not force a yawn"),
    ("5", "YAWN", 12, "Yawn naturally, or skip if you cannot"),
    ("6", "HEAD_LEFT", 10, "Turn head moderately left, face still visible"),
    ("7", "HEAD_RIGHT", 10, "Turn head moderately right, face still visible"),
    ("8", "OCCLUDED", 6, "Cover camera until the ending beep"),
    ("9", "FINAL_RECOVERY", 15, "Uncover camera, eyes open, look forward"),
)

HEAD_PHASES = (
    ("1", "HEAD_NEUTRAL", 20, "Look forward, eyes open; hold still for the head reference"),
    ("2", "LOOK_DOWN", 8, "Look down deliberately with eyes open, then return at the beep"),
    ("3", "NOD_OPEN", 20, "Simulate 3 moderate down/up nods, eyes OPEN; pause between nods"),
    ("4", "NOD_CLOSED", 20, "At your desk, simulate 3 moderate down/up nods with eyes closed; do not fall asleep"),
    ("5", "HEAD_RECOVERY", 15, "Look forward, eyes open, talk normally"),
    ("6", "HEAD_OCCLUDED", 6, "Cover camera until the ending beep"),
    ("7", "HEAD_FINAL_RECOVERY", 15, "Uncover camera, look forward, eyes open"),
)


def cue(frequency):
    try:
        import winsound
        # Tiny local cue only; its time is visible in frame-gap diagnostics.
        winsound.Beep(frequency, 100)
    except (ImportError, RuntimeError):
        pass


def describe(model, face, pose_status, raw, policy, now, gap_ms):
    signals = model.telemetry_signals()
    regions = dict(getattr(model, "region_diagnostics", {})) if face else {}
    return {
        "utc": datetime.now(timezone.utc).isoformat(), "elapsed_monotonic": now,
        "face_detected": bool(face), "raw_state": raw, "confirmed_state": policy.state,
        "policy_candidate": policy.candidate, "frame_gap_ms": gap_ms,
        "reason": decision_reason(model, bool(face), pose_status, raw,
                                  policy_gap=gap_ms is not None and gap_ms > policy.max_gap*1000),
        "allowed_policy_gap_ms": policy.max_gap*1000,
        "model_version": policy.model_version, "fusion_threshold": model.threshold,
        "window_reason": getattr(model.window, "last_quality_reason", None),
        "coverage": getattr(model.window, "last_coverage", None),
        "window_resets": getattr(model.window, "reset_count", 0),
        "regions": regions, "signals": signals, "head": pose_status,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("glasses", "no-glasses"), required=True)
    parser.add_argument("--bundle", type=Path, default=AI_MULTISIGNAL_BUNDLE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--profile-id")
    parser.add_argument("--head-down-risk", action="store_true", help="Enable sustained-downward-posture DROWSY policy locally")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--acceptance", action="store_true", help="Use a fresh 60s open/blink phase")
    parser.add_argument("--auto-close", action="store_true", help="Release camera after the final completed phase")
    short_trial = parser.add_mutually_exclusive_group()
    short_trial.add_argument("--mouth-trial", action="store_true", help="Only phases 4/5; finish after the yawn phase")
    short_trial.add_argument("--eye-trial", action="store_true", help="Only phases 1..4; finish after normal speech")
    short_trial.add_argument("--head-trial", action="store_true", help="Private guided head/posture test; no network or physical outputs")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    phases = tuple((key, name, 60 if args.acceptance and key == "1" else seconds, instruction)
                   for key, name, seconds, instruction in PHASES
                   if (not args.mouth_trial or key in {"4", "5"}) and (not args.eye_trial or key in {"1", "2", "3", "4"}))
    if args.head_trial:
        phases = HEAD_PHASES
    from config import DEVICE_CODE
    extra = {}
    if args.head_down_risk:extra["head_down_risk"]=True
    model = load_multisignal_model(args.bundle, args.device, calibration=args.calibration,
        profile_id=args.profile_id, condition=args.condition, camera=args.camera, device_code=DEVICE_CODE, **extra)
    effective_version = model.model_version
    if args.check:
        print(json.dumps({"status": "OK", "model_version": effective_version,
                          "base_model_version": getattr(model, "base_model_version", model.model_version),
                          "eye_guard": getattr(model, "guard_metadata", None),
                          "head_motion_mode": "OBSERVE_ONLY" if model.kind == "multisignal-v2" else None,
                          "head_down_policy_enabled":bool(getattr(model,"head_down",None)),
                          "camera_opened": False, "network_started": False, "phases": phases}))
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path(__file__).parent/"ml-runs"/"live-diagnostics"/(stamp+"-"+args.condition)
    output.mkdir(parents=True, exist_ok=False)
    (output/"frames").mkdir()
    meta = {"created_utc": datetime.now(timezone.utc).isoformat(), "condition": args.condition,
            "model_version": effective_version,
            "base_model_version": getattr(model, "base_model_version", model.model_version),
            "runtime_model_version": model.model_version,
            "model_or_threshold_changed": effective_version != getattr(model, "base_model_version", model.model_version),
            "eye_guard": getattr(model, "guard_metadata", None),
            "head_down_policy_enabled":bool(getattr(model,"head_down",None)),
            "mqtt_started": False, "http_started": False, "physical_outputs_used": False,
            "media": "Private local raw MJPG video + timestamped observations + sampled annotated JPEGs; no upload",
            "phase_labels": "Requested user actions, not independently verified clinical ground truth"}
    meta.update(acceptance=args.acceptance, phases=phases, calibration_used=args.calibration is not None,
                mouth_trial=args.mouth_trial, eye_trial=args.eye_trial, head_trial=args.head_trial)
    if getattr(model, "profile", None):
        meta.update(calibration_sha256=model.profile["_sha256"], calibration_format=model.profile["format"])
    (output/"trial.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    title = "AI diagnostic - PRIVATE - no network - Q exits"
    cv2.setNumThreads(1)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError("Camera is busy/unavailable. Close the previous AI window first.")
    detector = writer = None
    observations = (output/"observations.jsonl").open("w", encoding="utf-8", buffering=1)
    events_stream = (output/"policy-events.jsonl").open("w", encoding="utf-8", buffering=1)
    timings = deque(maxlen=100)
    phase = None; phase_start = None; measuring = False; done = False
    previous = last_log = last_snapshot = None
    counts = {}; phase_counts = {}; failures = frame_index = snapshot_index = 0
    policy = AlertPolicy("private-diagnostic", effective_version, max_gap=MAX_OBSERVATION_GAP_SECONDS)
    eyes = EyeClosureTracker(); perclos = PerclosCalculator()
    head = HeadPoseTracker(); estimator = HeadPoseEstimator()
    if getattr(model, "profile", None):
        from service.multisignal_calibration import head_tracker_for_profile
        head = head_tracker_for_profile(model.profile)
    state = {"threshold_since": {"DROWSY": None, "DISTRACTED": None},
             "threshold_event_sent": {"DROWSY": False, "DISTRACTED": False}}
    continuity = ObservationContinuity(eyes, perclos, head, state,
                                      reset_seconds=FACE_LOSS_RESET_SECONDS,
                                      max_gap_seconds=MAX_OBSERVATION_GAP_SECONDS)
    print(json.dumps({"status": "CAMERA_OPEN", "output": str(output), "network_started": False}), flush=True)
    try:
        detector = FaceLandmarkDetector(head_motion=True) if model.kind == "multisignal-v2" else FaceLandmarkDetector()
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, 1280, 650)
        while True:
            ok, frame = camera.read(); now = time.monotonic()
            if not ok:
                failures += 1
                continuity.update(False, now)
                model.observe(None, None, now)
                policy.update("UNKNOWN", valid=False, now=now)
                if failures >= 5:raise RuntimeError("Camera failed five consecutive reads")
                time.sleep(.05);continue
            failures = 0; frame_index += 1
            if writer is None:
                height, width = frame.shape[:2]
                writer = cv2.VideoWriter(str(output/"raw.avi"), cv2.VideoWriter_fourcc(*"MJPG"),
                                         20., (width, height))
                if not writer.isOpened():raise RuntimeError("Cannot create private recording")
            # Every recorded frame has its real monotonic timestamp below. AVI FPS is not capture FPS.
            writer.write(frame)
            gap_ms = (now-previous)*1000 if previous is not None else None
            previous = now; timings.append(now)
            faces = detector.process(frame);face = faces[0] if faces else None
            continuity.update(bool(face), now)
            ear = calculate_average_ear(face, (frame.shape[1], frame.shape[0])) if face else None
            if ear is not None and not math.isfinite(ear):ear = None
            pose = estimator.estimate(face, (frame.shape[1], frame.shape[0])) if face else None
            if pose and not all(math.isfinite(pose[k]) for k in ("yaw", "pitch")):pose = None
            pose_status = head.update(pose) if face else None
            motion_args = {"head_angles": detector.head_angles} if model.kind == "multisignal-v2" else {}
            raw = model.observe(frame, face, now, ear, pose, pose_status, **motion_args)
            events = policy.update(raw, valid=bool(face), now=now)
            for event in events:events_stream.write(json.dumps(event, allow_nan=False)+"\n")
            elapsed = now-phase_start if phase_start is not None else None
            stage = "IDLE" if phase is None else "DONE" if done else "PREP" if elapsed < 0 else "MEASURING"
            if phase is not None and not done and elapsed >= 0 and not measuring:
                measuring = True;cue(1000)
            if phase is not None and not done and elapsed >= phase[2]:
                done = True;stage = "DONE";cue(1400)
            row = describe(model, face, pose_status, raw, policy, now, gap_ms)
            row.update(frame_index=frame_index, ear_raw=ear, pose_raw=pose,
                       phase=phase[1] if phase else "IDLE", phase_stage=stage,
                       phase_elapsed_s=elapsed)
            observations.write(json.dumps(row, allow_nan=False)+"\n")
            if stage == "MEASURING":
                key = phase[1];phase_counts[key] = phase_counts.get(key, 0)+1
                group = counts.setdefault(key, {"raw": Counter(), "confirmed": Counter(), "reasons": Counter()})
                group["raw"][raw] += 1;group["confirmed"][policy.state] += 1;group["reasons"][row["reason"]] += 1
            signals = row["signals"];region = row["regions"]
            def fmt(value):return "--" if value is None else f"{value:.3f}"
            fps = (len(timings)-1)/(timings[-1]-timings[0]) if len(timings)>1 else 0
            lines = [f"PRIVATE / NO MQTT / {args.condition} | {fps:.1f} FPS",
                     "Press 1..7: neutral, look down, nod open, nod closed, recover, cover, recover; Q exits" if args.head_trial else
                     "Press 4 (talk), then 5 (yawn); Q exits" if args.mouth_trial else
                     "Press 1 (open), 2 (closed), 3 (open), 4 (talk); Q exits" if args.eye_trial else
                     "Press 1..9 to choose action; Q exits. Images stay local.",
                     (f"{phase[0]} {phase[1]}: {stage} | "+(f"{max(0,phase[2]-(elapsed or 0)):.1f}s" if not done else "Choose next key")) if phase else ("4: TALK; then 5: YAWN. Keep mouth and chin in frame." if args.mouth_trial else "1: LOOK FORWARD. First 5s: head calibration."),
                     phase[3] if phase else "Ready when you are. No physical alerts will be sent.",
                     f"State {policy.state} | Raw {raw} | {row['reason']}",
                     f"Eyes conf {fmt(region.get('eye_confidence'))} / .600 | sleepy raw {fmt((region.get('eye_probabilities') or [None,None])[1])}",
                     f"Mouth conf {fmt(region.get('mouth_confidence'))} | yawn raw {fmt((region.get('mouth_probabilities') or [None,None])[1])}",
                     f"EAR {fmt(ear)} | MAR {fmt(signals.get('mar'))} | RF {fmt(signals.get('fusion_score'))} / {model.threshold:.3f}",
                     f"Head calibrated {not pose_status.get('calibrating',True) if pose_status else False} | gap {gap_ms or 0:.0f}ms | window {row['window_reason']}"]
            if signals.get("schema_version") == "eye-mouth-v2":
                motion = signals.get("head_motion") or {}
                posture=signals.get("head_down_policy")
                if posture:lines.append(f"Head DOWN rule: {posture['state']} | {posture['observed_down_seconds']:.1f}/3s")
                lines.extend([f"Head motion OBSERVE ONLY: {motion.get('state')} | nods /20s: {motion.get('nod_count', 0)}",
                    f"Head pitch/yaw/roll deg: {fmt(motion.get('pitch_deg'))} / {fmt(motion.get('yaw_deg'))} / {fmt(motion.get('roll_deg'))}"])
                detail = (region.get("crop_details") or {}).get("mouth", {}).get("reason")
                lines.extend([f"Eye guard: {signals.get('eye_closure_state')} | mouth quality: {signals.get('mouth_quality')}",
                    "Move back/up: keep mouth and chin inside image" if detail == "OUTSIDE_FRAME" else
                    f"Mouth crop: {detail or '--'} | class confidence is separate from image quality"])
                guard_info = getattr(model, "guard_metadata", {})
                if guard_info.get("enabled"):
                    lines.append(f"EAR guard USES STATE: <{guard_info['ear_threshold']:.3f} for {guard_info['closed_seconds']:.1f}s | {guard_info['source']}")
                else:
                    lines.append("EAR guard OFF: glasses/unspecified needs a valid calibration")
            # Put diagnostics beside the image so sampled pictures still show eyelids/glasses.
            hud = cv2.copyMakeBorder(frame, 0, max(0, 300-frame.shape[0]), 0, 680,
                                     cv2.BORDER_CONSTANT, value=(15,15,15))
            for i,line in enumerate(lines):cv2.putText(hud,line,(frame.shape[1]+8,20+i*22),cv2.FONT_HERSHEY_SIMPLEX,.45,(230,245,235),1,cv2.LINE_AA)
            cv2.imshow(title, hud)
            if last_snapshot is None or now-last_snapshot >= 2:
                file = f"{snapshot_index:05d}-{row['phase']}-{policy.state}.jpg"
                cv2.imwrite(str(output/"frames"/file), hud, [cv2.IMWRITE_JPEG_QUALITY, 85])
                (output/"latest.json").write_text(json.dumps({**row,"image":str(output/"frames"/file)},indent=2,allow_nan=False),encoding="utf-8")
                snapshot_index += 1;last_snapshot = now
            if last_log is None or now-last_log >= 2:
                print(json.dumps({k:row[k] for k in ("utc","phase","phase_stage","raw_state","confirmed_state","reason","frame_gap_ms")}),flush=True)
                last_log = now
            key = cv2.waitKey(1) & 0xff
            if key in (ord("q"),27) or cv2.getWindowProperty(title,cv2.WND_PROP_VISIBLE)<1:break
            if (args.auto_close or args.mouth_trial or args.eye_trial) and done and phase and phase[0] == phases[-1][0]:break
            for candidate in phases:
                if key == ord(candidate[0]):
                    if candidate[0] == "1" and getattr(model, "kind", None) == "multisignal-v2" and not model.profile:
                        HeadPoseTracker.__init__(head)
                    phase = candidate;phase_start = time.monotonic()+3.;measuring = done = False
                    cue(650);break
    finally:
        observations.close();events_stream.close()
        camera.release()
        if writer is not None:writer.release()
        if detector is not None:detector.close()
        cv2.destroyAllWindows()
        summary = {**meta, "closed_utc":datetime.now(timezone.utc).isoformat(),
                   "frames":frame_index, "snapshots":snapshot_index,
                   "phase_sample_counts":phase_counts, "counts":counts,
                   "limits":["Counts are frames, not independent observations or measured accuracy.",
                             "Phase labels are requested actions; review video/images to verify execution.",
                             "AVI nominal FPS is fixed; replay must use observations.jsonl frame timestamps."]}
        (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
        print(json.dumps({"status":"CAMERA_CLOSED","output":str(output),"frames":frame_index}),flush=True)


if __name__ == "__main__":
    main()
