# Docker Setup Guide

## Quick Start with Docker

### Prerequisites

- Docker Desktop installed (Windows/Mac) or Docker Engine (Linux)
- Docker Compose 2.0+
- Credentials files ready

### Build and Run

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env  # or use your editor

# Build image (optional, compose handles this)
docker build -t gmail-to-sheets .

# Run with docker-compose
docker-compose up -d
```

## Docker Compose Configurations

### Production (docker-compose.yml)

```bash
# Start service
docker-compose up -d

# View logs
docker-compose logs -f gmail-to-sheets

# Stop service
docker-compose down

# View container status
docker-compose ps
```

### Development (docker-compose.dev.yml)

```bash
# Start interactive development environment
docker-compose -f docker-compose.dev.yml run --rm gmail-to-sheets-dev

# Inside container, you can run:
# python -m src.gmail_to_sheets       # Run app
# pytest                              # Run tests
# pytest --cov                        # With coverage
# ruff check src/ --fix               # Lint
# mypy src/                           # Type checking
```

## Manual Docker Commands

### Build Image

```bash
# Standard build
docker build -t gmail-to-sheets .

# Build with no-cache (fresh dependencies)
docker build --no-cache -t gmail-to-sheets .

# Build with custom tag
docker build -t gmail-to-sheets:v1.0 .
```

### Run Container

```bash
# Run once (print logs)
docker run --rm \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials:ro \
  -v $(pwd)/logs:/app/logs \
  gmail-to-sheets

# Run in background (daemon)
docker run -d \
  --name gmail-to-sheets \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials:ro \
  -v $(pwd)/logs:/app/logs \
  gmail-to-sheets

# Run with interactive shell
docker run -it --rm gmail-to-sheets bash
```

### Manage Container

```bash
# View logs
docker logs gmail-to-sheets
docker logs -f gmail-to-sheets  # Follow logs

# Inspect container
docker inspect gmail-to-sheets

# Stop container
docker stop gmail-to-sheets

# Remove container
docker rm gmail-to-sheets

# Execute command in running container
docker exec -it gmail-to-sheets bash
docker exec gmail-to-sheets pytest
```

## Volume Configuration

### Credentials (Read-Only)

```yaml
volumes:
  - ./credentials/gmail-client-secret.json:/app/credentials/gmail-client-secret.json:ro
  - ./credentials/sheets-service-account.json:/app/credentials/sheets-service-account.json:ro
