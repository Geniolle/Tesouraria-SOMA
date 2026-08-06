# Deploy Rápido - AppExtrato

**Guia de 5 minutos para deploy em produção**

---

## 🚀 Deploy em Linux/Ubuntu (Systemd)

### 1️⃣ Preparar Servidor

```bash
# SSH no servidor
ssh appuser@seu-servidor.com
cd /home/appuser

# Clonar/copiar código
git clone <seu-repo> AppExtrato
cd AppExtrato

# Instalar Python 3.11+
sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv

# Criar venv
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### 2️⃣ Configurar Credenciais

```bash
# Copiar arquivo .env
nano .env

# Preencher com valores de produção:
GMAIL_ACCOUNT_EMAIL=seu@email.com
GMAIL_SENDER_EMAIL=noreply@seu-dominio.pt
SHEETS_SPREADSHEET_ID=seu-spreadsheet-id
SHEETS_SERVICE_ACCOUNT_PATH=credentials/sheets-service-account.json
GMAIL_CREDENTIALS_PATH=credentials/gmail-oauth-token.json
GMAIL_CLIENT_SECRETS_PATH=credentials/gmail-client-secret.json
LOG_LEVEL=INFO
```

### 3️⃣ Testar Localmente

```bash
# Teste rápido (1 execução)
python -m src.gmail_to_sheets.app run-once

# Deve ver logs com sucesso ou erro
# Se sucesso → próximo passo
# Se erro → verificar credenciais e .env
```

### 4️⃣ Criar Serviço Systemd

```bash
# Criar arquivo de serviço
sudo tee /etc/systemd/system/appextrato.service > /dev/null << 'EOF'
[Unit]
Description=AppExtrato - Entradas Process (every 1 min)
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/home/appuser/AppExtrato
ExecStart=/home/appuser/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled
Restart=always
RestartSec=10
StandardOutput=append:/var/log/appextrato/app.log
StandardError=append:/var/log/appextrato/error.log
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

# Criar diretório de logs
sudo mkdir -p /var/log/appextrato
sudo chown appuser:appuser /var/log/appextrato

# Ativar serviço
sudo systemctl daemon-reload
sudo systemctl enable appextrato
sudo systemctl start appextrato

# Verificar
sudo systemctl status appextrato
```

### 5️⃣ Verificar Funcionamento

```bash
# Ver status
sudo systemctl status appextrato

# Ver logs (tempo real)
sudo tail -f /var/log/appextrato/app.log

# Deve mostrar:
# ✓ "Starting Entradas process..."
# ✓ "Scheduled Entradas process completed successfully"
# (a cada 1 minuto)
```

---

## 🐳 Deploy com Docker

### 1️⃣ Preparar Servidor

```bash
# Instalar Docker e Docker Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

# Começar daemon Docker
sudo systemctl start docker
sudo systemctl enable docker
```

### 2️⃣ Clonar e Configurar

```bash
# Clonar código
git clone <seu-repo> AppExtrato
cd AppExtrato

# Configurar .env
nano .env
# (preencher com valores de produção)

# Copiar credenciais
mkdir -p credentials
# Copiar arquivos de credenciais para credentials/
```

### 3️⃣ Iniciar Container

```bash
# Build e start
docker-compose up -d

# Ver logs
docker-compose logs -f appextrato

# Parar
docker-compose down
```

---

## 🧪 Testar Antes de Deploy

```bash
# 1. Validação local
python test_entradas_process.py

# 2. Uma execução (dry-run)
python -m src.gmail_to_sheets.app run-once

# 3. Scheduler por 5 minutos
timeout 5m python -m src.gmail_to_sheets.app run-scheduled
```

---

## 📊 Monitorar Produção

### Ver Logs

```bash
# Últimas 20 linhas
tail -20 /var/log/appextrato/app.log

# Tempo real
tail -f /var/log/appextrato/app.log

# Filtrar erros
grep ERROR /var/log/appextrato/app.log

# Últimas 24 horas
journalctl -u appextrato --since "24 hours ago" -f
```

### Verificar Status

```bash
# Systemd
sudo systemctl status appextrato

# Docker
docker-compose ps
docker-compose logs appextrato

# Processo
ps aux | grep appextrato
```

### Reiniciar

```bash
# Systemd
sudo systemctl restart appextrato

# Docker
docker-compose restart appextrato
```

---

## 🔧 Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| "Connection refused" | Verificar `.env` e credentials |
| "Module not found" | `pip install -r requirements.txt` |
| "FINANCE column not found" | Verificar estrutura de DÍZIMOS/OFERTAS |
| "Process não transfere nada" | Verificar se registros são válidos (validação) |
| "Permissão negada em logs" | `sudo chown appuser:appuser /var/log/appextrato` |

---

## ✅ Checklist Final

- [ ] Python 3.9+ instalado
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] `.env` configurado
- [ ] Credenciais no lugar certo
- [ ] Testes locais passaram
- [ ] Serviço/Docker iniciado
- [ ] Logs aparecem a cada 1 minuto
- [ ] Registros sendo transferidos

---

## 📞 Resumo de Comandos Principais

```bash
# Testar localmente
python test_entradas_process.py

# Uma execução
python -m src.gmail_to_sheets.app run-once

# Scheduler (produção)
python -m src.gmail_to_sheets.app run-scheduled

# Ver status (systemd)
sudo systemctl status appextrato

# Ver logs (systemd)
sudo tail -f /var/log/appextrato/app.log

# Reiniciar (systemd)
sudo systemctl restart appextrato
```

Pronto! 🎉
