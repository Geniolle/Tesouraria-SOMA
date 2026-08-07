# Processos - Documentação Completa

## Overview

Sistema modular de processos para orquestração de workflows. Cada processo é independente e pode ser executado sob demanda ou automaticamente.

## Processos Disponíveis

### 1. Extrato

**Status:** ✅ Ativo | **Trigger:** Manual

Importa e processa extratos bancários via email (formato MT940).

**Pipeline:**
1. Autenticação Gmail (OAuth)
2. Busca de emails com anexos MT940
3. Download e parsing de arquivos
4. Deduplicação (por data+valor)
5. Escrita em `T_EXTRATO` com formatação
6. Atualização de saldos em `SALDO_CAIXA`

**Entrada:** Email com anexo MT940  
**Saída:** Linhas em `T_EXTRATO` + atualização em `SALDO_CAIXA`

---

### 2. Entradas

**Status:** ✅ Ativo | **Trigger:** Automático (a cada 1 minuto)

Transfere registros de `DÍZIMOS/OFERTAS` para `CONTAORDEM` com validações.

**Pipeline:**
1. Validação de registros (TIPO, DOC.SOMA, FINANCE, VALOR, DATA)
2. Deduplicação (data+valor+descrição vs CONTAORDEM)
3. Transferência com mapeamento de campos
4. Marcação de status (FINANCE = "Transferido")
5. Ordenação de CONTAORDEM por data

**Entrada:** Linhas em `DÍZIMOS/OFERTAS` com FINANCE vazio  
**Saída:** Linhas em `CONTAORDEM` + marcação em `DÍZIMOS/OFERTAS`

**Validações:**
- TIPO deve ser "DÍZIMOS/OFERTAS" ou "DIA VERBO MISSÔES"
- DOC.SOMA deve estar vazio
- FINANCE deve estar vazio
- VALOR > 0
- DATA preenchida

**Agendamento:**
```bash
python -m src.gmail_to_sheets.app run-scheduled
```

**Uma execução:**
```bash
python -m src.gmail_to_sheets.app run-once
```

---

### 3. Conciliação

**Status:** ✅ Novo | **Trigger:** Manual

Valida e preenche `DOC.SOMA` em sheets de origem pesquisando em `CONTAORDEM`.

**Pipeline:**
1. Carregamento de candidatos (DOC.SOMA vazio + ID_INTERNO preenchido)
2. Carregamento de dados de referência (CONTAORDEM)
3. Lookup de ID_INTERNO em CONTAORDEM
4. Validação de formato DOC.SOMA (7 dígitos numéricos)
5. Batch update em sheet de origem

**Entrada:** Registros com DOC.SOMA vazio e ID_INTERNO preenchido  
**Saída:** DOC.SOMA preenchido na sheet de origem

**Formato DOC.SOMA:**
- Tipo: Numérico
- Comprimento: 7 dígitos
- Exemplo: `5408307`

**Uso:**
```bash
# Conciliar T_EXTRATO (padrão)
python -m src.gmail_to_sheets.app conciliacao

# Conciliar outra sheet
python -m src.gmail_to_sheets.app conciliacao OUTRA_SHEET
```

**Exemplo de Fluxo:**
```
T_EXTRATO linha 5:
  ID_INTERNO: "ABC123"
  DOC.SOMA: [vazio]

↓ Lookup em CONTAORDEM

CONTAORDEM:
  ID_INTERNO: "ABC123"
  DOC.SOMA: "5408307"

↓ Batch update

T_EXTRATO linha 5:
  DOC.SOMA: "5408307" ✓
```

---

## Arquitetura de Processos

### Estrutura de Diretórios

```
src/gmail_to_sheets/processes/
├── extrato/
│   ├── attachment_processor.py
│   ├── cash_balance_service.py
│   ├── matching_service.py
│   ├── sheets_writer.py
│   ├── smart_deduplication_service.py
│   ├── transaction_recovery_service.py
│   ├── transfer_matching_service.py
│   ├── transfer_service.py
│   ├── orchestrator.py
│   ├── README.md
│   └── __init__.py
├── entradas/
│   ├── entry_validator.py
│   ├── entry_deduplication.py
│   ├── entry_transfer_service.py
│   ├── entry_status_updater.py
│   ├── orchestrator.py
│   ├── README.md
│   └── __init__.py
└── conciliacao/
    ├── validator.py
    ├── lookup_service.py
    ├── reconciliation_service.py
    ├── orchestrator.py
    ├── README.md
    └── __init__.py
```

### Padrão de Implementação

Cada processo segue o padrão:

1. **Validators** — Validam dados de entrada
2. **Services** — Executam lógica específica
3. **Orchestrator** — Coordena pipeline completo

