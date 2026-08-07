# CLI Reference - AppExtrato

**Referência completa de comandos disponíveis**

---

## 📖 Uso Geral

```bash
python -m src.gmail_to_sheets.app <comando>
```

---

## 📋 Comandos Disponíveis

### 1. `run-scheduled` — Iniciar Scheduler

**Descrição:** Inicia o scheduler que executa Entradas a cada 1 minuto em background.

**Uso:**
```bash
python -m src.gmail_to_sheets.app run-scheduled
```

**Saída:**
```
================================================================================
Starting application with automatic scheduler
...
[Scheduler iniciado]
Application running. Press Ctrl+C to stop.
[Aguardando primeiro ciclo de 1 minuto]
```

**Logs gerados a cada 1 minuto:**
```
========== Entradas process starting...
[1/6] Authenticating with Google Sheets...
[2/6] Loading and validating entries from DÍZIMOS/OFERTAS...
[3/6] Deduplicating entries...
[4/6] Transferring to CONTAORDEM...
[5/6] Updating status in DÍZIMOS/OFERTAS...
[6/6] Sorting CONTAORDEM by DATA MOV....
========== Entradas process completed successfully!
```

**Parar:**
```bash
# Pressionar Ctrl+C
# ou
kill <pid>
```

**Usar em produção:**
```bash
# Em background (systemd)
sudo systemctl start appextrato

# Em background (nohup)
nohup python -m src.gmail_to_sheets.app run-scheduled > app.log 2>&1 &

# Em Docker
docker-compose up -d appextrato
```

---

### 2. `run-once` — Executar Uma Vez

**Descrição:** Executa o processo Entradas uma única vez. Útil para testes e debugging.

**Uso:**
```bash
python -m src.gmail_to_sheets.app run-once
```

**Saída:**
```
[INFO] Running Entradas process once...
[INFO] Starting Entradas process pipeline
[1/6] Authenticating with Google Sheets...
[2/6] Loading and validating entries from DÍZIMOS/OFERTAS...
      Loaded 50 rows
      Valid: 48, Invalid: 2
[3/6] Deduplicating entries...
      After deduplication: 45 entries
[4/6] Transferring to CONTAORDEM...
      Transferred: 45
[5/6] Updating status in DÍZIMOS/OFERTAS...
      Updated: 45, Failed: 0
[6/6] Sorting CONTAORDEM by DATA MOV....
      Sort completed
Pipeline completed successfully!
  - Total entries processed: 48
  - Invalid entries: 2
  - Transferred: 45
  - Duplicates: 3
  - Status updated: 45
```

**Casos de uso:**
- Testar antes de deploy
- Debugging de problemas
- Validar alterações no código
- Teste de credenciais/conectividade

---

### 3. `conciliacao` — Executar Conciliação Manual

**Descrição:** Executa o processo de Conciliação para preencher `DOC.SOMA` em uma sheet de origem pesquisando correspondências em `CONTAORDEM`.

**Nota:** O processo é **automático** quando usando `run-scheduled` (executa a cada 1 minuto, defasado de 30 segundos do Entradas).

**Uso:**
```bash
python -m src.gmail_to_sheets.app conciliacao [source_sheet]
```

**Argumentos:**
- `source_sheet` (opcional): Nome da sheet de origem (padrão: `T_EXTRATO`)

**Exemplos:**
```bash
# Conciliar T_EXTRATO (padrão)
python -m src.gmail_to_sheets.app conciliacao

# Conciliar outra sheet
python -m src.gmail_to_sheets.app conciliacao OUTRA_SHEET
```

**Saída:**
```
================================================================================
Iniciando processo de Conciliação (T_EXTRATO)
================================================================================
[1/4] Autenticando com Google Sheets...
      Sheets autenticado
[2/4] Carregando e validando registros de T_EXTRATO...
      Carregadas 3418 linhas
      Candidatos válidos: 28
[3/4] Carregando dados de referência...
      Carregadas 4013 linhas de CONTAORDEM
      Cache construído com 3917 registros indexados
[4/4] Realizando conciliação...
      Atualizadas 22 linhas em batch
      Conciliados: 22
================================================================================
Processo de Conciliação concluído!
  - Candidatos encontrados: 28
  - Registros conciliados: 22
  - Sem correspondência: 6
================================================================================
```

