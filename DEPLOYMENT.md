# Deployment Guide

## Pre-Deployment Checklist

### Configuration
- [ ] All `.env` variables configured with production values
- [ ] `GMAIL_ACCOUNT_EMAIL` verified and tested
- [ ] `SHEETS_SPREADSHEET_ID` correct
- [ ] `GMAIL_LABEL_NAME` and `GMAIL_BACKUP_LABEL_NAME` configured
- [ ] Log directory path is writable
- [ ] Timezone set correctly (default: `Europe/Lisbon`)

### Credentials
- [ ] `credentials/gmail-client-secret.json` placed and readable
- [ ] `credentials/sheets-service-account.json` placed and readable
- [ ] File permissions: `chmod 600 credentials/*.json`
- [ ] Not committed to git (verify `.gitignore` includes `credentials/`)
- [ ] OAuth token missing (will be generated on first run)

### Testing
- [ ] All unit tests pass: `pytest`
- [ ] Linting passes: `ruff check src/`
- [ ] Type checking reviewed: `mypy src/` (known 46 errors)
- [ ] Dry run successful with small email sample
- [ ] Logs verified for errors and warnings

### Environment
- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed: `pip install -e .`
- [ ] Disk space available for logs and data
- [ ] Network connectivity to Gmail and Google Sheets APIs

---

## Local Deployment (Development)

### Quick Start
```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your values

# Run tests
pytest

# Run application
python -m src.gmail_to_sheets
```

### Testing Before Production
```bash
# Test configuration loads
python -c "from src.gmail_to_sheets.config.settings import load_settings; print(load_settings())"

# Test Gmail authentication (creates token)
python -c "from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator; auth = GmailAuthenticator(); auth.authenticate()"

# Test Sheets access
python -c "from src.gmail_to_sheets.clients.sheets_client import SheetsClient; sheets = SheetsClient('your-spreadsheet-id'); print(sheets.get_sheet_names())"

# Test full pipeline with logging
LOG_LEVEL=DEBUG python -m src.gmail_to_sheets
```

---

## Remote Deployment (Oracle/Linux Server)

### Setup on Remote Server

1. **SSH to server**
   ```bash
   ssh opc@servidor-tesouraria
   cd /home/opc/AppExtrato
   ```

2. **Verify Python version**
   ```bash
   python3.11 --version  # Should be 3.11.x
   ```

3. **Create virtual environment (if not exists)**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

5. **Setup credentials**
   ```bash
   # Create credentials directory
   mkdir -p credentials
   chmod 700 credentials
   
   # Copy credential files (from local)
   # scp from local:
   # scp path/to/gmail-client-secret.json opc@servidor-tesouraria:/home/opc/AppExtrato/credentials/
   # scp path/to/sheets-service-account.json opc@servidor-tesouraria:/home/opc/AppExtrato/credentials/
   
   # Set permissions
   chmod 600 credentials/*.json
   ```

6. **Configure .env**
   ```bash
   cp .env.example .env
   nano .env  # Edit with production values
   ```

7. **Test configuration**
   ```bash
   source .venv/bin/activate
   python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()"
   ```

8. **Run initial test**
   ```bash
   python -m pytest -v
   python -m src.gmail_to_sheets --help
   ```

---

## Scheduled Execution (Cron)

### Setup Cron Job

1. **Edit crontab**
   ```bash
   crontab -e
   ```

2. **Add cron job** (runs daily at 06:00 UTC)
   ```cron
   0 6 * * * cd /home/opc/AppExtrato && source .venv/bin/activate && python -m src.gmail_to_sheets >> logs/cron.log 2>&1
   ```

3. **Cron schedule syntax**
   ```
   ┌───────────── minute (0 - 59)
   │ ┌───────────── hour (0 - 23)
   │ │ ┌───────────── day of month (1 - 31)
   │ │ │ ┌───────────── month (1 - 12)
   │ │ │ │ ┌───────────── day of week (0 - 6) (0 = Sunday)
   │ │ │ │ │
   │ │ │ │ │
   * * * * * command
   ```

4. **Common schedules**
   ```cron
   # Every day at 6 AM
   0 6 * * * command
   
   # Every 6 hours
   0 */6 * * * command
   
   # Every weekday at 8 AM
   0 8 * * 1-5 command
   
   # Every 30 minutes
   */30 * * * * command
   ```

