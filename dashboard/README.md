# Dashboard CONTAORDEM

Web dashboard for the `CONTAORDEM` sheet, served over HTTPS from the
production server. Only Diretória members can log in.

- `index.html`: the dashboard page (copied from the Claude artifact; data now
  comes from `api/main.xlsx` and `api/vc.xlsx` instead of the Drive connector).
  The header has a user menu (name, email, photo, change password, logout).
- `login.html`: email + password login page.
- `server.py`: stdlib HTTP backend on `127.0.0.1:8090`. Exports both
  spreadsheets as XLSX through the Drive API with the existing Sheets service
  account (`drive.readonly`) and enforces the login.
- `directory.py`: reads the `BP SERVICE` sheet (spreadsheet
  `BP_SERVICE_SPREADSHEET_ID`). Only rows with `DIRETÓRIA = TRUE` and an
  `EMAIL` may log in; `NOME` and `FOTO DO PERFIL` feed the user menu. Checked at
  login and on every request (5 min cache), so unticking `DIRETÓRIA` revokes
  access within minutes.
- `attendance.py`: service attendance from `AppFrequenciaMembresia` (same
  spreadsheet as BP SERVICE), served as counts only at `/api/frequencia` and
  used by the "Frequência nos cultos" block of "Motivos da variação".
- `auth_store.py`: SQLite database (`DASHBOARD_DB_PATH`) with scrypt password
  hashes and session tokens (stored as SHA-256 digests; 12 h sessions).
- `manage_users.py`: creates/resets accounts (see below).
- `tesouraria-dashboard.service`: systemd unit (runs as `opc`; may write only
  to `/home/opc/AppExtrato/data`, where the database lives).
- `Caddyfile`: HTTPS (Let's Encrypt) and security headers in front of the
  backend.

Required env (project `.env`): `SHEETS_SPREADSHEET_ID`,
`VERBO_CAFE_SOURCE_SPREADSHEET_ID`, `SHEETS_SERVICE_ACCOUNT_PATH`,
`BP_SERVICE_SPREADSHEET_ID`, `DASHBOARD_DB_PATH`. The server fails at startup
if any is missing. Optional: `DASHBOARD_ADMIN_EMAILS`,
`DASHBOARD_INITIAL_PASSWORD` (fixed initial password for new/reset accounts;
random when unset).

Profile photos are found in Drive by the file name stored in `FOTO DO PERFIL`;
they only show if the AppSheet images folders are shared (read-only) with the
service account. Otherwise the menu shows the initials.

## Accounts

Run on the server as `opc`, with the same env as the service:

```
sudo systemd-run --quiet --uid=opc --gid=opc --pipe --wait \
  -p EnvironmentFile=/home/opc/AppExtrato/.env -p WorkingDirectory=/home/opc/AppExtrato \
  /home/opc/AppExtrato/venv/bin/python -W ignore dashboard/manage_users.py sync
```

- `sync`: creates an account (random password, printed once) for every
  Diretória member without one, and deletes accounts whose email left the
  Diretória.
- `reset EMAIL`: new password for one member; ends their sessions.

Generated passwords are initial: at first login a popup that cannot be
dismissed forces a new password, and the data endpoints answer 403 until it
is changed. Members can change it again in the user menu (minimum 10
characters).

Admins (`DASHBOARD_ADMIN_EMAILS` in `.env`, comma-separated Diretória emails)
see "Administrador" in the menu and a "Gerir contas" window: every Diretória
member with their account state (no account / initial password / active) and
last login, plus "Criar conta" / "Nova senha", which shows a one-time initial
password. Clicking a name shows that user's history from the `events` table
(kept indefinitely): logins, failed logins, logouts, data loads, period
changes, password changes and admin actions, with time and IP.
Ten failed logins per IP or email block further attempts for 15 minutes.

## Deploy (server `ubuntu@152.67.150.143`)

1. Copy `dashboard/` to `/home/opc/AppExtrato/dashboard/` (owner `opc`) and
   create `/home/opc/AppExtrato/data` (owner `opc`, mode 700).
2. Add `BP_SERVICE_SPREADSHEET_ID` and
   `DASHBOARD_DB_PATH=/home/opc/AppExtrato/data/dashboard.db` to the `.env`.
3. `sudo cp dashboard/tesouraria-dashboard.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now tesouraria-dashboard`
4. Install Caddy (`apt install caddy`), copy `Caddyfile` to
   `/etc/caddy/Caddyfile`. Create `/etc/caddy/dashboard.env` (mode 600) with
   `DASHBOARD_DOMAIN` and add `EnvironmentFile=/etc/caddy/dashboard.env` to the
   caddy unit via `systemctl edit caddy`.
5. Open TCP 80/443: iptables on the instance **and** the VCN Security List in
   the Oracle console.
6. DNS `A` record of the domain pointing to `152.67.150.143`.
7. Create the accounts with `manage_users.py sync`.

Local test: export the required env vars (point `DASHBOARD_DB_PATH` at a
scratch file), create an account with `manage_users.py reset EMAIL`, run
`python dashboard/server.py`, open `http://localhost:8090/`.
