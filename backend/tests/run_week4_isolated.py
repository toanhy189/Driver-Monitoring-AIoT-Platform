"""Run only new week-4 paths with disposable broker/PostgreSQL containers."""
import json
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(os.getenv("W4_OUTPUT", str(ROOT/"edge-ai/ml-runs/merge-main-20261108")))


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression", action="store_true",
                        help="Also run existing W3/W4 HTTP and permission cases on the disposable services")
    parser.add_argument("--restart-only", action="store_true",
                        help="Run only the previously skipped disposable Docker restart case; build deployment-backend first")
    args = parser.parse_args()
    suffix = secrets.token_hex(6)
    network = "codex-w4-net-"+suffix
    postgres, broker = "codex-w4-pg-"+suffix, "codex-w3-broker-policy-"+suffix
    volume = "codex-w4-mqtt-data-"+suffix
    database = "codex_w3_policy_"+suffix  # Existing test fixture requires this disposable prefix.
    db_port, mqtt_port = port(), port()
    password = secrets.token_urlsafe(24)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    made_network = False
    made_volume = False
    with tempfile.TemporaryDirectory(prefix="codex-w4-") as directory:
        temp = Path(directory).resolve()
        assert temp.is_relative_to(Path(tempfile.gettempdir()).resolve()) and temp.name.startswith("codex-w4-")
        env = {**os.environ, "DATABASE_URL":f"postgresql+psycopg://w4_test:{password}@127.0.0.1:{db_port}/{database}",
            "SECRET_KEY":secrets.token_urlsafe(32), "MQTT_HOST":"127.0.0.1", "MQTT_PORT":str(mqtt_port),
            "MQTT_ADMIN_USERNAME":"test-admin", "MQTT_ADMIN_PASSWORD":secrets.token_urlsafe(24),
            "MQTT_USERNAME":"test-backend", "MQTT_PASSWORD":secrets.token_urlsafe(24),
            "AI_DEVICE_CODE":"vision-test", "AI_MQTT_USERNAME":"vision-test", "AI_MQTT_PASSWORD":secrets.token_urlsafe(24),
            "AI_VIDEO_DIR":str(temp/"videos"), "RULE_ENGINE_ENABLED":"true", "W3_INTEGRATION":"1", "W4_LIVE":"1",
            "W3_BROKER_SCOPE":"isolated disposable broker", "W3_TEST_MQTT_DOCKER_HOST":broker,
            "W3_EVIDENCE":str(OUTPUT), "W4_EVIDENCE":str(OUTPUT),
            "AI_QUEUE_DB":str(temp/"queue.db"), "AI_EVENT_AUDIT_PATH":str(temp/"events.jsonl"),
            "ENABLE_BACKGROUND_TASKS":"false", "ENABLE_MQTT_CONSUMER":"true", "SQL_ECHO":"false",
            "PYTHONIOENCODING":"utf-8", "PYTHONUTF8":"1"}
        if args.restart_only:
            env.update({"W3_DOCKER_TESTS":"1", "W3_TEST_POSTGRES_HOST":postgres,
                        "W3_TEST_NETWORK":network, "W3_BACKEND_IMAGE":os.getenv("W3_BACKEND_IMAGE","deployment-backend:latest")})
        (temp/"postgres.env").write_text(f"POSTGRES_USER=w4_test\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={database}\n")
        (temp/"mqtt.env").write_text("\n".join(key+"="+env[key] for key in ("MQTT_ADMIN_USERNAME","MQTT_ADMIN_PASSWORD")))
        try:
            docker("network", "create", network)
            made_network = True
            docker("volume", "create", volume)
            made_volume = True
            docker("run", "-d", "--name", postgres, "--network", network, "--env-file", str(temp/"postgres.env"),
                   "-p", f"127.0.0.1:{db_port}:5432", "postgres:16")
            for _ in range(50):
                # The image briefly starts a Unix-socket-only init server; wait
                # for the final TCP server rather than racing its shutdown.
                ready = subprocess.run(["docker", "exec", postgres, "pg_isready", "-h", "127.0.0.1", "-U", "w4_test", "-d", database],
                                       capture_output=True, timeout=5)
                if ready.returncode == 0:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError("Disposable PostgreSQL did not become ready")
            scripts = ("create.sql", "old/migration_be_week3.sql",
                       "old/migration_ai_videos.sql", "migration_ai_policy_v1.sql", "migration_ai_policy_v1.sql",
                       "migration_final_core.sql", "migration_final_core.sql")
            sql = "\n".join((ROOT/"database"/name).read_text(encoding="utf-8") for name in scripts)
            docker("exec", "-i", postgres, "psql", "-U", "w4_test", "-d", database, "-v", "ON_ERROR_STOP=1", input=sql)
            docker("run", "--rm", "--env-file", str(temp/"mqtt.env"),
                "--mount", f"type=volume,source={volume},target=/mosquitto/data",
                "--mount", f"type=bind,source={ROOT/'deployment/mqtt/init.sh'},target=/mosquitto/config/init.sh,readonly",
                "--entrypoint", "/bin/sh", "eclipse-mosquitto:2", "/mosquitto/config/init.sh")
            docker("run", "-d", "--name", broker, "--network", network, "-p", f"127.0.0.1:{mqtt_port}:1883",
                "--mount", f"type=volume,source={volume},target=/mosquitto/data",
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
            if args.restart_only:
                code = ("import sys,unittest;sys.path.insert(0,'backend/tests');"
                        "suite=unittest.defaultTestLoader.loadTestsFromName('test_week3_integration.Week3Integration.test_12_docker_restart_http_websocket_and_persistence');"
                        "r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not r.wasSuccessful())")
                result=subprocess.run([sys.executable,"-c",code],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",timeout=180)
                (OUTPUT/"restart-only.log").write_text(result.stdout+result.stderr,encoding="utf-8")
                (OUTPUT/"restart-only.json").write_text(json.dumps({"pass":result.returncode==0,"cases":1,
                    "scope":"Disposable Docker backend restart with real PostgreSQL/MQTT and WebSocket; no production containers restarted"},indent=2),encoding="utf-8")
                print((result.stdout+result.stderr)[-4000:])
                return result.returncode
            result = subprocess.run([sys.executable,"backend/tests/test_week4_live.py","-v"],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            (OUTPUT/"live-integration.log").write_text(result.stdout+result.stderr,encoding="utf-8")
            (OUTPUT/"live-integration.json").write_text(json.dumps({"exit_code":result.returncode,
                "scope":"Disposable real PostgreSQL + authenticated MQTT + HTTP; virtual ESP32; synthetic MP4",
                "production_database_modified":False, "physical_outputs_used":False,
                "cases":3, "full_old_suite_rerun":args.regression},indent=2),encoding="utf-8")
            print((result.stdout+result.stderr)[-3500:])
            exit_code = result.returncode
            if args.regression:
                env["W4_INTEGRATION"] = "1"
                regression = subprocess.run([sys.executable, "-m", "unittest", "discover",
                    "-s", "backend/tests", "-p", "test_week[34]_integration.py", "-v"],
                    cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
                (OUTPUT/"main-regression.log").write_text(regression.stdout+regression.stderr, encoding="utf-8")
                print((regression.stdout+regression.stderr)[-5500:])
                exit_code = exit_code or regression.returncode
                final_core = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests",
                    "-p", "test_final_core.py", "-v"], cwd=ROOT, env=env, capture_output=True,
                    text=True, encoding="utf-8", timeout=120)
                (OUTPUT/"final-core.log").write_text(final_core.stdout+final_core.stderr, encoding="utf-8")
                print((final_core.stdout+final_core.stderr)[-3000:])
                exit_code = exit_code or final_core.returncode
                (OUTPUT/"regression-summary.json").write_text(json.dumps({
                    "policy_exit_code":result.returncode,
                    "existing_regression_exit_code":regression.returncode,
                    "final_core_exit_code":final_core.returncode,
                    "scope":"Disposable real PostgreSQL and MQTT; virtual ESP32; no production data or physical outputs",
                    "pass":exit_code==0},indent=2),encoding="utf-8")
            return exit_code
        finally:
            for name in (broker, postgres):
                assert name in (broker, postgres) and name.endswith(suffix)
                subprocess.run(["docker","rm","-f","-v",name],capture_output=True,timeout=30)
            if made_network:
                subprocess.run(["docker","network","rm",network],capture_output=True,timeout=30)
            if made_volume:
                assert volume.startswith("codex-w4-mqtt-data-") and volume.endswith(suffix)
                docker("volume","rm",volume)


if __name__ == "__main__":
    raise SystemExit(main())
