"""Plot aggregate metrics from a completed run; never export face images."""

import argparse
import json
import os
from pathlib import Path


def plot_report(run_dir):
    run_dir = Path(run_dir)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    # Keep font caches with the local experiment, away from a crowded system drive.
    os.environ.setdefault("MPLCONFIGDIR", str((run_dir / "plot-cache").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    methods = {"baseline": report["baseline"], **report["models"]}
    historical = "historical_test_subjects" in report
    audit_label = "historical regression audit" if historical else "held-out subjects"
    figure, axes = plt.subplots(1, len(methods), figsize=(4.2 * len(methods), 4.2), squeeze=False)
    for axis, (name, result) in zip(axes[0], methods.items()):
        matrix = np.asarray(result["test"]["confusion_matrix"])
        axis.imshow(matrix, cmap="Blues", vmin=0)
        for (row, column), value in np.ndenumerate(matrix):
            axis.text(column, row, str(value), ha="center", va="center",
                      color="white" if value > matrix.max() / 2 else "black")
        axis.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["ALERT", "DROWSY"],
                 yticklabels=["ALERT", "DROWSY"], xlabel="Predicted", ylabel="Video label",
                 title=f"{name}: {audit_label}")
    figure.suptitle("UTA-RLDD binary experiment; weak video labels, valid windows only")
    figure.tight_layout()
    figure.savefig(run_dir / "confusion_matrices.png", dpi=180)
    plt.close(figure)

    names = list(methods)
    x = np.arange(len(names))
    figure, axis = plt.subplots(figsize=(8.5, 4.5))
    for offset, metric, label in ((-0.24, "macro_f1", "Macro F1"),
                                  (0.0, "recall", "DROWSY recall"),
                                  (0.24, "precision", "DROWSY precision")):
        values = [methods[name]["test"][metric] if metric == "macro_f1" else
                  methods[name]["test"]["per_class"]["DROWSY"][metric] for name in names]
        bars = axis.bar(x + offset, values, width=0.24, label=label)
        axis.bar_label(bars, fmt="%.2f", fontsize=8)
    axis.set(xticks=x, xticklabels=names, ylim=(0, 1.17), ylabel="Score",
             title=("Historical test audit; selected using grouped development CV" if historical
                    else "Held-out subject test; models selected using validation"))
    axis.legend(loc="upper center", ncols=3)
    figure.tight_layout()
    figure.savefig(run_dir / "test_metrics.png", dpi=180)
    plt.close(figure)
    ablation_path = run_dir / "ablation-summary.csv"
    if ablation_path.exists():
        import pandas as pd
        table = pd.read_csv(ablation_path)
        figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        for axis, kind in zip(axes, ("rf", "svm")):
            for group in ("core", "eyes", "full"):
                rows = table[(table.kind == kind) & (table.feature_group == group)].sort_values("window_seconds")
                axis.plot(rows.window_seconds, rows.macro_f1, marker="o", label=group)
            axis.set(title=kind.upper(), xlabel="Window (seconds)", ylabel="Mean-person macro F1",
                     ylim=(0, 1), xticks=sorted(table.window_seconds.unique()))
            axis.legend()
            axis.grid(alpha=.2)
        figure.suptitle("Development GroupKFold tuning scores; no test-based ablation selection")
        figure.tight_layout()
        figure.savefig(run_dir / "cv_ablation.png", dpi=180)
        plt.close(figure)
        selected = report["models"][report["selected_kind"]]
        trials = json.loads((run_dir / "cv-trials.json").read_text(encoding="utf-8"))
        rows = sorted([t for t in trials if t["kind"] == report["selected_kind"]
                       and t["parameters"] == selected["parameters"]
                       and t["feature_group"] == selected["feature_group"]
                       and t["window_seconds"] == selected["window_seconds"]], key=lambda t: t["threshold"])
        figure, axis = plt.subplots(figsize=(8.5, 4.5))
        for key in ("macro_f1", "drowsy_recall", "drowsy_precision", "false_positive_rate"):
            axis.plot([r["threshold"] for r in rows], [r["cv_mean_person"][key] for r in rows], marker=".", label=key)
        axis.axvline(selected["threshold"], linestyle="--", color="black", label="Selected threshold")
        axis.set(xlabel="Uncalibrated classifier score cutoff", ylabel="Mean-person score", ylim=(0, 1.05),
                 title="Development OOF threshold tradeoff; these scores were used for tuning")
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
        figure.tight_layout()
        figure.savefig(run_dir / "threshold_tradeoff.png", dpi=180)
        plt.close(figure)
    print(f"Saved aggregate plots under {run_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    plot_report(args.run_dir)


if __name__ == "__main__":
    main()
