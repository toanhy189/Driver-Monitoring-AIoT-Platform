"""Write reproducible UTF-8 verification output without reading application data."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/week3"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    node = shutil.which("node")
    commands = [
        ("unit", [sys.executable, "-m", "unittest", "discover", "-s", "backend/tests", "-v"], ROOT),
        ("frontend-tests", [node, "--test", *[str(path) for path in sorted((ROOT / "frontend/tests").glob("*.test.mjs"))]], ROOT),
        ("frontend-build", [node, "node_modules/vite/bin/vite.js", "build"], ROOT / "frontend"),
    ]
    if "--firmware" in sys.argv:
        pio = Path.home() / ".platformio/penv/Scripts/pio.exe"
        commands.append(("firmware-build", [str(pio), "run", "-d", "firmware/esp32-alert-node", "-e", "development"], ROOT))
    results = []
    for name, command, cwd in commands:
        run = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True)
        (EVIDENCE / f"{name}-output.txt").write_text(run.stdout + run.stderr, encoding="utf-8")
        results.append({"check": name, "exit_code": run.returncode})
        print(name + ": " + ("PASS" if run.returncode == 0 else "FAIL"))
    (EVIDENCE / "verification-results.json").write_text(json.dumps({
        "executed_at": datetime.now(timezone.utc).isoformat(), "checks": results,
    }, indent=2), encoding="utf-8")
    return 0 if all(row["exit_code"] == 0 for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
