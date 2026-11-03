"""HTTP backend for the CONTAORDEM dashboard.

Serves the pages and streams the treasury and Verbo Café spreadsheets as XLSX
exports via the Drive API, using the existing Sheets service account. Binds to
localhost only; Caddy terminates HTTPS.

Login: email + password. The email must belong to a BP SERVICE row with
DIRETÓRIA = TRUE (checked at login and on every request, cached a few
minutes); passwords and sessions live in the SQLite file at DASHBOARD_DB_PATH.
Accounts are created with ``manage_users.py``.

Required env (same ``.env`` as the automation): SHEETS_SPREADSHEET_ID,
VERBO_CAFE_SOURCE_SPREADSHEET_ID, SHEETS_SERVICE_ACCOUNT_PATH,
BP_SERVICE_SPREADSHEET_ID, DASHBOARD_DB_PATH.
Optional: DASHBOARD_PORT (default 8090), DASHBOARD_ADMIN_EMAILS (comma-separated
Diretória emails that may manage accounts from the page), DASHBOARD_USER_MIN_YEAR
(first year non-admins see, default 2026), LIVRARIA_SPREADSHEET_ID (AppVerboShop,
for the bookshop P&L card).
"""

import json
import logging
import os
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from attendance import fetch_attendance
from auth_store import SESSION_TTL, AuthStore, generate_password
from bookshop import fetch_bookshop
from cafe import fetch_cafe
from directory import Directory, DirectoryUnavailable
from google.oauth2 import service_account
from googleapiclient.discovery import build
from year_filter import filter_xlsx

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HERE = Path(__file__).parent
PAGES = {"/": "index.html", "/index.html": "index.html", "/login": "login.html"}
MIN_PASSWORD = 10
CLIENT_EVENTS = {"periodo", "gerir_contas", "card", "opcao", "clique"}
MAX_BODY = 4096
MAX_FAILS, FAIL_WINDOW = 10, 15 * 60
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
CREDS = service_account.Credentials.from_service_account_file(
    _require("SHEETS_SERVICE_ACCOUNT_PATH"),
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)
STORE = AuthStore(_require("DASHBOARD_DB_PATH"))
BP_SPREADSHEET_ID = _require("BP_SERVICE_SPREADSHEET_ID")
DIRECTORY = Directory(CREDS, BP_SPREADSHEET_ID)
# AppVerboShop (bookshop purchases/sales); the bookshop card is hidden when unset.
LIVRARIA_SPREADSHEET_ID = os.environ.get("LIVRARIA_SPREADSHEET_ID", "").strip().strip('"')
# Non-admin members only see data from this year on (admins see every year).
USER_MIN_YEAR = os.environ.get("DASHBOARD_USER_MIN_YEAR", "2026").strip().strip('"')
ADMINS = {
    e.strip().lower() for e in os.environ.get("DASHBOARD_ADMIN_EMAILS", "").split(",") if e.strip()
}

# Sheets the page reads from each export; non-admins get only these, without
# rows dated before USER_MIN_YEAR.
USED_SHEETS = {
    "/api/main.xlsx": {
        "CONTAORDEM",
        "T_EXTRATO",
        "DÍZIMOS/OFERTAS",
        "SAÍDAS",
        "CARTÃO",
        "CONSTANTES",
    },
    "/api/vc.xlsx": {"Financeiro", "VC_VENDAS"},
}
# Filtering takes seconds, so keep the result until the file changes in Drive.
_filtered: dict[str, tuple[str, bytes]] = {}
_filtered_lock = threading.Lock()

# Failed logins per client IP and per email (in memory; one process).
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def _blocked(*keys: str) -> bool:
    now = time.time()
    with _fails_lock:
        for k in keys:
            _fails[k] = [t for t in _fails.get(k, []) if now - t < FAIL_WINDOW]
        return any(len(_fails[k]) >= MAX_FAILS for k in keys)


def _fail(*keys: str) -> None:
    with _fails_lock:
        for k in keys:
            _fails.setdefault(k, []).append(time.time())


