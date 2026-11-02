# Dashboard CONTAORDEM

Read-only web dashboard for the `CONTAORDEM` sheet, served over HTTPS from the
production server.

- `index.html`: the dashboard page (copied from the Claude artifact; data now
  comes from `api/main.xlsx` and `api/vc.xlsx` instead of the Drive connector).
- `server.py`: stdlib HTTP backend on `127.0.0.1:8090`. Exports both
  spreadsheets as XLSX through the Drive API with the existing Sheets service
  account (`drive.readonly`). Reads `SHEETS_SPREADSHEET_ID`,
  `VERBO_CAFE_SOURCE_SPREADSHEET_ID`, `SHEETS_SERVICE_ACCOUNT_PATH` from the
  project `.env`; fails at startup if any is missing.
- `tesouraria-dashboard.service`: systemd unit (runs as `opc`).
- `Caddyfile`: HTTPS (Let's Encrypt) + basic auth in front of the backend.

## Deploy (server `ubuntu@152.67.150.143`)

1. Copy `dashboard/` to `/home/opc/AppExtrato/dashboard/` (owner `opc`).
2. `sudo cp dashboard/tesouraria-dashboard.service /etc/systemd/system/ && sudo systemctl enable --now tesouraria-dashboard`
3. Install Caddy (`apt install caddy`), copy `Caddyfile` to `/etc/caddy/Caddyfile`.
4. Create `/etc/caddy/dashboard.env` (mode 600) with `DASHBOARD_DOMAIN` and
   add `EnvironmentFile=/etc/caddy/dashboard.env` to the caddy unit via
   `systemctl edit caddy`. Logins go in `/etc/caddy/dashboard-users.caddy`
   (`root:caddy`, mode 640), one `login hash` per line, hash from
   `printf '%s
' "$PW" | caddy hash-password`.
   Profiles for the header user menu (`/api/me`) go in a JSON file
   `{"login": {"name": ..., "email": ..., "role": ...}}` pointed to by
   `DASHBOARD_USERS_PATH` in the project `.env` (server copy:
   `/home/opc/AppExtrato/credentials/dashboard-users.json`, mode 600).
   To add a person: append the login to `dashboard-users.caddy`, add the
   profile to the JSON, `systemctl reload caddy` and
   `systemctl restart tesouraria-dashboard`.
5. Open TCP 80/443: iptables on the instance **and** the VCN Security List in
   the Oracle console.
6. DNS `A` record of the domain pointing to `152.67.150.143`.

Local test: export the three env vars, run `python dashboard/server.py`, open
`http://127.0.0.1:8090/`.
