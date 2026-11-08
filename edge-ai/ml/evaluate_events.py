"""Evaluate AI warning events against reviewed UTC state intervals, not windows."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path


def date(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("All dates must include UTC offset")
    return result


def evaluate(events_path, truth_path):
    with Path(truth_path).open(encoding="utf-8-sig", newline="") as source:
        intervals = list(csv.DictReader(source))
    intervals.sort(key=lambda row: (row["session_id"], date(row["start"])))
    previous = {}
    for row in intervals:
        row["begin"], row["finish"] = date(row["start"]), date(row["end"])
        if row["state"] not in {"ATTENTIVE", "DISTRACTED", "DROWSY", "UNKNOWN"} or row["finish"] <= row["begin"]:
            raise ValueError("Invalid ground-truth interval")
        if row["session_id"] in previous and row["begin"] < previous[row["session_id"]]:
            raise ValueError("Overlapping ground-truth intervals")
        previous[row["session_id"]] = row["finish"]
    warnings = {}
    for line in Path(events_path).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if not event.get("event_type", "").endswith("_THRESHOLD_REACHED"):
            continue
        key = event["message_id"]
        if key in warnings and warnings[key] != event:
            raise ValueError("Message ID reused with different content")
        warnings[key] = event
    detections, false_episodes, wrong_state, unlabelled = {}, set(), set(), 0
    for event in warnings.values():
        observed = date(event["observed_at"])
        emitted = date(event["timestamp"])
        if emitted < observed:
            raise ValueError("Event precedes its camera observation")
        matches = [(i, row) for i, row in enumerate(intervals) if row["session_id"] == event["session_id"]
                   and row["begin"] <= observed < row["finish"]]
        if not matches or matches[0][1]["state"] == "UNKNOWN":
            unlabelled += 1
            continue
        index, truth = matches[0]
        identity = (event["session_id"], event["episode_id"])
        if truth["state"] == "ATTENTIVE":
            false_episodes.add(identity)
        elif truth["state"] != event["state"]:
            wrong_state.add(identity)
        elif emitted < truth["finish"]:
            delay = (emitted-truth["begin"]).total_seconds()
            detections[index] = min(detections.get(index, float("inf")), delay)
    attentive_hours = sum((row["finish"]-row["begin"]).total_seconds() for row in intervals
                          if row["state"] == "ATTENTIVE")/3600
    risks = [index for index, row in enumerate(intervals) if row["state"] in {"DROWSY", "DISTRACTED"}]
    return {"unique_warning_events": len(warnings), "risk_intervals": len(risks),
            "detected_intervals": len(detections), "missed_intervals": len(risks)-len(detections),
            "false_warning_episodes": len(false_episodes), "wrong_state_episodes": len(wrong_state),
            "annotated_attentive_hours": attentive_hours,
            "false_warning_episodes_per_attentive_hour": len(false_episodes)/attentive_hours if attentive_hours else None,
            "ai_detection_delay_seconds": [{"session_id": intervals[i]["session_id"],
                "state": intervals[i]["state"], "start": intervals[i]["start"], "delay_s": value}
                for i, value in sorted(detections.items())],
            "unevaluated_warning_events": unlabelled,
            "limits": ["Reviewed annotated intervals only; gaps are not labelled ATTENTIVE.",
                       "Delay ends at AI event creation, not ESP32 actuation; physical ACK/timing evidence is separate.",
                       "Repeats count once per false-warning episode. UNKNOWN is excluded from negative exposure."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve previous evaluations; choose a new output")
    result = evaluate(args.events, args.truth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
