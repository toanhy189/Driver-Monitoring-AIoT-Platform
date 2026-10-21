"""Run HTTP/WS/PostgreSQL/MQTT checks in a disposable database, then remove it."""

import os
from pathlib import Path
import secrets
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings


def main():
    base = make_url(str(settings.DATABASE_URL))
    database = "codex_w3_" + secrets.token_hex(6)
    target = base.set(database=database)
    connect = dict(host=base.host, port=base.port or 5432, user=base.username,
                   password=base.password, dbname=base.database, connect_timeout=5)
    evidence = ROOT / "docs/evidence/week3"
    evidence.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(**connect, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            with psycopg.connect(**{**connect, "dbname": database}, autocommit=True) as test:
                for path in ("database/create.sql", "database/migration_fe_be_week2.sql",
                             "database/migration_be_week3.sql", "database/migration_be_week3.sql",
                             "database/migration_ai_videos.sql", "database/migration_ai_videos.sql"):
                    test.execute((ROOT / path).read_text(encoding="utf-8"))
            env = {**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False),
                   "W3_INTEGRATION": "1", "RULE_ENGINE_ENABLED": "true", "SQL_ECHO": "false",
                   "ENABLE_BACKGROUND_TASKS": "false", "ENABLE_MQTT_CONSUMER": "true",
                   "W3_EVIDENCE": str(evidence), "PYTHONIOENCODING": "utf-8"}
            result = subprocess.run([sys.executable, "backend/tests/test_week3_integration.py"],
                                    cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True)
            output = result.stdout + result.stderr
            (evidence / "integration-output.txt").write_text(output, encoding="utf-8")
            print(output)
            return result.returncode
        finally:
            # Only this newly created database may be removed. No application DB is reset.
            if not database.startswith("codex_w3_"):
                raise RuntimeError("Unexpected test database name")
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


if __name__ == "__main__":
    raise SystemExit(main())
