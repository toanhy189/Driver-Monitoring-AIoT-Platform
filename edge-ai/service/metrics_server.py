"""Optional loopback Prometheus exporter for measurements from the camera process."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from config import METRICS_PATH


def render(snapshot):
    lines = []
    for field, name, scale in (("fps", "ai_fps", 1), ("rss_bytes", "ai_process_rss_bytes", 1),
                                ("cpu_process_percent", "ai_process_cpu_ratio", .01)):
        if snapshot.get(field) is not None:
            lines.append(f"{name} {snapshot[field]*scale}")
    for stage, values in snapshot.get("stages", {}).items():
        for key, quantile in (("p50_ms", "0.5"), ("p95_ms", "0.95")):
            if key in values:
                lines.append(f'ai_stage_latency_seconds{{stage="{stage}",quantile="{quantile}"}} {values[key]/1000}')
                if stage == "estimator":
                    lines.append(f'ai_inference_latency_ms{{quantile="{quantile}"}} {values[key]}')
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9108)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_error(404)
                return
            try:
                with METRICS_PATH.open("rb") as source:
                    source.seek(0, 2)
                    source.seek(max(0, source.tell()-65536))
                    lines = source.read().splitlines()
                snapshot = json.loads(lines[-1])
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(snapshot["timestamp"])).total_seconds()
                if not 0 <= age <= 30:
                    raise ValueError("Measurements are stale")
                body = render(snapshot).encode()
            except (OSError, ValueError, KeyError, IndexError):
                self.send_error(503, "Camera measurements unavailable or stale")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
