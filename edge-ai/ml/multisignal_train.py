"""Train eye/mouth heads and a subject-disjoint temporal fusion candidate.

Uses only original NTHU labels. Region models never fit the fusion-training people;
validation selects checkpoints/thresholds; historical test is reported once after selection.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import time

import cv2
import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from ml.dataset import sha256_file
from ml.multisignal_data import FORMAT, LABELS, write_json
from ml.multisignal_features import FEATURE_NAMES, FEATURE_VERSION, MultisignalWindow, window_label, bundle_version
from ml.region_net import MODEL_FORMAT, RegionNet, image_tensor, load_region_net
from ml.regions import REGION_VERSION, IMAGE_SIZE


class Regions(Dataset):
    def __init__(self, entries, augment=False):
        self.entries, self.augment = entries, augment

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        item = self.entries[index]
        image = cv2.imread(item["path"])
        if image is None:
            raise ValueError("Private crop missing; re-extract source")
        if self.augment:
            if random.random() < .5:
                image = cv2.flip(image, 1)
            alpha, beta = random.uniform(.8, 1.2), random.uniform(-10, 10)
            image = np.clip(image.astype(np.float32)*alpha+beta, 0, 255).astype(np.uint8)
        return image_tensor(image), item["task"], item["label"]


def report_metrics(y, predicted, classes):
    if not len(y):
        return {"samples": 0, "accuracy": None, "macro_f1": None, "confusion_matrix": None}
    precision, recall, f1, support = precision_recall_fscore_support(y, predicted, labels=classes, zero_division=0)
    return {"samples": len(y), "accuracy": float(accuracy_score(y, predicted)),
            "macro_f1": float(f1_score(y, predicted, labels=classes, average="macro", zero_division=0)),
            "confusion_matrix": confusion_matrix(y, predicted, labels=classes).tolist(),
            "precision": precision.tolist(), "recall": recall.tolist(), "f1": f1.tolist(), "support": support.tolist()}


def read_sources(root):
    plan = json.loads((root/"data-plan.json").read_text(encoding="utf-8"))
    summary = json.loads((root/"extraction-summary.json").read_text(encoding="utf-8"))
    if not summary.get("complete") or plan["format"] != FORMAT:
        raise ValueError("Finish full source extraction before selecting a model")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((root/"videos").glob("*/samples.json"))]
    ready = [report for report in reports if report["status"] == "READY"]
    groups = list(plan["groups"])
    if any(set(plan["groups"][a]) & set(plan["groups"][b]) for i,a in enumerate(groups) for b in groups[i+1:]):
        raise ValueError("People overlap between training and evaluation")
    return ready, plan


def region_entries(reports):
    entries = []
    for report in reports:
        for row in report["samples"]:
            for task, region, label in ((0, "eyes", "eye"), (1, "mouth", "mouth")):
                if not row.get(f"{region}_path") or (task == 0 and report["condition"] == "sunglasses"):
                    continue
                entries.append({"path": row[f"{region}_path"], "task": task, "label": row[label],
                    "subject": report["subject_id"], "condition": report["condition"], "group": report["group"]})
    return entries


def bounded_training(entries, maximum=400):
    buckets = defaultdict(list)
    for entry in entries:
        if entry["group"] == "cnn_train":
            buckets[(entry["subject"], entry["task"], entry["label"])].append(entry)
    rng = random.Random(20261110)
    selected = []
    for items in buckets.values():
        rng.shuffle(items)
        selected.extend(items[:maximum])
    return selected


def region_evaluate(network, entries, device, batch_size):
    predictions, labels, tasks, conditions = [], [], [], []
    network.eval()
    with torch.inference_mode():
        offset = 0
        for batch_index,(images, task, target) in enumerate(DataLoader(Regions(entries), batch_size=batch_size, shuffle=False, num_workers=0)):
            eye, mouth = network(images.to(device))
            prediction = torch.where(task.to(device) == 0, eye.argmax(1), mouth.argmax(1)).cpu().tolist()
            predictions.extend(prediction); labels.extend(target.tolist()); tasks.extend(task.tolist())
            conditions.extend(item["condition"] for item in entries[offset:offset+len(images)])
            offset += len(images)
            if batch_index and batch_index % 100 == 0:
                print(json.dumps({"validation_samples":offset,"total":len(entries)}),flush=True)
    result = {}
    for number, name, classes in ((0,"eye",[0,1]), (1,"mouth",[0,1,2])):
        mask = np.asarray(tasks) == number
        result[name] = report_metrics(np.asarray(labels)[mask], np.asarray(predictions)[mask], classes)
        result[name]["conditions"] = {condition: report_metrics(
            np.asarray(labels)[mask & (np.asarray(conditions) == condition)],
            np.asarray(predictions)[mask & (np.asarray(conditions) == condition)], classes)
            for condition in sorted(set(conditions))}
    return result


def train_regions(root, reports, args, device):
    output = root/"candidate"
    output.mkdir(exist_ok=True)
    entries = region_entries(reports)
    train = bounded_training(entries, args.max_per_class_subject)
    validation = [entry for entry in entries if entry["group"] == "validation"]
    write_json(output/"training-data.json",{"train_samples":len(train),"validation_samples":len(validation),
        "batch_size":args.batch_size,"head_epochs":args.head_epochs,"finetune_epochs":args.finetune_epochs,
        "max_per_class_subject":args.max_per_class_subject,"seed":20261110,
        "initial_regions_sha256":sha256_file(args.initial_regions) if args.initial_regions else None,
        "finetune_lr":args.finetune_lr,"unfreeze_blocks":args.unfreeze_blocks,"torch_version":str(torch.__version__)})
    print(json.dumps({"train_samples":len(train),"validation_samples":len(validation),"batch_size":args.batch_size}),flush=True)
    if any(set(entry["label"] for entry in train if entry["task"] == task) != set(range(classes))
           for task, classes in ((0,2), (1,3))):
        raise ValueError("Missing original classes in region training data")
    network = (load_region_net(args.initial_regions,device) if args.initial_regions
               else RegionNet(pretrained=True).to(device))
    best, history = -1., []
    torch.manual_seed(20261110); np.random.seed(20261110); random.seed(20261110)
    for parameter in network.features.parameters():
        parameter.requires_grad = False
    counts = {task: Counter(entry["label"] for entry in train if entry["task"] == task) for task in (0,1)}
    losses = {task: nn.CrossEntropyLoss(weight=torch.tensor(
        [sum(values.values()) / (len(values)*values[label]) for label in range(len(values))], device=device))
        for task, values in counts.items()}
    loader = DataLoader(Regions(train, augment=True), batch_size=args.batch_size, shuffle=True, num_workers=0)
    if args.initial_regions:
        metrics=region_evaluate(network,validation,device,args.batch_size)
        best=(metrics["eye"]["macro_f1"]+metrics["mouth"]["macro_f1"])/2
        torch.save({"format":MODEL_FORMAT,"state_dict":{key:value.cpu() for key,value in network.state_dict().items()}},output/"regions.pt")
        history.append({"epoch":0,"phase":"initialization","sha256":sha256_file(args.initial_regions),"validation":metrics})
        write_json(output/"region-selection.json",{"epoch":0,"score":best,"validation":metrics})
    optimizer = None
    for epoch in range(args.head_epochs + args.finetune_epochs):
        fine = epoch >= args.head_epochs
        if fine:
            for parameter in network.features[-args.unfreeze_blocks:].parameters():
                parameter.requires_grad = True
        if optimizer is None or epoch == args.head_epochs:
            optimizer = torch.optim.AdamW([parameter for parameter in network.parameters() if parameter.requires_grad],
                                         lr=args.finetune_lr if fine else 8e-4, weight_decay=1e-4)
        network.train(); network.features.eval()  # keep pretrained BN statistics stable with tiny batches
        total_loss = seen = 0
        started = time.monotonic()
        for batch_index,(images, task, labels) in enumerate(loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            eye, mouth = network(images)
            parts=[]
            for number,logits in ((0,eye),(1,mouth)):
                indices=(task==number).nonzero(as_tuple=True)[0]
                if len(indices):
                    indices=indices.to(device)
                    parts.append(losses[number](logits.index_select(0,indices),labels.index_select(0,indices)))
            loss=sum(parts)
            loss.backward(); optimizer.step()
            total_loss += loss.detach()*len(images); seen += len(images)
            if batch_index and batch_index % 100 == 0:
                print(json.dumps({"epoch":epoch+1,"train_samples_seen":seen,"total":len(train)}),flush=True)
        metrics = region_evaluate(network, validation, device, args.batch_size)
        score = (metrics["eye"]["macro_f1"] + metrics["mouth"]["macro_f1"]) / 2
        result = {"epoch": epoch+1, "phase": "finetune" if fine else "head", "train_samples": seen,
                  "loss": float(total_loss)/max(seen,1), "validation": metrics, "elapsed_seconds": time.monotonic()-started}
        history.append(result)
        print(json.dumps({"epoch":epoch+1,"phase":result["phase"],"validation_macro_f1":score,
                          "seconds":round(result["elapsed_seconds"],1)}), flush=True)
        if score > best:
            best = score
            torch.save({"format":MODEL_FORMAT,"state_dict":{key:value.cpu() for key,value in network.state_dict().items()}},
                       output/"regions.pt")
            write_json(output/"region-selection.json", {"epoch":epoch+1,"score":best,"validation":metrics})
        write_json(output/"region-training.json", history)
    return load_region_net(output/"regions.pt", device), entries


def predict_videos(root, reports, network, args, device):
    model_hash = sha256_file(root/"candidate/regions.pt")
    predictions_dir = root/"predictions"/model_hash[:12]
    predictions_dir.mkdir(parents=True, exist_ok=True)
    predicted = []
    for index, report in enumerate(reports):
        destination = predictions_dir/f"{report['video_id']}.json"
        if destination.exists():
            predicted.append(json.loads(destination.read_text(encoding="utf-8"))); continue
        pairs = [(i,task,row[f"{region}_path"]) for i,row in enumerate(report["samples"])
                 for task,region in ((0,"eyes"),(1,"mouth")) if row.get(f"{region}_path")]
        outputs = [{} for _ in report["samples"]]
        with torch.inference_mode():
            for offset in range(0,len(pairs),args.batch_size):
                batch = pairs[offset:offset+args.batch_size]
                images = torch.stack([image_tensor(cv2.imread(item[2])) for item in batch]).to(device)
                eye, mouth = network(images)
                probabilities=torch.cat((eye.softmax(1),mouth.softmax(1)),dim=1).cpu().numpy()
                eye,mouth=probabilities[:,:2],probabilities[:,2:]
                for row, (sample,task,_) in enumerate(batch):
                    if task == 0:
                        outputs[sample].update(eye_sleepy=float(eye[row,1]), eye_confidence=float(eye[row].max()))
                    else:
                        outputs[sample].update(mouth_yawn=float(mouth[row,1]),mouth_talk=float(mouth[row,2]),
                                               mouth_confidence=float(mouth[row].max()))
        value = {key:report[key] for key in ("video_id","subject_id","condition","group","video_sha256")}
        value["samples"] = [{**row, **scores} for row,scores in zip(report["samples"],outputs)]
        write_json(destination,value); predicted.append(value)
        if index % 20 == 0:
            print(json.dumps({"prediction_videos":index+1,"total":len(reports)}),flush=True)
    return predicted


def feature_rows(reports):
    result = []
    for report in reports:
        window = MultisignalWindow()
        for row in report["samples"]:
            signals = {key:row.get(key) for key in ("eye_sleepy","mouth_yawn","mouth_talk","ear","mar","yaw","pitch")}
            if report["condition"] == "sunglasses" or row.get("eye_confidence", 0) < .6:
                signals["eye_sleepy"] = signals["ear"] = None
            if row.get("mouth_confidence", 0) < .6:
                signals["mouth_yawn"] = signals["mouth_talk"] = signals["mar"] = None
            window.add(row["time_s"], signals)
            snapshot = window.snapshot()
            if snapshot is None:
                continue
            target = window_label(report["samples"], snapshot["start_s"], snapshot["end_s"])
            if target is None:
                continue
            result.append({"x":snapshot["features"],"label":target,"time_s":row["time_s"],
                           **{key:report[key] for key in ("video_id","subject_id","condition","group")}})
    return result


def train_fusion(root, reports):
    rows = feature_rows(reports)
    train = [row for row in rows if row["group"] == "fusion_train"]
    validation = [row for row in rows if row["group"] == "validation"]
    if not train or not validation or set(row["label"] for row in train) != {0,1}:
        raise ValueError("Missing disjoint fusion labels")
    x,y = np.asarray([row["x"] for row in train]),np.asarray([row["label"] for row in train])
    vx,vy = np.asarray([row["x"] for row in validation]),np.asarray([row["label"] for row in validation])
    estimators = {"lr":make_pipeline(StandardScaler(),LogisticRegression(class_weight="balanced",max_iter=1000,random_state=41)),
                  "rf":RandomForestClassifier(n_estimators=200,max_depth=8,min_samples_leaf=8,
                         class_weight="balanced",n_jobs=4,random_state=41)}
    choices = []
    for kind,estimator in estimators.items():
        estimator.fit(x,y)
        probabilities = estimator.predict_proba(vx)[:,1]
        for threshold in (.4,.5,.6,.7,.8,.9):
            metrics = report_metrics(vy,(probabilities>=threshold).astype(int),[0,1])
            negatives = vy == 0
            fpr = float(np.mean(probabilities[negatives]>=threshold)) if negatives.any() else 1.
            choices.append({"kind":kind,"threshold":threshold,"validation":metrics,"false_positive_rate":fpr})
    # Prefer a validation FPR <=10%; otherwise retain a visibly experimental
    # candidate and report the failure instead of fabricating acceptance.
    eligible = [choice for choice in choices if choice["false_positive_rate"] <= .1]
    selected = max(eligible or choices,key=lambda choice:(choice["validation"]["macro_f1"],-choice["false_positive_rate"]))
    estimator = estimators[selected["kind"]]
    artifact = {"format":"multisignal-fusion-v1","feature_version":FEATURE_VERSION,
                "feature_names":list(FEATURE_NAMES),"estimator":estimator,"threshold":selected["threshold"],
                "versions":{"sklearn":sklearn.__version__,"numpy":np.__version__}}
    joblib.dump(artifact,root/"candidate/fusion.joblib")
    # Selection is written before any historical-test predictions or metrics.
    write_json(root/"candidate/fusion-selection.json",{"selected":selected,"candidates":choices,
        "threshold_frozen_before_historical_test":True,"fit_subjects":sorted(set(row["subject_id"] for row in train)),
        "validation_subjects":sorted(set(row["subject_id"] for row in validation))})
    evaluation = {}
    for group in ("fusion_train","validation","historical_test"):
        subset = [row for row in rows if row["group"]==group]
        if not subset:
            continue
        probabilities=estimator.predict_proba([row["x"] for row in subset])[:,1]
        actual=np.asarray([row["label"] for row in subset]); prediction=(probabilities>=selected["threshold"]).astype(int)
        evaluation[group]=report_metrics(actual,prediction,[0,1])
        evaluation[group]["conditions"]={condition:report_metrics(actual[np.array([row["condition"]==condition for row in subset])],
            prediction[np.array([row["condition"]==condition for row in subset])],[0,1]) for condition in sorted(set(row["condition"] for row in subset))}
    write_json(root/"candidate/fusion-evaluation.json",evaluation)
    return selected,evaluation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--batch-size",type=int,default=32)
    parser.add_argument("--head-epochs",type=int,default=3)
    parser.add_argument("--finetune-epochs",type=int,default=2)
    parser.add_argument("--max-per-class-subject",type=int,default=400)
    parser.add_argument("--reuse-regions",action="store_true")
    parser.add_argument("--regions-only",action="store_true",help="Save the selected CNN without fitting/evaluating fusion")
    parser.add_argument("--initial-regions",type=Path,help="Fine-tune a trusted own checkpoint; validation retains the best weights")
    parser.add_argument("--finetune-lr",type=float,default=3e-5)
    parser.add_argument("--unfreeze-blocks",type=int,default=3)
    args=parser.parse_args()
    if not 1 <= args.unfreeze_blocks <= 13 or not 0 < args.finetune_lr <= .01:
        parser.error("Expected 1-13 backbone blocks and a positive fine-tune LR <=0.01")
    torch.set_num_threads(2); cv2.setNumThreads(1)
    torch.manual_seed(20261110);random.seed(20261110);np.random.seed(20261110)
    device="cuda" if torch.cuda.is_available() else "cpu"
    root=args.data_dir
    reports,plan=read_sources(root)
    eligible_groups=dict(Counter(report["group"] for report in reports))
    print(json.dumps({"device":device,"videos":len(reports),"groups":plan["groups"],
        "eligible_videos_by_group":eligible_groups,"historical_test_unavailable":not eligible_groups.get("historical_test")}),flush=True)
    if args.reuse_regions:
        network=load_region_net(root/"candidate/regions.pt",device);entries=region_entries(reports)
    else:
        network,entries=train_regions(root,reports,args,device)
    if args.regions_only:
        print(json.dumps({"status":"REGIONS_TRAINED","checkpoint":str(root/"candidate/regions.pt")}),flush=True)
        return
    # CNN-fit people never fit/evaluate the second-stage estimator. Avoid
    # generating unused predictions/windows for those people.
    predictions=predict_videos(root,[report for report in reports if report["group"]!="cnn_train"],network,args,device)
    selected,evaluation=train_fusion(root,predictions)
    historical=region_evaluate(network,[entry for entry in entries if entry["group"]=="historical_test"],device,args.batch_size)
    write_json(root/"candidate/region-historical-evaluation.json",historical)
    files={name:sha256_file(root/"candidate"/name) for name in ("regions.pt","fusion.joblib")}
    manifest={"format":"driver-multisignal-v1","model_version":bundle_version(files),
        "region_version":REGION_VERSION,"image_size":IMAGE_SIZE,"feature_version":FEATURE_VERSION,
        "feature_names":list(FEATURE_NAMES),"files":files,
        "policy_version":"driver-bench-20261107-v1","data_plan_sha256":sha256_file(root/"data-plan.json"),
        "label_mapping":LABELS,"landmarker_sha256":plan["landmarker_sha256"],"mediapipe_version":plan["mediapipe_version"],
        "release_status":"EXPERIMENTAL_OFFLINE_ONLY","historical_test_previously_inspected":True,
        "eligible_videos_by_group":eligible_groups,"historical_test_available":bool(eligible_groups.get("historical_test")),
        "webcam_glasses_passed":False,"physical_outputs_tested":False,"eye_confidence_threshold":.6,
        "mouth_confidence_threshold":.6,"window_seconds":5.,"min_history_seconds":2.,"max_gap_seconds":.5,
        "selected_fusion":selected,"trained_at":datetime.now(timezone.utc).isoformat(),
        "limitations":["NTHU eye labels describe sleepy eyes, not instant closure", "RGB glasses webcam still needs new live trials",
            "Historical held-out people were inspected in earlier project work", "No independent final test or physical load acceptance",
            "Sunglasses eye supervision excluded; mouth-only negatives cannot establish attentiveness"]}
    write_json(root/"candidate/manifest.json",manifest)
    print(json.dumps({"status":"TRAINED_EXPERIMENTAL","manifest":str(root/"candidate/manifest.json"),
                      "validation_fusion":evaluation.get("validation"),"historical_test_fusion":evaluation.get("historical_test")}),flush=True)


if __name__=="__main__":
    main()
