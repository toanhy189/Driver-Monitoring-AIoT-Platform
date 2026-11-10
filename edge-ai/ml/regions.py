"""Shared pixel geometry and independent eye/mouth crops for training and live AI."""
import math

import cv2
import numpy as np

from geometry import image_point

REGION_VERSION = "pixel-eye-mouth-v1"
IMAGE_SIZE = 96
EYE_POINTS = (33, 133, 159, 145, 362, 263, 386, 374)
MOUTH_POINTS = (61, 291, 13, 14, 0, 17, 78, 308)


def mouth_aspect_ratio(face, frame_size):
    """Lip opening / corner distance. A measurement, never itself a yawn label."""
    points = [image_point(face[index], frame_size) for index in (13, 14, 61, 291)]
    if not all(math.isfinite(v) for point in points for v in point):
        return None
    opening = math.dist(points[0], points[1])
    width = math.dist(points[2], points[3])
    if width < 4:
        return None
    value = opening / width
    return value if 0 <= value <= 2 else None


def crop_region(frame, face, indices, padding=.35, diagnostics=None):
    def mark(reason, **values):
        if diagnostics is not None:
            diagnostics.update(reason=reason, **values)
    if frame is None or not face:
        mark("NO_FACE")
        return None, 0.0
    height, width = frame.shape[:2]
    points = np.asarray([image_point(face[index], (width, height)) for index in indices])
    if not np.isfinite(points).all():
        mark("INVALID_GEOMETRY")
        return None, 0.0
    low, high = points.min(axis=0), points.max(axis=0)
    extent = high - low
    if extent[0] < 16 or extent[1] < 3:
        mark("SMALL_REGION")
        return None, 0.0
    # Keep enough surrounding eye/skin context for a classifier. This technical
    # crop gate is not a claim that a reflected/occluded eye is observable.
    margin = np.maximum(extent * padding, [3, 5])
    first, last = np.floor(low - margin).astype(int), np.ceil(high + margin).astype(int)
    mark("VALID", bounds=[first.tolist(), last.tolist()])
    if first[0] < 0 or first[1] < 0 or last[0] > width or last[1] > height:
        mark("OUTSIDE_FRAME")
        return None, 0.0
    crop = frame[first[1]:last[1], first[0]:last[0]]
    if crop.size == 0:
        mark("EMPTY_REGION")
        return None, 0.0
    sharpness = float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    if sharpness < 1:  # Reject blank crops; semantic visibility is a separate task.
        mark("BLANK")
        return None, sharpness
    return cv2.resize(crop, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_AREA), sharpness


def extract_regions(frame, face):
    details = {"eyes": {}, "mouth": {}}
    eyes, eye_sharpness = crop_region(frame, face, EYE_POINTS, .45, details["eyes"])
    mouth, mouth_sharpness = crop_region(frame, face, MOUTH_POINTS, .25, details["mouth"])
    return {"eyes": eyes, "mouth": mouth, "eye_sharpness": eye_sharpness,
            "mouth_sharpness": mouth_sharpness, "crop_details": details,
            "mar": mouth_aspect_ratio(face, (frame.shape[1], frame.shape[0]))}
