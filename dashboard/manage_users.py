"""Manage dashboard logins (run on the server as ``opc``, same env as server.py).

    python dashboard/manage_users.py sync          # account for every Diretória member
    python dashboard/manage_users.py reset EMAIL   # new password for one member

New passwords are printed once (email<TAB>password) to stdout; only their hash is
stored, and the user must replace it at first login. ``sync`` also removes accounts whose email left the Diretória.
"""

import argparse
import os
import secrets
import string

from auth_store import AuthStore
from directory import Directory
from google.oauth2 import service_account

ALPHABET = string.ascii_letters + string.digits


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip().strip('"')
    if not value:
        raise SystemExit(f"Missing required env var {name}")
    return value


def new_password() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(16))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    reset = sub.add_parser("reset")
    reset.add_argument("email")
    args = parser.parse_args()

    creds = service_account.Credentials.from_service_account_file(
        _env("SHEETS_SERVICE_ACCOUNT_PATH"),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    store = AuthStore(_env("DASHBOARD_DB_PATH"))
    members = Directory(creds, _env("BP_SERVICE_SPREADSHEET_ID")).members()

    if args.cmd == "reset":
        email = args.email.strip().lower()
        if email not in members:
            raise SystemExit(f"{email} is not in the Diretória (BP SERVICE)")
        password = new_password()
        store.set_password(email, password, must_change=True)
        store.delete_sessions(email)
        print(f"{email}\t{password}")
        return

    existing = set(store.emails())
    for email in sorted(set(members) - existing):
        password = new_password()
        store.set_password(email, password, must_change=True)
        print(f"{email}\t{password}")
    for email in sorted(existing - set(members)):
        store.delete_user(email)
        print(f"{email}\tREMOVED")


if __name__ == "__main__":
    main()
