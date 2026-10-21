"""Export public contracts and source hashes; never export environment secrets."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app
from app.services.mqtt_security import backend_acls, device_acls, vision_acls


def main():
    directory = ROOT / "docs/evidence/week3"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    acl = {"note": "Permission example only, no account passwords", "alert-EXAMPLE": device_acls("alert-EXAMPLE"),
        "backend": backend_acls(), "vision-EXAMPLE": vision_acls("vision-EXAMPLE"),
        "edge-ai": vision_acls("vision-01", legacy=True)}
    (directory / "acl-policy.json").write_text(json.dumps(acl, indent=2), encoding="utf-8")
    paths = [*ROOT.glob("backend/app/**/*.py"), *ROOT.glob("backend/tests/*.py"),
             *ROOT.glob("backend/scripts/*.py"), *ROOT.glob("frontend/src/**/*.js"), *ROOT.glob("frontend/src/**/*.jsx"),
             *ROOT.glob("frontend/tests/*.mjs"), *ROOT.glob("firmware/esp32-alert-node/src/app/*.cpp"),
             *[path for path in ROOT.glob("firmware/esp32-alert-node/include/*.h") if path.name != "network_config.h"],
             ROOT / "deployment/docker-compose.yml", ROOT / "deployment/backend/Dockerfile",
             ROOT / "database/migration_be_week3.sql", ROOT / "database/migration_ai_videos.sql"]
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "note": "Hashes identify current uncommitted workspace; passing tests are recorded in adjacent files",
        "sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)},
        "evidence_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.iterdir())
                            if path.is_file() and path.name != "source-manifest.json"}}
    (directory / "source-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Exported OpenAPI, ACL policy and source manifest to docs/evidence/week3")


if __name__ == "__main__":
    main()
