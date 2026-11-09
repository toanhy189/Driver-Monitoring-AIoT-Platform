"""Run link-management checks on a new PostgreSQL container, then remove only it.

No MQTT, application containers, production database or physical outputs are used.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    suffix = secrets.token_hex(6)
    name = "codex-rule-binding-pg-" + suffix
    database = "codex_rule_binding_" + suffix
    password = secrets.token_urlsafe(24)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="codex-rule-binding-") as directory:
        env_file = Path(directory) / "postgres.env"
        env_file.write_text(f"POSTGRES_USER=rule_test\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={database}\n", encoding="utf-8")
        try:
            subprocess.run(["docker", "run", "-d", "--name", name, "--env-file", str(env_file),
                "-p", f"127.0.0.1:{port}:5432", "postgres:16"], capture_output=True, check=True, timeout=60)
            for _ in range(100):
                probe = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "rule_test", "-d", database],
                    capture_output=True, timeout=5)
                if probe.returncode == 0:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError("Disposable PostgreSQL did not start")
            env = {**os.environ, "RULE_BINDING_TEST_POSTGRES":
                   f"postgresql+psycopg://rule_test:{password}@127.0.0.1:{port}/{database}"}
            return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests",
                "-p", "test_rule_binding_postgres.py", "-v"], cwd=ROOT, env=env, timeout=120).returncode
        finally:
            assert name.startswith("codex-rule-binding-pg-") and name.endswith(suffix)
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
