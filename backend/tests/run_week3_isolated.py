"""Run week-3 checks with a disposable secured broker and database, then clean up."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/week3"


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=50)
    if result.returncode:
        raise RuntimeError("Docker test fixture failed: " + result.stderr)
    return result.stdout.strip()


def main():
    suffix = secrets.token_hex(5)
    name, network = "codex-w3-broker-" + suffix, "codex-w3-net-" + suffix
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-w3-broker-") as directory:
        temporary = Path(directory)
        data = temporary / "data"
        data.mkdir()
        env = {**os.environ, "MQTT_HOST": "127.0.0.1", "MQTT_ADMIN_USERNAME": "test-admin",
               "MQTT_ADMIN_PASSWORD": secrets.token_urlsafe(24), "MQTT_USERNAME": "test-backend",
               "MQTT_PASSWORD": secrets.token_urlsafe(24), "AI_MQTT_USERNAME": "vision-01",
               "AI_MQTT_PASSWORD": secrets.token_urlsafe(24), "AI_DEVICE_CODE": "vision-01",
               "W3_DOCKER_TESTS": "1", "W3_TEST_NETWORK": network,
               "W3_TEST_MQTT_DOCKER_HOST": name, "W3_BROKER_SCOPE": "isolated disposable broker",
               "W3_BACKEND_IMAGE": "codex-w3-backend-test:latest",
               "PYTHONIOENCODING": "utf-8"}
        credentials = temporary / "init.env"
        credentials.write_text("\n".join(key + "=" + env[key] for key in
            ("MQTT_ADMIN_USERNAME", "MQTT_ADMIN_PASSWORD")), encoding="utf-8")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        env["MQTT_PORT"] = str(port)
        created_network = False
        try:
            # Rebuild dependencies when requirements change; mounting code into an old image is insufficient.
            build = subprocess.run(["docker", "build", "-t", env["W3_BACKEND_IMAGE"], "-f",
                str(ROOT / "deployment/backend/Dockerfile"), str(ROOT)], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600)
            if build.returncode:
                raise RuntimeError("Test backend image build failed: " + build.stderr[-1500:])
            docker("network", "create", network)
            created_network = True
            docker("run", "--rm", "--env-file", str(credentials),
                "--mount", f"type=bind,source={data},target=/mosquitto/data",
                "--mount", f"type=bind,source={ROOT / 'deployment/mqtt/init.sh'},target=/mosquitto/config/init.sh,readonly",
                "--entrypoint", "/bin/sh", "eclipse-mosquitto:2", "/mosquitto/config/init.sh")
            docker("run", "-d", "--name", name, "--network", network, "-p", f"127.0.0.1:{port}:1883",
                "--mount", f"type=bind,source={data},target=/mosquitto/data",
                "--mount", f"type=bind,source={ROOT / 'deployment/mqtt/mosquitto.conf'},target=/mosquitto/config/mosquitto.conf,readonly",
                "eclipse-mosquitto:2")
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            # Exercise creation and updating existing test roles. No live broker is accessed.
            setup = "import sys; sys.path.insert(0,'backend'); from app.services.mqtt_bootstrap import setup; setup(); setup()"
            subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env=env, check=True, timeout=40)
            run = subprocess.run([sys.executable, "backend/tests/run_week3_integration.py"], cwd=ROOT, env=env)
            acl = subprocess.run([sys.executable, "backend/tests/test_mqtt_security_integration.py", "-v"],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
            (EVIDENCE / "acl-output.txt").write_text(acl.stdout + acl.stderr, encoding="utf-8")
            (EVIDENCE / "acl-results.json").write_text(json.dumps({"executed_at": datetime.now(timezone.utc).isoformat(),
                "exit_code": acl.returncode, "scope": "Isolated real Docker MQTT broker; temporary accounts; production ACL unchanged"}, indent=2), encoding="utf-8")
            return run.returncode or acl.returncode
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            if created_network:
                subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
