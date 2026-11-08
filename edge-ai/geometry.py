"""Convert MediaPipe normalized landmarks to a common metric image plane."""

import math


def image_point(landmark, frame_size):
    """frame_size is (width, height) of the exact image sent to MediaPipe."""
    width, height = frame_size
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("Expected finite positive image width and height")
    return float(landmark.x) * width, float(landmark.y) * height
