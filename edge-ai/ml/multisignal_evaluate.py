"""Replay frozen candidates on complete sampled videos, including missing observations.

No webcam, network, queue, speaker or physical outputs. This reports sampled NTHU
labels, not a new independent test or physical-actuation acceptance.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np

from head_pose import HeadPoseTracker
from ml.dataset import sha256_file
from ml.multisignal_data import write_json
from ml.multisignal_features import MultisignalWindow
from ml.multisignal_runtime import fused_state
from service.alert_policy import AlertPolicy


def positive_intervals(samples):
    """Causal sample-and-hold annotation intervals; gaps are not interpolated."""
    intervals = []
    for first, second in zip(samples, samples[1:]):
        start, end = first["time_s"], second["time_s"]
        if first["drowsiness"] != 1 or not 0 < end-start <= .5:
            continue
        if intervals and abs(intervals[-1][1]-start) < 1e-7:
            intervals[-1][1] = end
        else:
            intervals.append([start,end])
    return intervals


def replay(report, manifest, artifact, mask_known_sunglasses=False, prepared_cache=None):
    v2 = manifest.get("format") == "driver-multisignal-v2"
    if v2:
        from ml.multisignal_v2_features import V2Window, ProbabilitySmoother, FusionDecision, admitted_values, state_and_reason
        smoother = ProbabilitySmoother()
        decision = FusionDecision(artifact["threshold"], artifact["leave_threshold"])
    window_type = V2Window if v2 else MultisignalWindow
    window = window_type(manifest["window_seconds"],manifest["min_history_seconds"],manifest["max_gap_seconds"])
    clock = [0.]
    origin = datetime(2026,11,10,tzinfo=timezone.utc)
    policy = AlertPolicy("offline-replay",manifest["model_version"],clock=lambda:clock[0],
                         utcnow=lambda:origin+timedelta(seconds=clock[0]))
    head = HeadPoseTracker()
    observations, warnings, prepared = [], [], []
    cache_key = (report["video_id"], manifest.get("feature_version"), manifest["window_seconds"],
                 manifest["min_history_seconds"], manifest["max_gap_seconds"], mask_known_sunglasses)
    cached = prepared_cache.get(cache_key) if prepared_cache is not None else None
    previous = None
    # Head calibration mirrors the real launcher, which asks the driver to look
    # forward for five seconds. NTHU does not guarantee that start condition.
    with patch("head_pose.time.monotonic",side_effect=lambda:clock[0]), redirect_stdout(io.StringIO()):
        for row in report["samples"] if cached is None else ():
            clock[0] = now = row["time_s"]
            present = bool(row.get("eyes_path") or row.get("mouth_path") or row.get("yaw") is not None)
            gap = previous is not None and now-previous > .5
            if not present or gap:
                head.interrupt()
            pose = {key:row[key] for key in ("yaw","pitch")} if row.get("yaw") is not None and row.get("pitch") is not None else None
            pose_status = head.update(pose)
            if v2:
                values = admitted_values(row, row["quality_v2"],
                    mask_eyes=mask_known_sunglasses and report["condition"] == "sunglasses")
                if not present or gap:
                    window.reset(); smoother.reset(); snapshot = None
                else:
                    values = smoother.update(now, values)
                    window.add(now, values); snapshot = window.snapshot()
                eyes, mouth = values["eye_sleepy"] is not None, values["mouth_yawn"] is not None
            else:
                eyes = (present and row.get("eye_confidence",0) >= manifest["eye_confidence_threshold"]
                        and not (mask_known_sunglasses and report["condition"] == "sunglasses"))
                mouth = present and row.get("mouth_confidence",0) >= manifest["mouth_confidence_threshold"]
                values = {"eye_sleepy":row.get("eye_sleepy") if eyes else None,
                          "ear":row.get("ear") if eyes else None,
                          "mouth_yawn":row.get("mouth_yawn") if mouth else None,
                          "mouth_talk":row.get("mouth_talk") if mouth else None,
                          "mar":row.get("mar") if mouth else None,
                          "yaw":row.get("yaw"),"pitch":row.get("pitch")}
                window.add(now,values)
                snapshot = window.snapshot()
            prepared.append({"row":row,"present":present,"eyes":eyes,"mouth":mouth,
                             "pose_status":pose_status,"yawn":values["mouth_yawn"],"snapshot":snapshot,
                             "force_unknown":v2 and (not present or gap), "window_reason":window.last_quality_reason})
            previous=now
    if cached is not None:
        prepared = cached
    elif prepared_cache is not None:
        prepared_cache[cache_key] = prepared
    ready=[item for item in prepared if item["snapshot"] is not None]
    # The estimator is stateless. Batch its causal feature vectors without ever
    # adding a future frame to an earlier window or starting a thread pool per frame.
    scores=iter(artifact["estimator"].predict_proba([item["snapshot"]["features"] for item in ready])[:,1]) if ready else iter(())
    for item in prepared:
        row=item["row"];clock[0]=now=row["time_s"]
        snapshot=item["snapshot"];score=float(next(scores)) if snapshot else None
        prediction = decision.update(score) if v2 else int(score >= artifact["threshold"]) if score is not None else None
        if v2:
            candidate = state_and_reason(prediction,item["pose_status"],eyes=item["eyes"],yawn=item["yawn"],
                window_reason=item["window_reason"])[0] if not item["force_unknown"] else "UNKNOWN"
        else:
            candidate = (fused_state(prediction,item["pose_status"],eyes_available=item["eyes"],mouth_yawn=item["yawn"])
                         if item["present"] else "UNKNOWN")
        events = policy.update(candidate,valid=item["present"],now=now)
        warnings.extend({"time_s":now,"episode":event["episode_id"],"level":event["level"]}
                        for event in events if event["event_type"] == "DROWSY_THRESHOLD_REACHED")
        observations.append({"time_s":now,"candidate":candidate,"confirmed":policy.state or "UNKNOWN",
            "eyes":item["eyes"],"mouth":item["mouth"],"fusion_ready":snapshot is not None,
            "truth":row["drowsiness"],"score":score})
    exposure=Counter()
    for first,second in zip(observations,observations[1:]):
        dt=second["time_s"]-first["time_s"]
        if not 0 < dt <= .5:
            continue
        exposure["total"]+=dt
        exposure["positive" if first["truth"] else "negative"]+=dt
        exposure["unknown"]+=dt*(first["candidate"]=="UNKNOWN")
        exposure["fusion_unavailable"]+=dt*(not first["fusion_ready"])
        exposure["eye_unavailable"]+=dt*(not first["eyes"])
        exposure["mouth_unavailable"]+=dt*(not first["mouth"])
        if first["truth"]:
            exposure["positive_detected"]+=dt*(first["candidate"]=="DROWSY")
        else:
            exposure["negative_flagged"]+=dt*(first["candidate"]=="DROWSY")
    intervals=positive_intervals(report["samples"])
    detected=[]
    eligible=[]
    for start,end in intervals:
        if end-start < 3.5:  # .5 s candidate confirmation + first 3 s policy threshold
            continue
        eligible.append([start,end])
        matches=[warning["time_s"]-start for warning in warnings if start <= warning["time_s"] < end]
        if matches:
            detected.append(min(matches))
    false_episodes=set()
    times=np.asarray([row["time_s"] for row in report["samples"]])
    for warning in warnings:
        index=min(int(np.searchsorted(times,warning["time_s"],side="right")-1),len(times)-1)
        if report["samples"][index]["drowsiness"]==0:
            false_episodes.add(warning["episode"])
    return {"video_id":report["video_id"],"condition":report["condition"],"group":report["group"],
            "exposure_seconds":dict(exposure),"positive_intervals":len(intervals),
            "eligible_intervals":len(eligible),"detected_intervals":len(detected),
            "delay_seconds":detected,"drowsy_warning_events":len(warnings),"false_warning_episodes":len(false_episodes)}


def aggregate(reports):
    exposure=Counter()
    for report in reports:
        exposure.update(report["exposure_seconds"])
    total=exposure["total"]
    eligible=sum(report["eligible_intervals"] for report in reports)
    detected=sum(report["detected_intervals"] for report in reports)
    false=sum(report["false_warning_episodes"] for report in reports)
    delays=[delay for report in reports for delay in report["delay_seconds"]]
    ratio=lambda x,y:x/y if y else None
    return {"videos":len(reports),"exposure_seconds":dict(exposure),
        "unknown_fraction":ratio(exposure["unknown"],total),
        "eye_unavailable_fraction":ratio(exposure["eye_unavailable"],total),
        "mouth_unavailable_fraction":ratio(exposure["mouth_unavailable"],total),
        "positive_time_recall":ratio(exposure["positive_detected"],exposure["positive"]),
        "negative_time_false_positive_fraction":ratio(exposure["negative_flagged"],exposure["negative"]),
        "eligible_intervals":eligible,"detected_intervals":detected,"missed_intervals":eligible-detected,
        "eligible_interval_recall":ratio(detected,eligible),"false_warning_episodes":false,
        "false_warning_episodes_per_negative_hour":ratio(false,exposure["negative"]/3600),
        "median_warning_delay_seconds":float(np.median(delays)) if delays else None,
        "p95_warning_delay_seconds":float(np.percentile(delays,95)) if delays else None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--bundle", type=Path, help="Frozen candidate override; predictions stay under data-dir")
    args=parser.parse_args()
    root=args.data_dir;bundle=args.bundle or root/"candidate"
    manifest=json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
    for name,expected in manifest["files"].items():
        if sha256_file(bundle/name)!=expected:
            raise ValueError("Frozen model hash mismatch")
    artifact=joblib.load(bundle/"fusion.joblib")
    v2 = manifest.get("format") == "driver-multisignal-v2"
    predictions=root/"predictions" if v2 else root/"predictions"/manifest["files"]["regions.pt"][:12]
    reports=[json.loads(path.read_text(encoding="utf-8")) for path in sorted(predictions.glob("*.json"))]
    reports=[report for report in reports if report["group"] in {"validation","historical_test"}]
    if not reports:
        raise ValueError("No frozen evaluation predictions")
    results=[replay(report,manifest,artifact) for report in reports]
    summary={}
    for group in ("validation","historical_test"):
        subset=[row for row in results if row["group"]==group]
        summary[group]=aggregate(subset)
        summary[group]["conditions"]={condition:aggregate([row for row in subset if row["condition"]==condition])
            for condition in sorted({row["condition"] for row in subset})}
    output={"format":"multisignal-policy-replay-v2" if v2 else "multisignal-policy-replay-v1","model_version":manifest["model_version"],"summary":summary,
        "videos":results,"limits":[
            "Original binary drowsiness annotations sampled at 3 Hz; no new independent labels or people.",
            "Missing observations and warmup remain in exposure and miss counts; no interpolation across >0.5s gaps.",
            "Warnings replay actual AlertPolicy, including confirmation and 3/6/10s thresholds; no MQTT/ESP32 actuation.",
            "Eligible intervals last >=3.5s; shorter positives are separately included in positive-time recall.",
            "Only DROWSY warnings are scored against drowsiness labels; DISTRACTED quality needs separate validation.",
            "Per-video head calibration uses first five seconds, whose neutral-forward condition is not guaranteed by NTHU.",
            "Replay follows versioned runtime admission; sunglasses are NOT automatically detected or masked at runtime.",
            "For v2, calibrated eye closure is DISABLED: no independent closure labels/profile exist for these videos.",
            "Frames/windows overlap; counts do not represent independent statistical trials."]}
    write_json(bundle/"policy-replay.json",output)
    print(json.dumps({group:{key:value for key,value in result.items() if key!="conditions"} for group,result in summary.items()}),flush=True)


if __name__=="__main__":
    main()