**Lógica:**
1. Carrega linhas da sheet onde `DOC.SOMA` está vazio
2. Extrai `ID_INTERNO` de cada linha
3. Pesquisa `ID_INTERNO` em `CONTAORDEM`
4. Se encontrar `DOC.SOMA` preenchido, copia para sheet de origem
5. Batch update: atualiza todas as linhas em uma única chamada API

**Casos de uso:**
- Validar e completar dados entre sheets
- Reconciliar após importação de dados
- Validação cruzada de registros
- Preenchimento automático de campos
- Conciliação contínua (via scheduler)

---

### 4. `status` — Ver Status

**Descrição:** Exibe informações sobre a aplicação e seus processos.

**Uso:**
```bash
python -m src.gmail_to_sheets.app status
```

**Saída:**
```
AppExtrato - Process Management System
  Processes:
    - Entradas: Scheduled (every 1 minute)
    - Conciliacao: Scheduled (every 1 minute, +30s offset)
  Status: Ready
```

---

## 🎯 Exemplos de Uso

### Exemplo 1: Testar Antes de Deploy

```bash
# 1. Validação rápida
python test_entradas_process.py

# Saída:
# ✓ Entry Validation: PASS
# ✓ Deduplication: PASS
# ✓ Transfer Service: PASS
# ✓ Status Updater: PASS
# ✓ ALL TESTS PASSED

# 2. Uma execução real
python -m src.gmail_to_sheets.app run-once

# Saída: Processamento completo com resultados

# 3. Testar scheduler por 5 minutos
timeout 5m python -m src.gmail_to_sheets.app run-scheduled

# Saída: 5 execuções (uma a cada minuto)
```

### Exemplo 2: Iniciar em Produção

```bash
# Opção 1: Systemd (recomendado)
sudo systemctl start appextrato
sudo systemctl status appextrato
sudo tail -f /var/log/appextrato/app.log

# Opção 2: Nohup
nohup python -m src.gmail_to_sheets.app run-scheduled > logs/app.log 2>&1 &

# Opção 3: Docker Compose
docker-compose up -d appextrato
docker-compose logs -f appextrato
```

### Exemplo 3: Executar Conciliação

```bash
# Conciliar T_EXTRATO (padrão)
python -m src.gmail_to_sheets.app conciliacao

# Conciliar outra sheet
python -m src.gmail_to_sheets.app conciliacao OUTRA_SHEET

# Conciliar e salvar log
python -m src.gmail_to_sheets.app conciliacao T_EXTRATO 2>&1 | tee conciliacao.log

# Testar conciliação
python test_conciliation_process.py
```

### Exemplo 4: Debug/Troubleshooting

```bash
# Executar uma vez com logs detalhados
python -m src.gmail_to_sheets.app run-once

# Executar com stderr para ver erros
python -m src.gmail_to_sheets.app run-once 2>&1 | tee debug.log

# Testar validação especificamente
python test_entradas_process.py

# Testar conciliação
python test_conciliation_process.py

# Ver logs históricos
tail -100 logs/gmail-to-sheets.log | grep ERROR
```

---

## 🔍 Interpretando Saídas

### Execução Bem-Sucedida

```
✓ Entry Validation: PASS
✓ Deduplication: PASS
✓ Transfer Service: PASS
✓ Status Updater: PASS
✓ ALL TESTS PASSED
```

### Execução com Entradas Inválidas

```
[2/6] Loading and validating entries from DÍZIMOS/OFERTAS...
      Valid: 45
      Invalid: 5  ← Alguns registros rejeitados
      
  Razões de rejeição:
  - Row 5: TIPO inválido
  - Row 10: FINANCE não está vazio
  - Row 15: VALOR <= 0
```

