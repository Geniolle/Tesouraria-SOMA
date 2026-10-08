# Server Monitoring & Diagnostics Guide

This document describes the remote and local continuous monitoring architecture for `Tesouraria-SOMA`.

## Architecture Overview

```
                   GitHub
                      │
            workflow_dispatch
                      │
                      ▼
           Self-hosted Runner
                      │
                      ▼
            server_diagnostics.py
                      │
              ┌───────┴───────┐
              │               │
              ▼               ▼
         GitHub Logs       JSON Artifact


servidor-tesouraria-v2
         │
         ▼
systemd monitor timer (appextrato-monitor.timer)
         │
         ▼
monitor_health.py
         │
         ▼
      NTFY Notifications
```

## 1. Remote Diagnostics (`server_diagnostics.py` & GitHub Actions)

### Script: `scripts/server_diagnostics.py`
- Executed on-demand via GitHub Actions workflow `Server Health Check` (`.github/workflows/server-health-check.yml`).
- Read-only diagnostics script. Does **not** modify production state.
- Produces:
  1. Human-readable text report on terminal stdout.
  2. Structured JSON artifact at `data/server-diagnostics.json`.
- Exit Codes:
  - `0`: `OK`
  - `1`: `WARNING`
  - `2`: `ERROR`

### What it checks:
- **Systemd Services**: `appextrato.service`, `actions.runner.Geniolle-Tesouraria-SOMA.servidor-tesouraria-runner.service`.
- **System Resources**: Disk usage % (warning >= 80%, error >= 90%), Memory usage % (warning >= 85%, error >= 95%), CPU load.
- **Scheduler & Processes**: Seconds since last tick (warning > 120s, error > 180s), process state & consecutive failures.
- **Git Repository**: Branch, HEAD SHA, origin/master SHA, sync state (`synced`, `ahead`, `behind`), clean/dirty working tree (with secrets/env redacted).
- **Log Analysis**: Last 200 journalctl lines for keywords (`Traceback`, `ERROR`, `CRITICAL`, `RESOURCE_EXHAUSTED`, `quota`, `429`, `failed`, `exception`, `Batch write failed`, `Transfer failed`).
- **Data Sanitization**: Automatically redacts passwords, tokens, bearer headers, cookies, `.env` file contents, and credentials.

### GitHub Actions Workflow
- Workflow name: `Server Health Check`
- Trigger: `workflow_dispatch` (Manual / API)
- Artifact: `server-diagnostics` (`data/server-diagnostics.json`, 7 days retention)
- Step Summary: Automatically appends formatted Markdown summary to `$GITHUB_STEP_SUMMARY`.

---

## 2. Continuous Local Watchdog (`monitor_health.py` & Systemd Timer)

### Script: `scripts/monitor_health.py`
- Executed every 1 minute on `servidor-tesouraria-v2` via systemd timer `appextrato-monitor.timer`.
- Monitors local service health, scheduler ticks, GitHub runner status, system thresholds, and process failures.
- Sends instant notifications via `scripts/send_ntfy.py` (using `/etc/appextrato/ntfy.env`).
- Features state persistence & deduplication in `/home/opc/AppExtrato/data/monitor-state.json`.
- Sends recovery notifications when an alerting component returns to healthy state (`✅ TESOURARIA — ...`).
- **Read-Only Vigilance**: The monitor strictly detects and alerts — it does **not** perform automatic service restarts.

### Systemd Timer Configuration:
- Service: `appextrato-monitor.service` (`Type=oneshot`)
- Timer: `appextrato-monitor.timer` (`OnUnitActiveSec=1min`)
- Status check command:
  ```bash
  sudo systemctl status appextrato-monitor.timer --no-pager
  ```

---

## 3. Minimal Sudo Permissions (`/etc/sudoers.d/github-runner-appextrato`)

The runner user `github-runner` is equipped with minimal sudo commands required for deployment and status checking:
```sudoers
github-runner ALL=(root) NOPASSWD: /usr/bin/systemctl restart appextrato, /usr/bin/systemctl status appextrato, /usr/bin/systemctl is-active appextrato, /usr/bin/systemctl show appextrato
```
`github-runner` is also a member of the `systemd-journal` group to allow read-only journalctl log analysis without sudo.
