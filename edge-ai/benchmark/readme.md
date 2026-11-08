# Facial landmark benchmark

Notebook: `detection_ai.ipynb`. This evaluates five facial points, not driver states.

Week-4 corrections:
- IMAGE mode uses `detect()`, not `detect_for_video()`.
- Both predictions and ground truth use the same image-x order for eyes and mouth.
- Invalid/non-finite points and zero interocular ground truth are excluded explicitly.
- Report detection coverage, NME on each detected subset, and NME on the common detected subset.
- FPS is inference-only; camera pipeline FPS is measured separately.
- Saved notebook outputs were cleared because their numbers predate these corrections.

Run the notebook again with the original Facial Keypoints CSV and benchmark-only dependencies before citing new numbers. The old 100% / 8.08 ms claims are not current evidence. Keep the CSV, image IDs, versions and model hashes with the benchmark report.

`landmark_metrics.py` is covered by camera-free tests. No large model weights were downloaded or benchmark runs repeated during the policy implementation.
