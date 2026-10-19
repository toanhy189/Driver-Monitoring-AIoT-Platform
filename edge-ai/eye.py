import numpy as np
import time


# =========================
# CẤU HÌNH
# =========================

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20

PERCLOS_WINDOW_SECONDS = 10.0
PERCLOS_WARMUP_SECONDS = 10.0

# Khoảng cách tối đa giữa 2 lần nhận diện hợp lệ.
# Nếu lớn hơn giá trị này → coi là thiếu dữ liệu.
MAX_DATA_GAP_SECONDS = 0.5


# =========================
# VỊ TRÍ 6 ĐIỂM MỖI MẮT
# =========================

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]


# =========================
# TÍNH EAR
# =========================

def calculate_ear(face_landmarks, eye_indices):

    points = []

    for index in eye_indices:
        landmark = face_landmarks[index]

        points.append(
            np.array([landmark.x, landmark.y])
        )

    p1, p2, p3, p4, p5, p6 = points

    vertical_1 = np.linalg.norm(p2 - p6)
    vertical_2 = np.linalg.norm(p3 - p5)

    horizontal = np.linalg.norm(p1 - p4)

    ear = (
        vertical_1 + vertical_2
    ) / (2.0 * horizontal)

    return ear


def calculate_average_ear(face_landmarks):

    left_ear = calculate_ear(
        face_landmarks,
        LEFT_EYE
    )

    right_ear = calculate_ear(
        face_landmarks,
        RIGHT_EYE
    )

    average_ear = (
        left_ear + right_ear
    ) / 2.0

    return average_ear


# =========================
# PERCLOS
# =========================

class PerclosCalculator:

    def __init__(
        self,
        ear_threshold=EAR_THRESHOLD,
        window_seconds=10.0,
        warmup_seconds=10.0,
        max_data_gap=0.5
    ):

        self.ear_threshold = ear_threshold
        self.window_seconds = window_seconds
        self.warmup_seconds = warmup_seconds
        self.max_data_gap = max_data_gap

        # (timestamp, eye_closed)
        self.samples = []

        # Tổng thời gian dữ liệu hợp lệ kể từ lúc bắt đầu
        self.valid_time = 0.0

        self.last_timestamp = None

    def update(self, ear):

        current_time = time.monotonic()

        eye_closed = ear < self.ear_threshold

        # =========================
        # SAMPLE ĐẦU TIÊN
        # =========================

        if self.last_timestamp is None:

            self.last_timestamp = current_time

            self.samples.append(
                (current_time, eye_closed)
            )

            return None

        # =========================
        # KHOẢNG THỜI GIAN
        # =========================

        delta = current_time - self.last_timestamp

        self.last_timestamp = current_time

        # =========================
        # THIẾU DỮ LIỆU
        # =========================

        if delta > self.max_data_gap:

            # Không tính khoảng bị mất
            self.samples.append(
                (current_time, eye_closed)
            )

            return None

        # =========================
        # DỮ LIỆU HỢP LỆ
        # =========================

        self.valid_time += delta

        self.samples.append(
            (current_time, eye_closed)
        )

        # =========================
        # GIỮ LẠI 10 GIÂY GẦN NHẤT
        # =========================

        cutoff_time = (
            current_time - self.window_seconds
        )

        self.samples = [
            sample
            for sample in self.samples
            if sample[0] >= cutoff_time
        ]

        # =========================
        # WARMUP
        # =========================

        if self.valid_time < self.warmup_seconds:

            return None

        # =========================
        # TÍNH PERCLOS
        # =========================

        closed_time = 0.0
        valid_time = 0.0

        for i in range(1, len(self.samples)):

            previous_time, previous_closed = (
                self.samples[i - 1]
            )

            current_sample_time, _ = (
                self.samples[i]
            )

            delta = (
                current_sample_time
                - previous_time
            )

            # Bỏ qua khoảng mất dữ liệu
            if delta > self.max_data_gap:
                continue

            valid_time += delta

            if previous_closed:
                closed_time += delta

        if valid_time <= 0:
            return None

        return closed_time / valid_time

# class riêng để theo dõi trạng thái mắt
class EyeClosureTracker:
    def __init__(self, ear_threshold=0.20):
        self.ear_threshold = ear_threshold
        self.closed_since = None

    def update(self, ear):
        current_time = time.monotonic()

        # Mắt đang đóng
        if ear < self.ear_threshold:

            if self.closed_since is None:
                # Bắt đầu lần nhắm mắt mới
                self.closed_since = current_time

            # Thời gian mắt đã đóng
            closed_duration = (
                current_time - self.closed_since
            )

            return {
                "is_closed": True,
                "closed_duration_ms": closed_duration * 1000
            }

        # Mắt mở lại
        else:

            closed_duration_ms = 0

            if self.closed_since is not None:
                # Tính thời gian của lần nhắm mắt vừa kết thúc
                closed_duration_ms = (
                    current_time - self.closed_since
                ) * 1000

                # Reset để chờ lần nhắm mắt tiếp theo (EAR < EAR_THRESHOLD)
                self.closed_since = None

            return {
                "is_closed": False,
                "closed_duration_ms": closed_duration_ms
            }