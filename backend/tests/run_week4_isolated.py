"""Run only new week-4 paths with disposable broker/PostgreSQL containers."""
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
OUTPUT = ROOT/"edge-ai/ml-runs/week4-completion-20261107"


def docker(*args, input=None):
    result = subprocess.run(["docker", *args], input=input, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    return result.stdout.strip()


def port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def main():
    suffix = secrets.token_hex(6)
    network = "codex-w4-net-"+suffix
    postgres, broker = "codex-w4-pg-"+suffix, "codex-w4-mqtt-"+suffix
    database = "codex_w3_policy_"+suffix  # Existing test fixture requires this disposable prefix.
    db_port, mqtt_port = port(), port()
    password = secrets.token_urlsafe(24)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    made_network = False
    with tempfile.TemporaryDirectory(prefix="codex-w4-") as directory:
        temp = Path(directory).resolve()
        assert temp.is_relative_to(Path(tempfile.gettempdir()).resolve()) and temp.name.startswith("codex-w4-")
        data = temp/"mqtt-data"
        data.mkdir()
        env = {**os.environ, "DATABASE_URL":f"postgresql+psycopg://w4_test:{password}@127.0.0.1:{db_port}/{database}",
            "SECRET_KEY":secrets.token_urlsafe(32), "MQTT_HOST":"127.0.0.1", "MQTT_PORT":str(mqtt_port),
            "MQTT_ADMIN_USERNAME":"test-admin", "MQTT_ADMIN_PASSWORD":secrets.token_urlsafe(24),
            "MQTT_USERNAME":"test-backend", "MQTT_PASSWORD":secrets.token_urlsafe(24),
            "AI_DEVICE_CODE":"vision-test", "AI_MQTT_USERNAME":"vision-test", "AI_MQTT_PASSWORD":secrets.token_urlsafe(24),
            "AI_VIDEO_DIR":str(temp/"videos"), "RULE_ENGINE_ENABLED":"true", "W3_INTEGRATION":"1", "W4_LIVE":"1",
            "ENABLE_BACKGROUND_TASKS":"false", "ENABLE_MQTT_CONSUMER":"true", "SQL_ECHO":"false",
            "PYTHONIOENCODING":"utf-8", "PYTHONUTF8":"1"}
        (temp/"postgres.env").write_text(f"POSTGRES_USER=w4_test\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={database}\n")
        (temp/"mqtt.env").write_text("\n".join(key+"="+env[key] for key in ("MQTT_ADMIN_USERNAME","MQTT_ADMIN_PASSWORD")))
        try:
            docker("network", "create", network)
            made_network = True
            docker("run", "-d", "--name", postgres, "--network", network, "--env-file", str(temp/"postgres.env"),
                   "-p", f"127.0.0.1:{db_port}:5432", "postgres:16")
            for _ in range(50):
                ready = subprocess.run(["docker", "exec", postgres, "pg_isready", "-U", "w4_test", "-d", database],
                                       capture_output=True, timeout=5)
                if ready.returncode == 0:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError("Disposable PostgreSQL did not become ready")
            scripts = ("create.sql", "migration_fe_be_week2.sql", "migration_be_week3.sql",
                       "migration_ai_videos.sql", "migration_ai_policy_v1.sql")
            sql = "\n".join((ROOT/"database"/name).read_text(encoding="utf-8") for name in scripts)
            docker("exec", "-i", postgres, "psql", "-U", "w4_test", "-d", database, "-v", "ON_ERROR_STOP=1", input=sql)
            docker("run", "--rm", "--env-file", str(temp/"mqtt.env"),
                "--mount", f"type=bind,source={data},target=/mosquitto/data",
                "--mount", f"type=bind,source={ROOT/'deployment/mqtt/init.sh'},target=/mosquitto/config/init.sh,readonly",
                "--entrypoint", "/bin/sh", "eclipse-mosquitto:2", "/mosquitto/config/init.sh")
            docker("run", "-d", "--name", broker, "--network", network, "-p", f"127.0.0.1:{mqtt_port}:1883",
                "--mount", f"type=bind,source={data},target=/mosquitto/data",
                "--mount", f"type=bind,source={ROOT/'deployment/mqtt/mosquitto.conf'},target=/mosquitto/config/mosquitto.conf,readonly",
                "eclipse-mosquitto:2")
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1",mqtt_port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            setup = subprocess.run([sys.executable,"-c",
                "import sys; sys.path.insert(0,'backend'); from app.services.mqtt_bootstrap import setup; setup()"],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=40)
            if setup.returncode:
                raise RuntimeError("Private broker setup failed: "+setup.stderr[-1500:])
            result = subprocess.run([sys.executable,"backend/tests/test_week4_live.py","-v"],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            (OUTPUT/"live-integration.log").write_text(result.stdout+result.stderr,encoding="utf-8")
            (OUTPUT/"live-integration.json").write_text(json.dumps({"exit_code":result.returncode,
                "scope":"Disposable real PostgreSQL + authenticated MQTT + HTTP; virtual ESP32; synthetic MP4",
                "production_database_modified":False, "physical_outputs_used":False,
                "cases":3, "full_old_suite_rerun":False},indent=2),encoding="utf-8")
            print((result.stdout+result.stderr)[-3500:])
            return result.returncode
        finally:
            for name in (broker, postgres):
                assert name.startswith("codex-w4-") and name.endswith(suffix)
                subprocess.run(["docker","rm","-f","-v",name],capture_output=True,timeout=30)
            if made_network:
                subprocess.run(["docker","network","rm",network],capture_output=True,timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
