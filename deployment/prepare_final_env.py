"""Create local monitoring secrets without printing values or changing existing credentials."""
from pathlib import Path
import secrets
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]

def main():
    env = ROOT / ".env"
    if not env.is_file():
        raise SystemExit("Create .env from .env.example and configure the existing DB/MQTT first")
    values = dotenv_values(env)
    for key in ("METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD"):
        if not values.get(key):
            value = secrets.token_urlsafe(32)
            set_key(env, key, value)
            values[key] = value
    directory = ROOT / "deployment/monitoring/secrets"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metrics-token").write_text(values["METRICS_TOKEN"], encoding="utf-8")
    print("Local monitoring credentials ready. Values were not printed; .env and secret files stay private.")

if __name__ == "__main__": main()
