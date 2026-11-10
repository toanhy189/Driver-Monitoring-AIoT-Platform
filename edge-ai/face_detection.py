import cv2
import mediapipe as mp
import time
from config import TASK_PATH


class FaceLandmarkDetector:
    def __init__(self, model_path=TASK_PATH, *, head_motion=False):
        base_options = mp.tasks.BaseOptions(
            model_asset_path=str(model_path)
        )

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_facial_transformation_matrixes=head_motion
        )

        self.landmarker = (
            mp.tasks.vision.FaceLandmarker
            .create_from_options(options)
        )

        self.started_at = time.monotonic()
        self.timestamp_ms = -1
        self.head_motion = head_motion
        self.head_angles = None

    def process(self, frame, timestamp_ms=None):
        # OpenCV dùng BGR → chuyển sang RGB
        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        # Chuyển ảnh sang MediaPipe Image
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame
        )

        # Timestamp phải tăng dần
        if timestamp_ms is None:
            elapsed_ms = int((time.monotonic() - self.started_at) * 1000)
            self.timestamp_ms = max(self.timestamp_ms + 1, elapsed_ms)
        else:
            # Offline video uses source timestamps, never extraction wall time.
            timestamp_ms = int(timestamp_ms)
            if timestamp_ms < 0 or timestamp_ms <= self.timestamp_ms:
                raise ValueError("Video timestamps must be nonnegative and strictly increasing")
            self.timestamp_ms = timestamp_ms

        # Phát hiện khuôn mặt + landmarks
        result = self.landmarker.detect_for_video(
            image,
            self.timestamp_ms
        )

        self.head_angles = None
        if self.head_motion and result.face_landmarks and result.facial_transformation_matrixes:
            from service.head_motion import rotation_angles
            self.head_angles = rotation_angles(result.facial_transformation_matrixes[0])
        return result.face_landmarks

    def close(self):
        self.landmarker.close()
