"""Five-point geometry metrics; these do not measure driver-state accuracy."""
import numpy as np


def canonical_five(points):
    points = np.asarray(points, dtype=float)
    if points.shape != (5, 2) or not np.isfinite(points).all():
        raise ValueError("Expected five finite 2D landmarks")
    eyes = points[:2][np.argsort(points[:2, 0])]
    mouth = points[3:][np.argsort(points[3:, 0])]
    return np.vstack([eyes, points[2], mouth])


def nme(predicted, truth):
    predicted, truth = canonical_five(predicted), canonical_five(truth)
    distance = np.linalg.norm(truth[0]-truth[1])
    if distance <= 0:
        raise ValueError("Zero ground-truth eye separation")
    return float(np.linalg.norm(predicted-truth, axis=1).mean()/distance)


def evaluate_benchmark(truth, results):
    eligible = []
    for index, points in enumerate(truth):
        try:
            nme(points, points)
            eligible.append(index)
        except ValueError:
            pass
    if not eligible:
        raise ValueError("No valid ground-truth points")
    errors = {}
    for name, result in results.items():
        if len(result["predictions"]) != len(truth) or len(result["times"]) != len(truth):
            raise ValueError("Prediction/ground-truth length mismatch")
        errors[name] = {}
        for index in eligible:
            try:
                errors[name][index] = nme(result["predictions"][index], truth[index])
            except (ValueError, TypeError):
                pass
    common = set(eligible).intersection(*(set(value) for value in errors.values()))
    summary = []
    for name, values in errors.items():
        times = np.asarray(results[name]["times"], dtype=float)[eligible]
        if not np.isfinite(times).all() or np.any(times < 0):
            raise ValueError("Invalid measured inference times")
        summary.append({"Model": name, "Eligible images": len(eligible),
            "Detection rate (%)": 100*len(values)/len(eligible),
            "NME detected (%)": 100*float(np.mean(list(values.values()))) if values else None,
            "Common detected images": len(common),
            "NME common (%)": 100*float(np.mean([values[i] for i in common])) if common else None,
            "Mean inference (ms)": 1000*float(times.mean()),
            "FPS (inference only)": 1/float(times.mean()) if times.mean() > 0 else None,
            "Errors": len(results[name].get("errors", []))})
    return summary