```python
# Exemplo: Uso de Conciliação
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator

orchestrator = ConciliationOrchestrator(source_sheet="T_EXTRATO")
orchestrator.run()
```

---

## Integração com App

### AppOrchestrator

Gerencia todos os processos:

```python
from src.gmail_to_sheets.app import AppOrchestrator

app = AppOrchestrator()

# Entradas automático
app.run_interactive()  # run-scheduled

# Entradas uma vez
app.run_once()  # run-once

# Conciliação
app.run_conciliation(source_sheet="T_EXTRATO")  # conciliacao
```

### CLI

```bash
# Scheduler automático (Entradas a cada 1 min)
python -m src.gmail_to_sheets.app run-scheduled

# Entradas uma execução
python -m src.gmail_to_sheets.app run-once

# Conciliação T_EXTRATO
python -m src.gmail_to_sheets.app conciliacao

# Conciliação outra sheet
python -m src.gmail_to_sheets.app conciliacao OUTRA_SHEET

# Status
python -m src.gmail_to_sheets.app status
```

---

## Fluxos Comuns

### Flow 1: Importar Extrato + Conciliar

```bash
# Processo manual (email enviado → anexo MT940 disponível)
# 1. Importar extrato
python -m src.gmail_to_sheets.app conciliacao

# 2. Validar e conciliar
python -m src.gmail_to_sheets.app conciliacao T_EXTRATO
```

### Flow 2: Automação Contínua

```bash
# Terminal 1: Scheduler automático (Entradas a cada 1 min)
python -m src.gmail_to_sheets.app run-scheduled

# Terminal 2: Monitorar logs
tail -f logs/gmail-to-sheets.log

# Resultado: Entradas transferidas automaticamente a cada minuto
```

### Flow 3: Teste Completo

```bash
# 1. Testar Entradas
python test_entradas_process.py

# 2. Testar Conciliação
python test_conciliation_process.py

# 3. Validar status
python -m src.gmail_to_sheets.app status

# 4. Pronto para produção
```

---

## Tratamento de Erros

### Por Processo

#### Extrato
- **Erro:** Nenhum email encontrado → Log warning, sem saída
- **Erro:** Parse MT940 falha → Detalhamento por linha
- **Erro:** Deduplicação → Registro skipado, continua pipeline

#### Entradas
- **Erro:** Validação falha → Registro marcado como inválido, continua
- **Erro:** Duplicata → Incrementa contador, pula registro
- **Erro:** Transfer falha → Atualiza contador failed, continua

#### Conciliação
- **Erro:** ID_INTERNO não encontrado → Contabilizado em `not_found`
- **Erro:** DOC.SOMA formato inválido → Contabilizado em `invalid_format`
- **Erro:** Batch update falha → Falha isolada, próxima execução retry

### Logging

Todos os processos registram em `logs/gmail-to-sheets.log`:

```
[TIMESTAMP] [LEVEL] [LOGGER] [MESSAGE]

Níveis:
- DEBUG: Detalhes de execução
- INFO: Marco de progresso
- WARNING: Problema não crítico
- ERROR: Falha de execução
```

### Recuperação

1. **Idempotência:** Marcação de status permite re-execução segura
2. **Batch atomicidade:** Atualização em batch é tudo-ou-nada
3. **Logging:** Histórico completo para auditoria

---

## Extensibilidade

### Adicionar Novo Processo

1. Criar diretório: `processes/novo_processo/`
2. Implementar:
   - `validator.py` — Validação de dados
   - `service.py` — Lógica principal
   - `orchestrator.py` — Coordenação
3. Adicionar em `app.py`:
   ```python
   from src.gmail_to_sheets.processes.novo_processo.orchestrator import NovoOrchestrator
   
   def run_novo(self):
       orchestrator = NovoOrchestrator()
       orchestrator.run()
   ```
4. Adicionar comando CLI:
   ```bash
   parser.add_argument("command", choices=["...", "novo"])
   ```
5. Documentar em `PROCESSES.md`

---

## Roadmap

### Curto Prazo
- [ ] Validação de dados antes/depois em Conciliação
- [ ] Histórico de execuções (audit trail)
- [ ] Alertas por email em caso de erro

### Médio Prazo
- [ ] Suporte a múltiplos campos de lookup
- [ ] Scheduler customizável (não apenas 1 min)
- [ ] Dashboard de monitoramento
- [ ] Retry automático com backoff

### Longo Prazo
- [ ] Pipeline genérico (declarativo)
- [ ] Webhooks para integrações
- [ ] Data lineage e rastreamento
- [ ] Testes de carga e stress

---

## Referências

- [CLI Reference](CLI_REFERENCE.md) — Comandos disponíveis
- [Architecture](ARCHITECTURE.md) — Design geral
- [Troubleshooting](TROUBLESHOOTING.md) — Resoluções de problemas
