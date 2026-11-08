
from datetime import datetime, timezone


def current_timestamp():
    """Lấy thời gian UTC theo định dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat()

def draw_text(frame, text, y, color=(0, 255, 0)):
    # MQTT's timestamp helper must also work without the optional camera stack.
    import cv2
    cv2.putText(
        frame,
        str(text),
        (15, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        1,
        cv2.LINE_AA
    )
    return y + 25
