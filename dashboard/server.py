"""Read-only HTTP backend for the CONTAORDEM dashboard.

Serves ``index.html`` and streams the treasury and Verbo Café spreadsheets as
XLSX exports via the Drive API, using the existing Sheets service account.
Binds to localhost only; Caddy terminates HTTPS and enforces basic auth.

Required env (same ``.env`` as the automation): SHEETS_SPREADSHEET_ID,
VERBO_CAFE_SOURCE_SPREADSHEET_ID, SHEETS_SERVICE_ACCOUNT_PATH.
Optional: DASHBOARD_PORT (default 8090), DASHBOARD_USERS_PATH (JSON profiles
``{"login": {"name": ..., "email": ..., "role": ...}}`` for ``/api/me``).
Caddy sends the authenticated login in ``X-Dashboard-User``.
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
INDEX = Path(__file__).with_name("index.html")
log = logging.getLogger("dashboard")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip().strip('"')
    if not value:
        raise SystemExit(f"Missing required env var {name}")
    return value


FILES = {
    "/api/main.xlsx": _require("SHEETS_SPREADSHEET_ID"),
    "/api/vc.xlsx": _require("VERBO_CAFE_SOURCE_SPREADSHEET_ID"),
}
_users_path = os.environ.get("DASHBOARD_USERS_PATH", "").strip().strip('"')
USERS: dict[str, dict[str, str]] = (
    json.loads(Path(_users_path).read_text(encoding="utf-8")) if _users_path else {}
)
_creds = service_account.Credentials.from_service_account_file(
    _require("SHEETS_SERVICE_ACCOUNT_PATH"),
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/me":
            login = self.headers.get("X-Dashboard-User", "")
            profile = {"name": login, "email": "", "role": ""} | USERS.get(login, {})
            body = json.dumps({"login": login, **profile}).encode()
            self._send(200, body, "application/json")
            return
        file_id = FILES.get(path)
        if not file_id:
            self._send(404, b"Not found", "text/plain")
            return
        try:
            # httplib2 is not thread-safe, so build a client per request.
            drive = build("drive", "v3", credentials=_creds, cache_discovery=False)
            data = drive.files().export(fileId=file_id, mimeType=XLSX_MIME).execute()
        except Exception:
            log.exception("Drive export failed for %s", path)
            self._send(502, b"Drive export failed", "text/plain")
            return
        self._send(200, data, XLSX_MIME)

    def log_message(self, fmt: str, *args: object) -> None:
        log.info("%s %s", self.address_string(), fmt % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("DASHBOARD_PORT", "8090"))
    log.info("Dashboard listening on 127.0.0.1:%d", port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
