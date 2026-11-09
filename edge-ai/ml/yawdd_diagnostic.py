"""Frozen mouth-head diagnostic on the authors' clean demo with separate frame labels.

This single external clip is not a final driver-state or glasses test. The
annotation class is read from YOLO file CONTENT, never its misleading _0 suffix.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import zipfile

import cv2
import numpy as np
from sklearn.metrics import accuracy_score,confusion_matrix,f1_score

from face_detection import FaceLandmarkDetector
from ml.dataset import sha256_file
from ml.multisignal_data import write_json
from ml.multisignal_runtime import MultisignalModel
from ml.regions import extract_regions

ARCHIVE_SHA="b5ca0bc584e5b1311d62de2f37f848bdeb1f5a5cf239a5c5e420f853465b6d66"
VIDEO_SHA="11015776ca2194d8b5c636c106a140bb8d03c4120ecdc3b29b83a35917702163"
PREFIX="Mirror/1-FemaleNoGlasses-Yawning/labels/"


def read_labels(archive):
    labels={}
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if not name.startswith(PREFIX) or not name.endswith(".txt"):
                continue
            match=re.fullmatch(r"(\d+)_\d+\.txt",name.removeprefix(PREFIX))
            if not match:raise ValueError("Unexpected frame annotation name")
            index=int(match[1])
            lines=source.read(name).decode("utf-8").strip().splitlines()
            if index in labels or len(lines)!=1:raise ValueError("Duplicate frame or ambiguous boxes")
            values=lines[0].split()
            if len(values)!=5 or values[0] not in {"0","1"}:
                raise ValueError("Expected an original binary YOLO class")
            if not all(math.isfinite(float(x)) and 0 <= float(x) <= 1 for x in values[1:]):
                raise ValueError("Invalid YOLO box")
            labels[index]=int(values[0])
    if not labels or set(labels)!=set(range(len(labels))):
        raise ValueError("Missing or nonzero-origin frame annotations")
    return labels


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=Path("ml-data/yawdd-20261110"))
    parser.add_argument("--bundle",type=Path,required=True)
    args=parser.parse_args()
    archive,video=args.data_dir/"annotations.zip",args.data_dir/"author-demo.avi"
    if sha256_file(archive)!=ARCHIVE_SHA or sha256_file(video)!=VIDEO_SHA:
        raise ValueError("Author release checksum mismatch")
    labels=read_labels(archive)
    model=MultisignalModel(args.bundle,"cpu")
    from ml.region_net import image_tensor
    import torch
    detector=FaceLandmarkDetector();cap=cv2.VideoCapture(str(video));cv2.setNumThreads(1)
    fps=cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not math.isfinite(fps) or fps<=0:
        cap.release();detector.close();raise ValueError("Invalid demo video")
    crops=[];rows=[];index=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            if index not in labels:raise ValueError("Video exceeds original annotation count")
            faces=detector.process(frame,timestamp_ms=round(index*1000/fps))
            crop=extract_regions(frame,faces[0])["mouth"] if faces else None
            row={"frame":index,"label":labels[index],"face_detected":bool(faces),"crop_available":crop is not None,
                 "top1_binary":None,"runtime_binary":None,"yawn_score":None}
            rows.append(row)
            if crop is not None:crops.append((index,crop))
            index+=1
        if index!=len(labels):raise ValueError("Full video/annotation count mismatch; no resampling")
        with torch.inference_mode():
            for offset in range(0,len(crops),128):
                batch=crops[offset:offset+128]
                _,mouth=model.network(torch.stack([image_tensor(crop) for _,crop in batch]))
                probabilities=mouth.softmax(1).numpy()
                for position,(frame_index,_) in enumerate(batch):
                    p=probabilities[position];row=rows[frame_index]
                    row["top1_binary"]=int(p.argmax()==1)
                    row["runtime_binary"]=row["top1_binary"] if p.max()>=model.manifest["mouth_confidence_threshold"] else None
                    row["yawn_score"]=float(p[1])
    finally:
        cap.release();detector.close()
    detected=[row for row in rows if row["top1_binary"] is not None]
    actual=[row["label"] for row in detected];predicted=[row["top1_binary"] for row in detected]
    matrix=np.zeros((2,3),dtype=int)
    for row in rows:
        matrix[row["label"],2 if row["runtime_binary"] is None else row["runtime_binary"]]+=1
    report={"model_version":model.model_version,"source":"https://opensource.silicon-austria.com/mujtabaa/yawdd",
        "source_commit":"222e94371df161bd673fcec4a1a755afef18ddd7","video_sha256":VIDEO_SHA,"annotations_sha256":ARCHIVE_SHA,
        "frames":len(rows),"original_labels":dict(Counter(row["label"] for row in rows)),
        "mouth_crop_coverage":len(detected)/len(rows),
        "top1_on_detected_crops":{"samples":len(detected),"accuracy":accuracy_score(actual,predicted) if detected else None,
            "macro_f1":f1_score(actual,predicted,labels=[0,1],average="macro",zero_division=0) if detected else None,
            "confusion_matrix":confusion_matrix(actual,predicted,labels=[0,1]).tolist()},
        "runtime_confidence_threshold":model.manifest["mouth_confidence_threshold"],
        "runtime_columns":["NON_YAWN","YAWN","UNKNOWN"],"runtime_confusion_matrix":matrix.tolist(),
        "runtime_unknown_fraction":float(matrix[:,2].sum()/len(rows)),
        "runtime_yawn_recall_including_unknown_misses":float(matrix[1,1]/matrix[1].sum()) if matrix[1].sum() else None,
        "samples":rows,"limits":["One public clip, no glasses; correlated frames are not independent people.",
            "Clean original demo visually inspected; labels are YOLO first-column classes, not filename suffixes.",
            "Frozen candidate and confidence threshold; this clip was not used for fit or checkpoint/threshold selection.",
            "This measures yawn recognition only, not drowsiness, distraction, policy events or physical outputs.",
            "Original YawDD and derived annotations require non-commercial research use."]}
    write_json(args.bundle/"yawdd-author-diagnostic.json",report)
    print(json.dumps({key:value for key,value in report.items() if key not in {"samples","limits"}}),flush=True)


if __name__=="__main__":
    main()
