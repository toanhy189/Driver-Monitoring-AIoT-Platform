import math
import time


class HeadPoseEstimator:
    """
    Uoc luong huong dau dua tren vi tri tuong doi
    cua cac landmark MediaPipe.

    Yaw/Pitch la gia tri ratio, khong phai do.
    Roll chi de quan sat, chua dung trong logic.
    """

    NOSE = 1

    LEFT_EYE = 263
    RIGHT_EYE = 33

    FOREHEAD = 10
    CHIN = 152

    MOUTH_LEFT = 61
    MOUTH_RIGHT = 291

    def __init__(self):
        pass

    @staticmethod
    def distance(p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]

        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def point(face_landmarks, index):
        landmark = face_landmarks[index]

        return landmark.x, landmark.y

    def estimate(self, face_landmarks):

        nose = self.point(
            face_landmarks,
            self.NOSE
        )

        left_eye = self.point(
            face_landmarks,
            self.LEFT_EYE
        )

        right_eye = self.point(
            face_landmarks,
            self.RIGHT_EYE
        )

        forehead = self.point(
            face_landmarks,
            self.FOREHEAD
        )

        chin = self.point(
            face_landmarks,
            self.CHIN
        )

        mouth_left = self.point(
            face_landmarks,
            self.MOUTH_LEFT
        )

        mouth_right = self.point(
            face_landmarks,
            self.MOUTH_RIGHT
        )

        # =====================================================
        # YAW
        # =====================================================

        eye_center_x = (
            left_eye[0] + right_eye[0]
        ) / 2

        eye_distance = self.distance(
            left_eye,
            right_eye
        )

        if eye_distance == 0:
            return None

        yaw_ratio = (
            nose[0] - eye_center_x
        ) / eye_distance

        # =====================================================
        # PITCH
        # =====================================================

        face_height = self.distance(
            forehead,
            chin
        )

        if face_height == 0:
            return None

        mouth_center_y = (
            mouth_left[1] + mouth_right[1]
        ) / 2

        nose_to_mouth = (
            mouth_center_y - nose[1]
        )

        pitch_ratio = (
            nose_to_mouth / face_height
        )

        # =====================================================
        # ROLL
        # =====================================================

        dx = right_eye[0] - left_eye[0]
        dy = right_eye[1] - left_eye[1]

        roll_angle = math.degrees(
            math.atan2(dy, dx)
        )

        return {
            "yaw": yaw_ratio,
            "pitch": pitch_ratio,
            "roll": roll_angle
        }


class HeadPoseTracker:
    """
    Calibration baseline va theo doi thoi gian dau lech huong.

    Quy trinh:

        1. Calibration trong calibration_seconds.
        2. Lay trung binh yaw/pitch lam baseline.
        3. So sanh gia tri hien tai voi baseline.
        4. Neu vuot threshold -> bat dau dem thoi gian.
        5. Neu tro lai binh thuong -> reset.
    """

    def __init__(
        self,
        yaw_threshold=0.20,
        pitch_threshold=0.05,
        calibration_seconds=5.0,
        distracted_duration=2.0
    ):
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold

        self.calibration_seconds = calibration_seconds
        self.distracted_duration = distracted_duration

        # Calibration
        self.calibrating = True
        self.calibration_start = time.monotonic()

        self.yaw_samples = []
        self.pitch_samples = []

        self.yaw_baseline = None
        self.pitch_baseline = None

        # Theo doi lech huong
        self.deviation_since = None

    # =========================================================
    # CALIBRATION
    # =========================================================

    def _update_calibration(self, yaw, pitch):
        current_time = time.monotonic()

        self.yaw_samples.append(yaw)
        self.pitch_samples.append(pitch)

        elapsed = current_time - self.calibration_start

        if elapsed >= self.calibration_seconds:

            self.yaw_baseline = (
                sum(self.yaw_samples)
                / len(self.yaw_samples)
            )

            self.pitch_baseline = (
                sum(self.pitch_samples)
                / len(self.pitch_samples)
            )

            self.calibrating = False

            print()
            print("=== HEAD POSE CALIBRATION DONE ===")
            print(
                f"Yaw baseline: "
                f"{self.yaw_baseline:.3f}"
            )
            print(
                f"Pitch baseline: "
                f"{self.pitch_baseline:.3f}"
            )
            print("==================================")
            print()

    # =========================================================
    # UPDATE
    # =========================================================

    def update(self, pose):
        """
        pose:
            {
                "yaw": ...,
                "pitch": ...,
                "roll": ...
            }

        Tra ve:
            calibration
            yaw_diff
            pitch_diff
            is_deviated
            deviation_duration
            is_distracted
        """

        if pose is None:
            return {
                "calibrating": self.calibrating,
                "valid": False,
                "yaw_diff": None,
                "pitch_diff": None,
                "is_deviated": False,
                "deviation_duration": 0.0,
                "is_distracted": False
            }

        yaw = pose["yaw"]
        pitch = pose["pitch"]

        # =====================================================
        # CALIBRATION
        # =====================================================

        if self.calibrating:

            self._update_calibration(
                yaw,
                pitch
            )

            return {
                "calibrating": True,
                "valid": True,
                "yaw_diff": None,
                "pitch_diff": None,
                "is_deviated": False,
                "deviation_duration": 0.0,
                "is_distracted": False
            }

        # =====================================================
        # TINH DO LECH
        # =====================================================

        yaw_diff = abs(
            yaw - self.yaw_baseline
        )

        pitch_diff = abs(
            pitch - self.pitch_baseline
        )

        is_deviated = (
            yaw_diff > self.yaw_threshold
            or
            pitch_diff > self.pitch_threshold
        )

        current_time = time.monotonic()

        # =====================================================
        # BAT DAU / RESET DEM THOI GIAN
        # =====================================================

        if is_deviated:

            if self.deviation_since is None:
                self.deviation_since = current_time

            deviation_duration = (
                current_time
                - self.deviation_since
            )

        else:

            self.deviation_since = None
            deviation_duration = 0.0

        # =====================================================
        # DISTRACTED
        # =====================================================

        is_distracted = (
            is_deviated
            and
            deviation_duration >= self.distracted_duration
        )

        return {
            "calibrating": False,
            "valid": True,
            "yaw_diff": yaw_diff,
            "pitch_diff": pitch_diff,
            "is_deviated": is_deviated,
            "deviation_duration": deviation_duration,
            "is_distracted": is_distracted
        }

    # =========================================================
    # GET BASELINE
    # =========================================================

    def get_baseline(self):
        return {
            "yaw": self.yaw_baseline,
            "pitch": self.pitch_baseline
        }