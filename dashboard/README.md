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
- `year_filter.py`: for non-admins the server removes rows dated before
  `DASHBOARD_USER_MIN_YEAR` and the sheets the page does not read from both
  XLSX exports (and older attendance), so earlier years never reach their
  browser. The filtered file is cached until the spreadsheet changes in Drive
  (first load after a change takes a few seconds). Needs `openpyxl`.
- `bookshop.py`: bookshop sales (DB_VENDAS) and average purchase cost per ISBN
  (DB_COMPRAS) from AppVerboShop (`LIVRARIA_SPREADSHEET_ID`), served at
  `/api/livraria` without customer data. The "Livraria · Resultado de vendas"
  card adds the TPA fees from CONTAORDEM: terminal 01433272 (`FECHOTPA…`,
  `COMISS.TPA…`) and rental machine 0005346910001.
- `accountant.py`: file names in the accountant's Drive folders, served at
  `/api/contabilista` (names only, filtered by `DASHBOARD_USER_MIN_YEAR` for
  non-admins). The "Envio documental ao contabilista" card checks, for the
  chosen month, that each DÍZIMOS/OFERTAS `RECIBO` and SAÍDAS
  `IMAGEM DO RECIBO` has its copy `yyyyMMdd_<file>` (Apps Script
  `SincronizarRecibosContabilista`, hourly), and lists the fixed-cost
  invoices saved from email (`yyyy_MM_dd_<supplier>…`, FaturasEmail process).
  Set `DASHBOARD_CONTABILISTA_DIZIMOS_FOLDER_ID`, `…_SAIDAS_FOLDER_ID` and
  `…_FATURAS_FOLDER_ID`, and share those folders (Viewer) with the service
  account; the card is hidden unless all three are set.
  `DASHBOARD_CONTABILISTA_FATURAS_ESPERADAS` (optional, JSON list of
  `{"nome", "padrao", "qtd", "desde"}`) sets the invoices expected each
  month: `padrao` is a case-insensitive regex on the file name after its date,
  `qtd` how many per month, `desde` the first month (yyyy-MM). The card then
  shows saved vs expected per supplier. Wrap the JSON in single quotes in the
  env file.
- `cafe.py`: Verbo Café sales (VC_VENDAS, menus via VC_PACK) and average unit
  cost per product (VC_COMPRAS `VALOR DA UNIDADE`; donated purchases cost 0)
  from AppVerboCafé, served at `/api/cafe` in the same shape as the bookshop.
  The "Verbo Café · Resultado de vendas" card uses terminal 01443426, rental
  machine 0005346910002 and plan RECEITAS DE LANCHONETE.
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
random when unset), `DASHBOARD_USER_MIN_YEAR` (first year non-admins see in the
page, default 2026; admins see every year).

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

Admins also see "Enviar Email" in the header. With a month selected, it asks
for confirmation and emails a PDF summary (month totals, fixed costs, cost
centres, bookshop and Verbo Café) to every Diretória member listed in Gerir
contas, whatever their account state. It sends from `GMAIL_ACCOUNT_EMAIL` with the Extrato process token
(`GMAIL_CREDENTIALS_PATH`); `DASHBOARD_PUBLIC_URL` adds the link to the email. With
`DASHBOARD_REPORT_TEST=true` the email goes only to the admin who sends it.

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
