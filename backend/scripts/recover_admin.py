"""Recover the sole administrator from a trusted server terminal.

Example: python backend/scripts/recover_admin.py --username admin_demo --apply
No credentials are accepted on the command line or printed to logs.
"""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session, select
from app.core.db import engine
from app.core.security import get_password_hash
from app.models.user import User
from app.services.audit_service import log_action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with Session(engine) as db:
        admins = db.exec(select(User).where(User.role.in_(["Admin", "ADMIN"])).with_for_update()).all()
        target = db.exec(select(User).where(User.username == args.username).with_for_update()).first()
        if len(admins) != 1 or target is None or admins[0].id != target.id:
            raise SystemExit("Recovery requires the existing sole administrator. No account was changed.")
        if not args.apply:
            print("Administrator exists. Add --apply to reset its password and reactivate it.")
            return
        password = getpass("New administrator password: ")
        if not 8 <= len(password) <= 128 or password != getpass("Confirm password: "):
            raise SystemExit("Password length or confirmation is invalid. No account was changed.")
        target.hash_password = get_password_hash(password)
        target.status = "ACTIVE"
        target.session_version += 1
        db.add(target)
        log_action(db, target.id, "RECOVER_ADMIN", "User", str(target.id), {"source": "server_terminal"})
        db.commit()
    print("Administrator recovered. Previous HTTP sessions are invalid; sign in again.")


if __name__ == "__main__":
    main()