```

**Setup:**
```bash
mkdir -p credentials
# Copy your downloaded credential files:
cp ~/Downloads/gmail-client-secret.json credentials/
cp ~/Downloads/sheets-service-account.json credentials/
chmod 600 credentials/*.json
```

### Data & Logs (Read-Write)

```yaml
volumes:
  - ./data:/app/data          # Downloaded attachments
  - ./logs:/app/logs          # Application logs
```

**Setup:**
```bash
mkdir -p data logs
chmod 755 data logs
```

## Environment Variables

Create `.env` file based on `.env.example`:

```bash
# Gmail Configuration
GMAIL_ACCOUNT_EMAIL=your@gmail.com
GMAIL_SENDER_EMAIL=noreply@montepio.pt
GMAIL_SEARCH_QUERY=from:noreply@montepio.pt has:attachment
GMAIL_LABEL_NAME=Serviços/Banco/Montepio24/MT940
GMAIL_BACKUP_LABEL_NAME=serviços-banco-montepio24-archive

# Google Sheets Configuration
SHEETS_SPREADSHEET_ID=1poVWJGSBb...
SHEETS_SHEET_NAME=T_EXTRATO

# Application Behavior
LOG_LEVEL=INFO
BATCH_SIZE=100
SKIP_IF_DUPLICATE=true
ARCHIVE_AFTER_PROCESS=true
TIMEZONE=Europe/Lisbon
ENABLE_MATCHING=false
ENABLE_TRANSFER=true
```

## Health Checks

The container includes a built-in health check that validates configuration:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' gmail-to-sheets

# Get health details
docker inspect gmail-to-sheets | grep -A 5 Health
```

## Resource Limits

Production setup includes resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 512M
    reservations:
      cpus: '0.5'
      memory: 256M
```

Adjust based on your system capacity:

```bash
# Monitor container resources in real-time
docker stats gmail-to-sheets
```

## Logging

### Docker Compose Logging

```bash
# View last 100 lines
docker-compose logs --tail 100

# Follow logs with timestamps
docker-compose logs -t -f

# View logs for specific service
docker-compose logs -f gmail-to-sheets
```

### Application Logs

Application logs are written to `logs/` directory:

```bash
# View inside container
docker exec gmail-to-sheets tail -f /app/logs/gmail-to-sheets.log

# View from host
tail -f logs/gmail-to-sheets.log
```

## Scheduling with Docker

### Option 1: Docker Compose with Cron

Use host's crontab to run docker-compose:

```bash
# Add to crontab (crontab -e):
0 6 * * * cd /path/to/AppExtrato && docker-compose run --rm gmail-to-sheets >> logs/cron.log 2>&1
```

### Option 2: Docker Only with Cron

```bash
# Run Docker container via cron
0 6 * * * docker run --rm --env-file /path/to/.env \
  -v /path/to/credentials:/app/credentials:ro \
  -v /path/to/logs:/app/logs \
  gmail-to-sheets >> /path/to/logs/cron.log 2>&1
```

### Option 3: Scheduled Job with systemd-timer

Create `/etc/systemd/system/gmail-to-sheets.service`:

```ini
[Unit]
Description=Gmail to Sheets Pipeline
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/opc/AppExtrato
ExecStart=/usr/bin/docker-compose run --rm gmail-to-sheets

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/gmail-to-sheets.timer`:

```ini
[Unit]
Description=Run Gmail to Sheets Pipeline Daily

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gmail-to-sheets.timer
sudo systemctl start gmail-to-sheets.timer

# Check status
sudo systemctl status gmail-to-sheets.timer
sudo systemctl list-timers
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs gmail-to-sheets

# Check configuration loads
docker run --rm --env-file .env gmail-to-sheets \
  python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()"

# Check image
docker images | grep gmail-to-sheets

# Rebuild
docker-compose build --no-cache
```

### Permission issues

```bash
# Fix credential permissions
chmod 600 credentials/*.json

# Fix volume permissions
docker exec gmail-to-sheets chown -R 1000:1000 /app/logs /app/data
```

### Out of memory

```bash
# Reduce batch size
docker-compose exec gmail-to-sheets bash
# Edit environment or config:
export BATCH_SIZE=25
python -m src.gmail_to_sheets
```

### Network issues

```bash
# Check network
docker network ls
docker network inspect gmail-to-sheets-network

# Troubleshoot DNS resolution
docker exec gmail-to-sheets nslookup gmail.com
```

## Best Practices

### Security

- Never commit credentials files
- Use `.env` for sensitive data (git-ignored)
- Run container as non-root user (handled by Dockerfile)
- Use read-only volumes for credentials
- Regular credential rotation

### Performance

- Use multi-stage builds (included in Dockerfile)
- Minimize image layers
- Use `.dockerignore` to exclude unnecessary files
- Enable logging drivers for centralized logging

### Maintenance

- Regular image updates: `docker-compose pull`
- Monitor container health: `docker stats`
- Rotate logs: Docker json-file driver handles this
- Backup data and logs: Set up scheduled backups

## Production Deployment

For production, consider:

1. **Image Registry:** Push to Docker Hub or private registry
   ```bash
   docker tag gmail-to-sheets username/gmail-to-sheets:v1.0
   docker push username/gmail-to-sheets:v1.0
   ```

2. **Orchestration:** Use Kubernetes or Docker Swarm
3. **Monitoring:** Integrate with monitoring stack (Prometheus, etc.)
4. **Logging:** Centralize logs (ELK, Splunk, etc.)
5. **Backup:** Automated credential and data backups

