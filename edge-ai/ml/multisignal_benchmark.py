"""Measure a frozen candidate on recorded video; never connect to demo devices."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import ctypes
import io
import json
import math
from pathlib import Path
import platform
import time
from unittest.mock import patch

import cv2
import numpy as np

from eye import calculate_average_ear
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseEstimator, HeadPoseTracker
from ml.multisignal_data import write_json
from ml.multisignal_runtime import MultisignalModel
from service.alert_policy import AlertPolicy


def peak_memory_bytes():
    if platform.system()=="Windows":
        class Counters(ctypes.Structure):
            _fields_=[("cb",ctypes.c_ulong),("faults",ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
                ("peak_working","working","peak_pool","pool","peak_nonpage","nonpage","pagefile","peak_pagefile")]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        measure=ctypes.WinDLL("psapi",use_last_error=True).GetProcessMemoryInfo
        measure.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
        measure.restype=ctypes.c_int
        if measure(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            return counters.peak_working
        return None
    import resource
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system()=="Darwin" else value*1024


def measure(job,bundle,device,seconds):
    model=MultisignalModel(bundle,device)
    detector=FaceLandmarkDetector();estimator=HeadPoseEstimator();head=HeadPoseTracker()
    policy=AlertPolicy("offline-benchmark",model.model_version)
    cap=cv2.VideoCapture(job["video_path"],cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,1])
    if not cap.isOpened():
        detector.close();raise ValueError("Recorded benchmark source unavailable")
    now=[0.];due=0.;previous=None;states=Counter();channels=Counter();latencies=[];cnn=[]
    begin=time.perf_counter();cpu=time.process_time()
    try:
        with patch("head_pose.time.monotonic",side_effect=lambda:now[0]),redirect_stdout(io.StringIO()):
            while cap.grab():
                timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
                if timestamp > seconds:break
                if timestamp+1e-8 < due:continue
                due+=.2
                ok,frame=cap.retrieve()
                if not ok:raise ValueError("Recorded benchmark frame failed to decode")
                now[0]=timestamp
                started=time.perf_counter()
                faces=detector.process(frame,timestamp_ms=round(timestamp*1000))
                face=faces[0] if faces else None
                if not face or (previous is not None and timestamp-previous>.5):head.interrupt()
                ear=calculate_average_ear(face,(frame.shape[1],frame.shape[0])) if face else None
                ear=ear if ear is not None and math.isfinite(ear) else None
                pose=estimator.estimate(face,(frame.shape[1],frame.shape[0])) if face else None
                pose=pose if pose and all(math.isfinite(pose[key]) for key in ("yaw","pitch")) else None
                status=head.update(pose)
                candidate=model.observe(frame,face,timestamp,ear,pose,status)
                policy.update(candidate,valid=bool(face),now=timestamp)
                latencies.append((time.perf_counter()-started)*1000)
                if model.last_inference_ms is not None:cnn.append(model.last_inference_ms)
                states[candidate]+=1
                for key in ("eyes_available","mouth_available"):
                    channels[key]+=int(model.telemetry_signals()[key])
                previous=timestamp
    finally:
        cap.release();detector.close()
    wall=time.perf_counter()-begin
    return {"video_id":job["video_id"],"condition":job["condition"],"source_sample_hz":5,
        "samples":len(latencies),"model_version":model.model_version,"device":device,
        "mean_pipeline_ms":float(np.mean(latencies)),"p50_pipeline_ms":float(np.percentile(latencies,50)),
        "p95_pipeline_ms":float(np.percentile(latencies,95)),"max_pipeline_ms":max(latencies),
        "mean_cnn_fusion_ms":float(np.mean(cnn)) if cnn else None,
        "wall_seconds_including_decode":wall,"processing_samples_per_wall_second":len(latencies)/wall,
        "mean_cpu_cores":(time.process_time()-cpu)/wall,"peak_process_rss_bytes":peak_memory_bytes(),
        "candidate_counts":dict(states),"channel_available_samples":dict(channels),"inference_failed":model.failed,
        "last_signals":model.telemetry_signals(),"last_candidate":candidate,"last_face_detected":bool(face)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--device",choices=("cpu","cuda"),default="cpu")
    parser.add_argument("--seconds",type=float,default=20)
    args=parser.parse_args()
    if not 5 <= args.seconds <= 120:raise ValueError("Expected 5-120 seconds")
    cv2.setNumThreads(1)
    jobs=json.loads((args.data_dir/"jobs.json").read_text(encoding="utf-8"))
    selected=[next(job for job in jobs if job["group"]=="validation" and job["condition"]==condition)
              for condition in ("noglasses","glasses")]
    results=[measure(job,args.data_dir/"candidate",args.device,args.seconds) for job in selected]
    output={"recordings":results,"limits":["Recorded NTHU videos, no new webcam/glasses acceptance.",
        "5 Hz source sampling; throughput measured without real-time waiting, network, rendering, encoding or audio.",
        "Pipeline includes landmarks, eye/mouth inference, geometry, temporal fusion and policy; decode is included only in wall throughput.",
        "Head calibration assumes a forward-facing start, which the source may not provide; state counts are not accuracy.",
        "Measurements include cold inference and may be affected by other programs."]}
    write_json(args.data_dir/"candidate"/f"benchmark-{args.device}.json",output)
    print(json.dumps(output),flush=True)


if __name__=="__main__":
    main()
