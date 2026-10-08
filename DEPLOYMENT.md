# Deployment Guide

This project runs in production through `systemd` (`appextrato.service`) managed automatically via **GitHub Actions Self-hosted Runner**.

## Official Deployment Flow

```
Pull Request
    ↓
CI (GitHub-hosted runner: unit tests & ruff check)
    ↓
Merge master
    ↓
GitHub Actions (Deploy Production workflow)
    ↓
Self-hosted runner (servidor-tesouraria-v2)
    ↓
Testes no servidor (pytest & compileall)
    ↓
Restart appextrato.service (via minimal sudo)
    ↓
Health check (status & service check)
    ↓
Produção (Active & Healthy)
```

## Active Production Runtime

- Host: `opc@servidor-tesouraria-v2`
- Project directory: `/home/opc/AppExtrato`
- Service: `appextrato.service`
- Runner Directory: `/home/github-runner/actions-runner-tesouraria`
- Runner User: `github-runner` (dedicated user with minimal sudo permissions)
- Runner Service: `actions.runner.Geniolle-Tesouraria-SOMA.servidor-tesouraria-runner.service`
- Start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`

## Automatic CI/CD Pipeline

1. **CI Workflow (`.github/workflows/ci.yml`)**:
   - Executes on every Pull Request and Push to `master`.
   - Runs `ruff check .` and `pytest` on `ubuntu-latest`.
   - Has no access to production credentials.

2. **Deploy Workflow (`.github/workflows/deploy-production.yml`)**:
   - Executes automatically after `CI` succeeds on `master`.
   - Environment: `production`.
   - Concurrency group: `tesouraria-production` (prevents concurrent deploys).
   - Runs on self-hosted runner `[self-hosted, linux, tesouraria, production]`.
   - Executes git pull `--ff-only`, virtualenv test suite, `systemctl restart appextrato`, and post-restart health check.
   - Automatically rolls back to the previous good commit if health check fails.

## Manual Emergency Operations & Health Checks

```bash
ssh opc@servidor-tesouraria-v2
cd /home/opc/AppExtrato
source venv/bin/activate
python -m src.gmail_to_sheets.app status
sudo systemctl status appextrato --no-pager -l
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
