# Guia de Integração - Processos Extrato e Entradas

**Versão:** 2.0  
**Data:** 2026-08-06  
**Status:** Pronto para Deploy

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Testes Locais](#testes-locais)
4. [Interface CLI](#interface-cli)
5. [Deployment no Servidor](#deployment-no-servidor)
6. [Monitoramento e Troubleshooting](#monitoramento-e-troubleshooting)

---

## 🎯 Visão Geral

O **AppExtrato** é um sistema de processamento automatizado com dois processos principais:

| Processo | Tipo | Frequência | Descrição |
|----------|------|-----------|-----------|
| **Extrato** | Manual | Sob demanda | Processa extratos MT940 do Gmail |
| **Entradas** | Automático | A cada 1 minuto | Transfere dízimos/ofertas para CONTAORDEM |

---

## 🏗️ Arquitetura

### Estrutura de Pastas

```
src/gmail_to_sheets/
├── app.py                               ← Orchestrador principal
├── orchestrator.py                      ← Extrato (manual)
├── processes/
│   ├── extrato/                         ← Processo Extrato
│   │   ├── orchestrator.py
│   │   └── [8 services]
│   └── entradas/                        ← Processo Entradas
│       ├── orchestrator.py
│       └── [5 services]
└── [clients, config, models, etc]
```

### Fluxo de Execução

```
┌─────────────────────┐
│  AppOrchestrator    │
│  (app.py)           │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌──────────────┐
│ Extrato │  │ Entradas (*)  │
│ Manual  │  │ Automático    │
│         │  │ a cada 1 min  │
└─────────┘  └──────────────┘

(*) Executa em background a cada 1 minuto
    via APScheduler
```

---

## 🧪 Testes Locais

### Pré-requisitos

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Verificar configuração .env
cat .env
# Verifique: SHEETS_SPREADSHEET_ID, SHEETS_SERVICE_ACCOUNT_PATH, etc.
```

### Teste 1: Validação de Entradas

```bash
# Testa validação, deduplicação, transfer e status updater
python test_entradas_process.py

# Saída esperada:
# ✓ Entry Validation: PASS
# ✓ Deduplication: PASS
# ✓ Transfer Service: PASS
# ✓ Status Updater: PASS
```

### Teste 2: Execução Única (Dry-run)

```bash
# Executa Entradas uma vez (sem fazer mudanças)
python -m src.gmail_to_sheets.app run-once

# Saída: Logs detalhados do processamento
```

### Teste 3: Execução com Scheduler

```bash
# Inicia scheduler (Entradas a cada 1 minuto)
timeout 5m python -m src.gmail_to_sheets.app run-scheduled

# Saída:
# [1/6] Authenticating...
# [2/6] Validating entries...
# [3/6] Deduplicating...
# ...
# (repete a cada minuto)
```

---

## 🖥️ Interface CLI

### Comandos Disponíveis

```bash
# 1. Rodar scheduler (automático, 1 minuto)
python -m src.gmail_to_sheets.app run-scheduled

# 2. Rodar Entradas uma vez (para testes)
python -m src.gmail_to_sheets.app run-once

# 3. Ver status
python -m src.gmail_to_sheets.app status
```

### Exemplos de Uso

#### Iniciar Aplicação (Produção)

```bash
# Iniciar em background
nohup python -m src.gmail_to_sheets.app run-scheduled > logs/app.log 2>&1 &

# Monitorar logs
tail -f logs/app.log
```

#### Testar Antes de Deploy

```bash
# 1. Validar processo
python test_entradas_process.py

# 2. Teste de integração (1 execução)
python -m src.gmail_to_sheets.app run-once

# 3. Teste com scheduler (5 minutos)
timeout 5m python -m src.gmail_to_sheets.app run-scheduled
```

---

## 🚀 Deployment no Servidor

### Opção 1: Systemd Service (Linux/Ubuntu)

#### 1. Criar arquivo de serviço

```bash
sudo nano /etc/systemd/system/appextrato.service
```

**Conteúdo:**

```ini
[Unit]
Description=AppExtrato - Process Management System
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/home/appuser/AppExtrato
ExecStart=/usr/bin/python3 -m src.gmail_to_sheets.app run-scheduled
Restart=always
RestartSec=10
StandardOutput=append:/var/log/appextrato/app.log
StandardError=append:/var/log/appextrato/error.log
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

#### 2. Criar diretório de logs

```bash
sudo mkdir -p /var/log/appextrato
sudo chown appuser:appuser /var/log/appextrato
```

#### 3. Ativar e iniciar serviço

```bash
# Recarregar systemd
sudo systemctl daemon-reload

# Ativar na inicialização
sudo systemctl enable appextrato

# Iniciar serviço
sudo systemctl start appextrato

# Verificar status
sudo systemctl status appextrato

# Ver logs
sudo tail -f /var/log/appextrato/app.log
```

### Opção 2: Docker Compose

#### 1. Criar Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar código
COPY . .

# Logs
RUN mkdir -p logs

# Entrypoint
CMD ["python", "-m", "src.gmail_to_sheets.app", "run-scheduled"]
```

#### 2. Criar docker-compose.yml

```yaml
version: '3.8'

services:
  appextrato:
    build: .
    environment:
      - GMAIL_ACCOUNT_EMAIL=${GMAIL_ACCOUNT_EMAIL}
      - GMAIL_SENDER_EMAIL=${GMAIL_SENDER_EMAIL}
      - SHEETS_SPREADSHEET_ID=${SHEETS_SPREADSHEET_ID}
      - SHEETS_SERVICE_ACCOUNT_PATH=/app/credentials/sheets-service-account.json
      - GMAIL_CREDENTIALS_PATH=/app/credentials/gmail-oauth-token.json
      - GMAIL_CLIENT_SECRETS_PATH=/app/credentials/gmail-client-secret.json
      - LOG_LEVEL=INFO
    volumes:
      - ./logs:/app/logs
      - ./credentials:/app/credentials:ro
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

#### 3. Executar

```bash
# Iniciar
docker-compose up -d

# Ver logs
docker-compose logs -f appextrato

# Parar
docker-compose down
```

### Opção 3: Supervisor (Alternativa)

#### 1. Criar configuração

```bash
sudo nano /etc/supervisor/conf.d/appextrato.conf
```

**Conteúdo:**

```ini
[program:appextrato]
command=/usr/bin/python3 -m src.gmail_to_sheets.app run-scheduled
directory=/home/appuser/AppExtrato
user=appuser
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/appextrato/app.log
```

#### 2. Recarregar e iniciar

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start appextrato
```

---

## 📊 Monitoramento e Troubleshooting

### Verificar Status

#### Systemd

```bash
# Status
sudo systemctl status appextrato

# Logs
sudo journalctl -u appextrato -f

# Reiniciar
sudo systemctl restart appextrato
```

#### Docker

```bash
# Status
docker-compose ps

# Logs
docker-compose logs -f appextrato

# Reiniciar
docker-compose restart appextrato
```

### Logs Importantes

```
📍 Location: logs/gmail-to-sheets.log (ou /var/log/appextrato/app.log)

Exemplos de sucesso:
  ✓ "[1/6] Authenticating with Google Sheets..."
  ✓ "[2/6] Loading and validating entries..."
  ✓ "[3/6] Deduplicating entries..."
  ✓ "[4/6] Transferring to CONTAORDEM..."
  ✓ "[5/6] Updating status in DÍZIMOS/OFERTAS..."
  ✓ "[6/6] Sorting CONTAORDEM by DATA MOV...."
  ✓ "Entradas process completed successfully!"

Exemplos de erro:
  ✗ "Sheets authentication failed"
  ✗ "No valid entries found for transfer"
  ✗ "Failed to append row"
```

### Troubleshooting Comum

| Problema | Causa | Solução |
|----------|-------|---------|
| "Sheets authentication failed" | Credentials inválidas | Verificar `SHEETS_SERVICE_ACCOUNT_PATH` |
| "FINANCE column not found" | Sheet estrutura mudou | Atualizar coluna em `DÍZIMOS/OFERTAS` |
| "No valid entries found" | Registros inválidos | Verificar validações em `entry_validator.py` |
| "Scheduler not starting" | APScheduler não instalado | `pip install APScheduler` |
| "Process runs but never transfers" | Deduplicação rejeita tudo | Verificar se DATA+VALOR+DESC já existem |

### Dashboard/Monitoramento

Para produção, considere:

- **Prometheus** + **Grafana** para métricas
- **ELK Stack** para centralizar logs
- **Alerting** via Slack/Email para erros

---

## 📋 Checklist de Deploy

### Pré-Deployment

- [ ] Todos os testes locais passaram (`python test_entradas_process.py`)
- [ ] Scheduler testado localmente (`timeout 5m python -m src.gmail_to_sheets.app run-scheduled`)
- [ ] Credentials configuradas (`.env` com valores corretos)
- [ ] Requirements instalado (`pip install -r requirements.txt`)
- [ ] APScheduler na lista (`pip list | grep APScheduler`)

### Deployment

- [ ] Servidor preparado (Python 3.9+, pip, git)
- [ ] Código clonado/copiado
- [ ] `.env` configurado com valores de produção
- [ ] Serviço systemd/Docker criado e testado
- [ ] Logs rotacionados configurados
- [ ] Backup de credenciais realizado

### Pós-Deployment

- [ ] Serviço iniciado e rodando
- [ ] Logs aparecem regularmente (a cada 1 minuto)
- [ ] Registros sendo transferidos (DÍZIMOS/OFERTAS → CONTAORDEM)
- [ ] FINANCE sendo marcado como "Transferido"
- [ ] Alertas configurados (erro, falha de conexão, etc)

---

## 📞 Suporte

**Logs para compartilhar em caso de problema:**

```bash
# Últimas 50 linhas
tail -50 logs/gmail-to-sheets.log

# Últimas 24 horas
journalctl -u appextrato --since "24 hours ago"

# Verificar configuração (sem valores sensíveis)
grep -v "PASSWORD\|TOKEN\|SECRET" .env
```

---

## 🔄 Atualizações e Manutenção

### Atualizar Código

```bash
# 1. Backup
cp -r . ../AppExtrato.backup.$(date +%Y%m%d)

# 2. Pull novo código
git pull origin master

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Testes
python test_entradas_process.py

# 5. Restart serviço
sudo systemctl restart appextrato
```

### Escala Futura

Quando precisar processar mais entradas:

- Aumentar frequência de Entradas (ex: a cada 30 segundos)
- Adicionar mais workers (múltiplas instâncias)
- Usar fila de jobs (Celery + Redis)
- Implementar banco de dados local para cache

---

## ✅ Resumo

- ✅ Dois processos implementados
- ✅ Entradas roda automaticamente a cada 1 minuto
- ✅ Extrato roda sob demanda (CLI)
- ✅ Testes completos inclusos
- ✅ Pronto para deploy em servidor
- ✅ Múltiplas opções de deployment
- ✅ Monitoramento configurável
