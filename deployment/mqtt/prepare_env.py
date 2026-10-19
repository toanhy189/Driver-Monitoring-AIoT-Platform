"""Add fresh MQTT secrets to the ignored project .env without printing them."""

import secrets
from pathlib import Path


root = Path(__file__).resolve().parents[2]
env_path = root / ".env"
if not env_path.exists():
    raise SystemExit("Create .env from .env.example first")

content = env_path.read_text(encoding="utf-8-sig")
existing = {}
for line in content.splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        existing[key.strip()] = value.strip()

required = {
    "MQTT_ADMIN_USERNAME": "admin",
    "MQTT_ADMIN_PASSWORD": secrets.token_urlsafe(32),
    "MQTT_USERNAME": "backend",
    "MQTT_PASSWORD": secrets.token_urlsafe(32),
    "AI_MQTT_USERNAME": "vision-01",
    "AI_MQTT_PASSWORD": secrets.token_urlsafe(32),
}
missing = {key for key in required if not existing.get(key)}
if missing:
    updated = []
    found = set()
    for line in content.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in missing:
            line = f"{key}={required[key]}"
            found.add(key)
        updated.append(line)
    if missing - found:
        updated.append("")
        updated.append("# MQTT broker accounts (private; do not commit)")
        updated.extend(f"{key}={required[key]}" for key in required if key in missing - found)
    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
print("MQTT variables are ready in the ignored .env file")
