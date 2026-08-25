# Deployment Guide

This project currently runs in production through `systemd`, not Docker.

## Active Production Runtime

- Host: `opc@servidor-tesouraria`
- Project directory: `/home/opc/AppExtrato`
- Service: `appextrato.service`
- Start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`

## Production Checklist

- `.env` is present and populated with production values
- Gmail credentials exist under `credentials/`
- Sheets service account exists under `credentials/`
- `venv` is created and dependencies are installed
- Logs directory exists and is writable
- The service starts and remains `active (running)`
- Logs do not show tracebacks

## Remote Update Steps

1. SSH into the server.
2. Go to `/home/opc/AppExtrato`.
3. Pull the desired branch or commit.
4. Activate the virtual environment.
5. Install updated dependencies if needed.
6. Run a quick validation command.
7. Restart `appextrato.service`.
8. Check `journalctl` for errors.

Example:

```bash
ssh opc@servidor-tesouraria
cd /home/opc/AppExtrato
git pull origin master
source venv/bin/activate
pip install -r requirements.txt
python -m src.gmail_to_sheets.app run-once
sudo systemctl restart appextrato
sudo systemctl status appextrato --no-pager
sudo journalctl -u appextrato -n 50 --no-pager
```

## Service Commands

```bash
sudo systemctl status appextrato --no-pager
sudo systemctl restart appextrato
sudo systemctl stop appextrato
sudo systemctl start appextrato
sudo journalctl -u appextrato -f
```

## Docker

Docker is supported in the repository as a helper for local or future container-based work.
It is not the current production runtime.

See:

- [`DOCKER.md`](DOCKER.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)

