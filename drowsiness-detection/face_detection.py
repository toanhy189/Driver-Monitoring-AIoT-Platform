import cv2
import mediapipe as mp


class FaceLandmarkDetector:
    def __init__(self, model_path="face_landmarker.task"):
        base_options = mp.tasks.BaseOptions(
            model_asset_path=model_path
        )

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.landmarker = (
            mp.tasks.vision.FaceLandmarker
            .create_from_options(options)
        )

        self.timestamp_ms = 0

    def process(self, frame):
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
        self.timestamp_ms += 33

        # Phát hiện khuôn mặt + landmarks
        result = self.landmarker.detect_for_video(
            image,
            self.timestamp_ms
        )

        return result.face_landmarks

    def close(self):
        self.landmarker.close()