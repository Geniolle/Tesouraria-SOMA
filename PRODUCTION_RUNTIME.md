# Production Runtime

This project has a single active production runtime managed automatically via GitHub Actions self-hosted runner.

## Active Production

- Host: `opc@servidor-tesouraria-v2`
- Project directory: `/home/opc/AppExtrato`
- Self-Hosted Runner directory: `/home/github-runner/actions-runner-tesouraria`
- Dedicated Runner User: `github-runner`
- Runtime: `systemd`
- Service name: `appextrato.service`
- Start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`
- Scheduler: single central orchestrator tick every 60 seconds
- Process health: `/home/opc/AppExtrato/data/orchestrator-health.json`

## Official CI/CD Deployment Flow

```
Pull Request
    ↓
CI
    ↓
Merge master
    ↓
GitHub Actions
    ↓
Self-hosted runner servidor-tesouraria-v2
    ↓
testes no servidor
    ↓
restart appextrato.service
    ↓
health check
    ↓
produção
```

## Operational Health

Use:

```bash
cd /home/opc/AppExtrato
source venv/bin/activate
python -m src.gmail_to_sheets.app status
sudo systemctl status appextrato --no-pager -l
sudo journalctl -u appextrato --since "10 minutes ago" --no-pager
```

The CLI `status` command is local-only and does not call Gmail or Google Sheets APIs.

The central scheduler records per-process state, last run, last success, last failure and consecutive failures. Three consecutive failures generate a CRITICAL `PROCESS HEALTH ALERT` in the normal logs.

## Role of Docker

Docker is available in the repository as a support path, not as the current production executor.

Use Docker for:

- local isolation during development;
- future container-based deployment experiments;
- reproducible builds when needed.

Do not treat Docker as the source of truth for the live server unless the server deployment is explicitly migrated.

## Related Files

- [`SERVER_PATH.md`](SERVER_PATH.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`DOCKER.md`](DOCKER.md)
- [`UPDATE_SERVER.md`](UPDATE_SERVER.md)