### Erro de Autenticação

```
[1/6] Authenticating with Google Sheets...
ERROR: Sheets authentication failed: [PERMISSION_DENIED]
       Verifique: SHEETS_SERVICE_ACCOUNT_PATH em .env
                  Credenciais válidas em credentials/
```

### Nenhuma Entrada para Processar

```
[2/6] Loading and validating entries...
WARNING: No valid entries found for transfer
Pipeline completed with 0 results
```

---

## 🛠️ Variáveis de Ambiente

Controláveis via `.env`:

```bash
# Log
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/app.log       # Arquivo de log

# Google
SHEETS_SPREADSHEET_ID=...   # ID da planilha
GMAIL_ACCOUNT_EMAIL=...     # Email para buscar dados

# Caminhos
SHEETS_SERVICE_ACCOUNT_PATH=credentials/sheets-service-account.json
GMAIL_CREDENTIALS_PATH=credentials/gmail-oauth-token.json
GMAIL_CLIENT_SECRETS_PATH=credentials/gmail-client-secret.json
```

---

## 📊 Saídas e Formatos

### Log Format

```
2026-08-06 14:23:45,123 - src.gmail_to_sheets.processes.entradas.orchestrator - INFO - Starting Entradas process pipeline
```

Formato: `TIMESTAMP - LOGGER - LEVEL - MESSAGE`

### Níveis de Log

| Nível | Símbolo | Significado |
|-------|---------|-------------|
| DEBUG | 🔍 | Informações detalhadas de debug |
| INFO | ℹ️ | Informações gerais de execução |
| WARNING | ⚠️ | Avisos (pode continuar) |
| ERROR | ❌ | Erro (processo pode falhar) |

---

## 🚀 Tips & Tricks

### Executar e Salvar Log

```bash
python -m src.gmail_to_sheets.app run-once 2>&1 | tee output.log
```

### Executar com Timeout

```bash
# Parar após 5 minutos
timeout 5m python -m src.gmail_to_sheets.app run-scheduled
```

### Executar em Background e Manter Log

```bash
nohup python -m src.gmail_to_sheets.app run-scheduled > app.log 2>&1 &
echo $! > app.pid  # Salvar PID

# Depois para matar:
kill $(cat app.pid)
```

### Monitorar Execuções

```bash
# Contar execuções por hora
grep "Starting Entradas" logs/gmail-to-sheets.log | wc -l

# Ver todas as transferências bem-sucedidas
grep "Transferred:" logs/gmail-to-sheets.log

# Ver erros
grep ERROR logs/gmail-to-sheets.log
```

---

## 🔐 Segurança

### Não Exponha Credenciais

```bash
# ❌ ERRADO - Credenciais em command-line
python -m app --token ABC123

# ✅ CORRETO - Usar .env
echo "TOKEN=ABC123" >> .env
```

### Proteja Logs

```bash
# Logs podem conter informações sensíveis
chmod 600 logs/gmail-to-sheets.log

# Rotação de logs (systemd faz automaticamente)
sudo journalctl --vacuum=time=30d
```

---

## ✅ Checklist de Uso

- [ ] Python 3.9+ instalado
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] `.env` configurado com credenciais válidas
- [ ] Credenciais arquivos no lugar certo
- [ ] Teste local passou (`python test_entradas_process.py`)
- [ ] Teste de conciliação passou (`python test_conciliation_process.py`)
- [ ] Uma execução testada (`python -m src.gmail_to_sheets.app run-once`)
- [ ] Conciliação testada (`python -m src.gmail_to_sheets.app conciliacao`)
- [ ] Pronto para produção (`python -m src.gmail_to_sheets.app run-scheduled`)

---

## 📞 Support

Para problemas:

1. Verificar `.env` - `cat .env | grep -v "^#"`
2. Verificar logs - `tail -50 logs/gmail-to-sheets.log`
3. Executar teste - `python test_entradas_process.py`
4. Debug - `python -m src.gmail_to_sheets.app run-once`
