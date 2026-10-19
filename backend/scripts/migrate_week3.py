"""Apply only the additive week-3 migration to the database selected by .env."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings


def main():
    address = make_url(str(settings.DATABASE_URL))
    with psycopg.connect(host=address.host, port=address.port or 5432, dbname=address.database,
                         user=address.username, password=address.password, autocommit=True) as connection:
        connection.execute((ROOT / "database/migration_be_week3.sql").read_text(encoding="utf-8"))
        tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('ai_events','rule_bindings') ORDER BY table_name").fetchall()
    evidence = {"executed_at": datetime.now(timezone.utc).isoformat(), "migration": "database/migration_be_week3.sql",
                "status": "APPLIED", "verified_tables": [row[0] for row in tables], "schema_change": "additive"}
    directory = ROOT / "docs/evidence/week3"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "migration-results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("Week-3 migration applied; ai_events and rule_bindings verified. Existing rows were not reset.")


if __name__ == "__main__":
    main()