5. **View cron logs**
   ```bash
   grep CRON /var/log/syslog  # Linux
   # or check application log:
   tail -f logs/cron.log
   ```

---

## Systemd Service (Optional)

### Create Systemd Service

1. **Create service file** (as root)
   ```bash
   sudo nano /etc/systemd/system/gmail-to-sheets.service
   ```

2. **Service configuration**
   ```ini
   [Unit]
   Description=Gmail to Sheets Pipeline
   After=network-online.target
   Wants=network-online.target
   
   [Service]
   Type=simple
   User=opc
   WorkingDirectory=/home/opc/AppExtrato
   ExecStart=/home/opc/AppExtrato/.venv/bin/python -m src.gmail_to_sheets
   Restart=on-failure
   RestartSec=60
   StandardOutput=journal
   StandardError=journal
   Environment="LOG_LEVEL=INFO"
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start service**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable gmail-to-sheets
   sudo systemctl start gmail-to-sheets
   ```

4. **View service logs**
   ```bash
   sudo journalctl -u gmail-to-sheets -n 100 -f
   ```

---

## Docker Deployment (Future)

### Dockerfile Template
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .env .env.production ./

ENV LOG_LEVEL=INFO

CMD ["python", "-m", "src.gmail_to_sheets"]
```

### Build and Run
```bash
docker build -t gmail-to-sheets .
docker run -v $(pwd)/credentials:/app/credentials gmail-to-sheets
```

---

## Monitoring and Maintenance

### Health Checks

1. **Application running**
   ```bash
   ps aux | grep "gmail_to_sheets"
   ```

2. **Recent successful runs**
   ```bash
   tail -20 logs/gmail-to-sheets.log | grep "Starting\|Completed"
   ```

3. **Check for errors**
   ```bash
   grep ERROR logs/gmail-to-sheets.log | wc -l
   ```

4. **Monitor disk space**
   ```bash
   df -h /home/opc/AppExtrato
   du -sh logs/
   ```

### Maintenance Tasks

1. **Rotate logs** (weekly)
   ```bash
   # Manual rotation
   gzip logs/gmail-to-sheets.log
   # or configure logrotate
   ```

2. **Update dependencies** (monthly)
   ```bash
   pip install --upgrade -r requirements.txt
   ```

3. **Run tests** (after updates)
   ```bash
   pytest tests/
   ```

4. **Backup credentials** (offsite, monthly)
   ```bash
   tar czf credentials-backup-$(date +%Y%m%d).tar.gz credentials/
   ```

---

## Troubleshooting Deployment

### Application won't start
1. Check Python version: `python --version`
2. Check virtual environment activated: `which python`
3. Check `.env` exists: `ls -la .env`
4. Check credentials: `ls -la credentials/`
5. Review startup logs: `python -m src.gmail_to_sheets 2>&1 | head -50`

### Cron job not running
1. Check cron service: `systemctl status cron`
2. Check crontab: `crontab -l`
3. Check logs: `grep CRON /var/log/syslog` or `tail logs/cron.log`
4. Check PATH in cron (use full paths): `/usr/bin/python` not `python`
5. Test command manually: Run the exact command from cron

### Memory issues
1. Monitor memory: `free -h`
2. Check swap: `swapon --show`
3. Reduce BATCH_SIZE in .env
4. Add memory limits if using systemd

### API rate limiting
1. Reduce batch size: `BATCH_SIZE=25`
2. Add delay between runs
3. Check Google Cloud quotas
4. Request quota increase

---

## Rollback Procedure

If deployment fails:

```bash
# Stop current version
systemctl stop gmail-to-sheets

# Rollback to previous git commit
git log --oneline -5
git checkout COMMIT_HASH

# Reinstall dependencies
pip install -e "."

# Run tests
pytest

# Restart service
systemctl start gmail-to-sheets

# Verify
systemctl status gmail-to-sheets
tail -f logs/gmail-to-sheets.log
```

---

## Disaster Recovery

### Backup Strategy
- Keep backups of `.env` (encrypted)
- Backup credentials folder (secure storage)
- Backup `.mypy.ini` and `pyproject.toml` (configuration)
- Backup logs (archive weekly)

### Restore Procedure
```bash
# Restore from backup
tar xzf backup-YYYY-MM-DD.tar.gz

# Verify configuration
python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()"

# Restart service
systemctl restart gmail-to-sheets
```