class Handler(BaseHTTPRequestHandler):
    def _send(
        self, code: int, body: bytes, ctype: str, headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: dict, headers: dict[str, str] | None = None) -> None:
        self._send(code, json.dumps(data).encode(), "application/json", headers)

    def _token(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie["sid"].value if "sid" in cookie else ""

    def _user(self) -> dict[str, str] | None:
        """Profile of the logged-in Diretória member, or None."""
        token = self._token()
        email = STORE.session_email(token) if token else None
        if not email:
            return None
        member = DIRECTORY.get(email)
        if not member:  # removed from the Diretória: end the session
            STORE.delete_session(token)
        return member

    def _client(self) -> str:
        # Caddy sets X-Forwarded-For from the real client address.
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[-1].strip() or self.client_address[0]

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY or "json" not in self.headers.get("Content-Type", ""):
            return {}
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/login":
            self._send(200, (HERE / "login.html").read_bytes(), "text/html; charset=utf-8")
            return
        try:
            user = self._user()
        except DirectoryUnavailable:
            self._send(503, b"Directory unavailable", "text/plain")
            return
        if not user:
            if path in PAGES:
                self._send(303, b"", "text/plain", {"Location": "login"})
            else:
                self._json(401, {"error": "login"})
            return
        if path in PAGES:
            self._send(200, (HERE / PAGES[path]).read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/me":
            must = STORE.must_change(user["email"])
            admin = user["email"] in ADMINS
            min_year = None if admin else USER_MIN_YEAR
            self._json(
                200,
                {**self._public(user), "must_change": must, "admin": admin, "min_year": min_year},
            )
        elif STORE.must_change(user["email"]):
            # Initial password: no data until it has been replaced.
            self._json(403, {"error": "change_password"})
        elif path == "/api/photo":
            self._photo(user["email"])
        elif path == "/api/admin/users" and user["email"] in ADMINS:
            self._admin_users()
        elif path == "/api/admin/events" and user["email"] in ADMINS:
            email = parse_qs(urlsplit(self.path).query).get("email", [""])[0]
            self._json(200, {"events": STORE.events(email)})
        elif path == "/api/livraria":
            self._livraria(admin=user["email"] in ADMINS)
        elif path == "/api/cafe":
            self._cafe(admin=user["email"] in ADMINS)
        elif path == "/api/frequencia":
            self._frequencia(admin=user["email"] in ADMINS)
        elif path in FILES:
            if path == "/api/main.xlsx":  # one per page load / "Atualizar"
                self._audit(user["email"], "dados")
            self._export(path, admin=user["email"] in ADMINS)
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._body()
        try:
            if path == "/api/login":
                self._login(body)
            elif path == "/api/logout":
                if self._token():
                    email = STORE.session_email(self._token())
                    if email:
                        self._audit(email, "logout")
                    STORE.delete_session(self._token())
                self._json(200, {}, {"Set-Cookie": "sid=; Max-Age=0; Path=/; HttpOnly; Secure"})
            elif path == "/api/password":
                self._change_password(body)
            elif path == "/api/admin/reset":
                self._admin_reset(body)
            elif path == "/api/event":
                self._client_event(body)
            else:
                self._send(404, b"Not found", "text/plain")
        except DirectoryUnavailable:
            self._json(503, {"error": "Diretório indisponível. Tente mais tarde."})

    def _login(self, body: dict) -> None:
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        ip_key, email_key = f"ip:{self._client()}", f"email:{email}"
        if _blocked(ip_key, email_key):
            self._json(429, {"error": "Demasiadas tentativas. Tente daqui a 15 minutos."})
            return
        # Same message whatever failed, so it does not reveal who has access.
        if not (email and DIRECTORY.get(email) and STORE.check_password(email, password)):
            _fail(ip_key, email_key)
            log.warning("Failed login from %s", self._client())
            if email and DIRECTORY.get(email):  # only members, so bots cannot fill the log
                self._audit(email, "login_falhado")
            self._json(401, {"error": "Email ou senha inválidos."})
            return
        token = STORE.create_session(email)
        log.info("Login ok from %s", self._client())
        self._audit(email, "login")
        cookie = f"sid={token}; Max-Age={SESSION_TTL}; Path=/; HttpOnly; Secure; SameSite=Strict"
        self._json(200, {}, {"Set-Cookie": cookie})

    def _change_password(self, body: dict) -> None:
        user = self._user()
        if not user:
            self._json(401, {"error": "login"})
            return
        new = str(body.get("new", ""))
        # First login: the session was just opened with the initial password.
        must = STORE.must_change(user["email"])
        if not must and not STORE.check_password(user["email"], str(body.get("current", ""))):
            self._json(400, {"error": "A senha atual está errada."})
        elif len(new) < MIN_PASSWORD:
            self._json(400, {"error": f"A nova senha precisa de {MIN_PASSWORD} caracteres."})
        elif must and STORE.check_password(user["email"], new):
            self._json(400, {"error": "A nova senha tem de ser diferente da inicial."})
        else:
            STORE.set_password(user["email"], new)
            STORE.delete_sessions(user["email"], keep_token=self._token())
            self._audit(user["email"], "senha_inicial_trocada" if must else "senha_alterada")
            self._json(200, {})

    def _audit(self, email: str, action: str, detail: str = "") -> None:
        try:
            STORE.log_event(email, action, detail, self._client())
        except Exception:  # auditing must never break the request
            log.exception("Audit write failed")

    def _client_event(self, body: dict) -> None:
        """Page actions reported by the browser (whitelisted, logged-in users only)."""
        user = self._user()
        action = str(body.get("action", ""))
        if not user or action not in CLIENT_EVENTS:
            self._json(400, {})
            return
        self._audit(user["email"], action, str(body.get("detail", "")))
        self._json(200, {})

    @staticmethod
    def _public(member: dict[str, str]) -> dict[str, str]:
        return {"name": member["name"], "email": member["email"]}

    def _admin_users(self) -> None:
        """Diretória members with their account state, for the admin page."""
        accounts = STORE.accounts()
        users = [
            {**self._public(m), **accounts.get(email, {}), "has_account": email in accounts}
            for email, m in sorted(DIRECTORY.members().items(), key=lambda kv: kv[1]["name"])
        ]
        self._json(200, {"users": users})

    def _admin_reset(self, body: dict) -> None:
        """Create or reset a member's account; the initial password is shown once."""
        user = self._user()
        if not user or user["email"] not in ADMINS or STORE.must_change(user["email"]):
            self._json(403, {"error": "Sem permissão."})
            return
        email = str(body.get("email", "")).strip().lower()
        if not DIRECTORY.get(email):
            self._json(400, {"error": "Este email não está na Diretória."})
            return
        password = generate_password()
        STORE.set_password(email, password, must_change=True)
        STORE.delete_sessions(email, keep_token=self._token() if email == user["email"] else None)
        log.info("Admin reset password for an account")
        self._audit(user["email"], "admin_nova_senha", email)
        self._audit(email, "senha_reposta", user["email"])
        self._json(200, {"email": email, "password": password})

    def _photo(self, email: str) -> None:
        try:
            found = DIRECTORY.photo(email)
        except Exception:
            log.exception("Profile photo lookup failed")
            found = None
        if found:
            self._send(200, found[0], found[1])
        else:
            self._send(404, b"No photo", "text/plain")

    def _livraria(self, admin: bool) -> None:
        if not LIVRARIA_SPREADSHEET_ID:
            self._send(404, b"Bookshop not configured", "text/plain")
            return
        try:
            min_year = None if admin else int(USER_MIN_YEAR)
            data = fetch_bookshop(CREDS, LIVRARIA_SPREADSHEET_ID, min_year)
        except Exception:
            log.exception("Bookshop read failed")
            self._send(502, b"Bookshop read failed", "text/plain")
            return
        self._json(200, data)

    def _cafe(self, admin: bool) -> None:
        try:
            min_year = None if admin else int(USER_MIN_YEAR)
            data = fetch_cafe(CREDS, FILES["/api/vc.xlsx"], min_year)
        except Exception:
            log.exception("Cafe read failed")
            self._send(502, b"Cafe read failed", "text/plain")
            return
        self._json(200, data)

    def _frequencia(self, admin: bool) -> None:
        try:
            data = fetch_attendance(CREDS, BP_SPREADSHEET_ID)
            if not admin:
                data = [x for x in data if x["date"][:4] >= USER_MIN_YEAR]
        except Exception:
            log.exception("Attendance read failed")
            self._send(502, b"Attendance read failed", "text/plain")
            return
        self._json(200, {"cultos": data})

    def _export(self, path: str, admin: bool) -> None:
        try:
            # httplib2 is not thread-safe, so build a client per request.
            drive = build("drive", "v3", credentials=CREDS, cache_discovery=False)
            if admin:
                data = drive.files().export(fileId=FILES[path], mimeType=XLSX_MIME).execute()
            else:
                data = self._filtered_export(drive, path)
        except Exception:
            log.exception("Drive export failed for %s", path)
            self._send(502, b"Drive export failed", "text/plain")
            return
        self._send(200, data, XLSX_MIME)

    @staticmethod
    def _filtered_export(drive: object, path: str) -> bytes:
        """Export for non-admins: used sheets only, from USER_MIN_YEAR on (cached per version)."""
        files = drive.files()  # type: ignore[attr-defined]
        version = files.get(fileId=FILES[path], fields="modifiedTime").execute()["modifiedTime"]
        with _filtered_lock:
            cached = _filtered.get(path)
            if cached and cached[0] == version:
                return cached[1]
            raw = files.export(fileId=FILES[path], mimeType=XLSX_MIME).execute()
            data = filter_xlsx(raw, int(USER_MIN_YEAR), USED_SHEETS[path])
            _filtered[path] = (version, data)
            return data

    def log_message(self, fmt: str, *args: object) -> None:
        log.info("%s %s", self._client(), fmt % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("DASHBOARD_PORT", "8090"))
    log.info("Dashboard listening on 127.0.0.1:%d", port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
