"""Exercise the current Edge AI payload builders, SQLite and MQTT without a camera."""

import ast
import json
import logging
from pathlib import Path
import socket
import sys
import time
import uuid
from unittest.mock import patch


EDGE = Path(__file__).resolve().parents[2] / "edge-ai"


def load_builders(config, queue):
    # Execute the actual producer functions; skip OpenCV/MediaPipe and the camera main loop.
    source = ast.parse((EDGE / "main2.py").read_text(encoding="utf-8"))
    names = {"send_message", "current_timestamp", "publish_event", "publish_telemetry", "check_threshold_events"}
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    from datetime import datetime, timezone
    scope = {"json": json, "uuid": uuid, "time": time, "datetime": datetime, "timezone": timezone,
             "logger": logging.getLogger(__name__), "add_to_queue": queue.add_to_queue,
             **{name: getattr(config, name) for name in ("DEVICE_CODE", "MODEL_VERSION", "EVENT_TOPIC", "TELEMETRY_TOPIC")}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(EDGE / "main2.py"), "exec"), scope)
    return scope


def main():
    sys.path.insert(0, str(EDGE))
    import config
    import edge_queue
    import mqtt_client

    if "codex-edge-" not in str(config.DB_PATH):
        raise RuntimeError("Probe requires an isolated codex-edge- SQLite path")
    assert edge_queue.init_db()
    builders = load_builders(config, edge_queue)
    sink = type("QueueSink", (), {"notify_queue": lambda self: None})()
    state = {"confirmed_state": "DROWSY", "candidate_state": "DROWSY", "event_sequence": 0,
             "threshold_seconds": {"DROWSY": 3.0, "DISTRACTED": 3.0},
             "threshold_since": {"DROWSY": time.monotonic() - 3.2, "DISTRACTED": None},
             "threshold_event_sent": {"DROWSY": False, "DISTRACTED": False}}
    builders["publish_telemetry"](sink, state, False, None, None, None, None)
    for event in builders["check_threshold_events"](state, config.DEVICE_CODE):
        builders["publish_event"](sink, event)
    before = edge_queue.get_queue()
    assert len(before) == 2

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        unavailable_port = reservation.getsockname()[1]
    with patch.object(mqtt_client, "MQTT_PORT", unavailable_port):
        offline = mqtt_client.MQTTClient()
        time.sleep(0.3)
        offline.close()
    assert len(edge_queue.get_queue()) == 2

    client = mqtt_client.MQTTClient()
    try:
        deadline = time.monotonic() + 15
        while edge_queue.get_queue() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert edge_queue.get_queue() == [], "SQLite must remain until BE sends SAVED"
    finally:
        client.close()
    assert not client.worker.is_alive()
    print(json.dumps({"probe": "PASS", "queued_before": len(before), "pending_after_storage_ack": 0,
                      "builder_source": "edge-ai/main2.py", "camera_opened": False}))


if __name__ == "__main__":
    main()
