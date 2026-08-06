# Processo Entradas

Processamento de entradas de dízimos e ofertas da sheet DÍZIMOS/OFERTAS para CONTAORDEM.

**Status:** ✅ **IMPLEMENTADO**

## 📋 Pipeline (6 Fases)

### Fase 1: Autenticação
Autentica com Google Sheets API via Service Account.

### Fase 2: Validação de Entradas
Carrega registros de DÍZIMOS/OFERTAS e valida critérios:
- ✓ TIPO = "DÍZIMOS/OFERTAS" (ou "DIA VERBO MISSÔES")
- ✓ DOC.SOMA está VAZIO
- ✓ FINANCE está VAZIO
- ✓ VALOR > 0
- ✓ DATA existe e é válida

### Fase 3: Deduplicação
Verifica duplicatas contra CONTAORDEM usando chave: `DATA + VALOR + DESCRIÇÃO`
- Evita transferências repetidas
- Usa cache em memória para batch processing

### Fase 4: Transferência para CONTAORDEM
Transfere registros validados com mapeamento de campos:

```
DÍZIMOS/OFERTAS           →  CONTAORDEM
─────────────────────────    ────────────────────────────
[4] DATA                  →  DATA MOV.
[7] NÚMERO DOCUMENTO      →  DESCRIÇÃO (com suffix)
[8] VALOR                 →  IMPORTÂNCIA
[15] ID_INTERNO           →  ID_INTERNO (cópia)
                          →  TIPO = "Entrada" (fixo)
                          →  PLANO DE CONTA = "DOAÇÕES - DÍZIMOS E OFERTAS" (fixo)
                          →  CENTRO DE CUSTO = "10.10.01 - DÍZIMOS E OFERTAS" (fixo)
                          →  PROCESSO = "DÍZIMOS/OFERTAS" (fixo)
                          →  PERÍODO = extraído de DATA
                          →  FORMA DE PAGAMENTO = "DINHEIRO" (fixo)
                          →  CAIXA = "CAIXA DIÁRIO" (fixo)
                          →  DESCRIÇÃO SOMA = igual a DESCRIÇÃO
```

### Fase 5: Atualização de Status
Preenche FINANCE = "Transferido" em DÍZIMOS/OFERTAS para próximas execuções reconhecerem já processados.

### Fase 6: Ordenação
Ordena CONTAORDEM por DATA MOV. em ordem decrescente.

## 🔧 Serviços Implementados

```
processes/entradas/
├── orchestrator.py              → Orquestrador principal
├── entry_validator.py           → Valida registros
├── entry_deduplication.py       → Deduplicação
├── entry_transfer_service.py    → Transferência
└── entry_status_updater.py      → Atualiza FINANCE
```

### EntryValidator
- Valida cada registro contra critérios de negócio
- Retorna motivo de rejeição se inválido
- Mapeia colunas por nome (case-insensitive)

### EntryDeduplicationService
- Carrega registros existentes em CONTAORDEM
- Cria chaves normalizadas: data-valor-descrição
- Registra novas entradas em cache durante batch

### EntryTransferService
- Constrói linhas formatadas para CONTAORDEM
- Mapeia campos com valores fixos e calculados
- Extrai mês de DATA para PERÍODO
- Formata valores monetários (decimal separator)
- Ordena sheet por DATA MOV. descrescente

### EntryStatusUpdater
- Encontra coluna FINANCE dinamicamente
- Atualiza em batch para eficiência
- Marca "Transferido" para rastrear processamento

## 📊 Fluxo de Dados

```
DÍZIMOS/OFERTAS (entrada)
    ↓
[EntryValidator] → valida TIPO, DOC.SOMA, FINANCE, VALOR, DATA
    ↓ ↓
 válido ↓ inválido → rejeita
    ↓
[EntryDeduplicationService] → verifica duplicatas em CONTAORDEM
    ↓ ↓
 novo ↓ duplicado → pula
    ↓
[EntryTransferService] → constrói linha para CONTAORDEM
    ↓
CONTAORDEM (saída)
    ↓
[EntryStatusUpdater] → marca FINANCE="Transferido" em DÍZIMOS/OFERTAS
    ↓
DÍZIMOS/OFERTAS (atualizado)
    ↓
[Sort by DATA MOV.]
    ↓
CONTAORDEM (ordenado)
```

## 🎯 Características

✅ **Validação rigorosa** — 5 critérios de negócio  
✅ **Deduplicação** — Usa chave normalizada (data+valor+descrição)  
✅ **Valores fixos** — Hardcoded conforme lógica de negócio  
✅ **Rastreamento** — FINANCE marcado como "Transferido"  
✅ **Batch operations** — Atualiza múltiplas linhas eficientemente  
✅ **Auditoria** — Logs detalhados de cada etapa  
✅ **Idempotência** — Re-execução segura (reconhece já processados)  

## 🚀 Uso

### Executar pipeline completo

```python
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator

orchestrator = EntradasOrchestrator()
orchestrator.run()
```

### Usar serviços individualmente

```python
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator
from src.gmail_to_sheets.config.settings import load_settings

settings = load_settings()
sheets_client = SheetsClient(
    service_account_path=str(settings.sheets.service_account_path)
)

validator = EntryValidator(sheets_client, settings.sheets.spreadsheet_id)
is_valid, error = validator.is_valid_entry(row_data, row_number)
```

## 📝 Notas

1. **Coluna NÚMERO DOCUMENTO** — Pode estar vazia. Se vazia, DESCRIÇÃO = "DÍZIMOS E OFERTAS (CULTO)"

2. **ID_INTERNO** — Já existe na sheet DÍZIMOS/OFERTAS (formato ENT0000000001). Apenas copia para CONTAORDEM.

3. **FINANCE** — Campo de validação E marcador. Vazio = elegível. "Transferido" = já processado.

4. **Valores hardcoded** — Por design. Não buscam de CONSTANTES (diferente do Extrato).

5. **Deduplicação** — Usa data+valor+descrição. Descrição inclui NÚMERO DOCUMENTO se preenchido.

## 🔄 Fluxo de Execução Típico

```
1. Operador preenche DÍZIMOS/OFERTAS manualmente
2. Executa EntradasOrchestrator.run()
3. Validação filtra registros elegíveis
4. Deduplicação pula já processados
5. Transferência cria linhas em CONTAORDEM
6. Status updater marca FINANCE="Transferido"
7. Re-execução detecta FINANCE preenchido e pula esses registros
```

## ⚠️ Validações Críticas

Se qualquer critério falhar, o registro é **rejeitado**:

| Campo | Critério | Exemplos de rejeição |
|-------|----------|---------------------|
| TIPO | = "DÍZIMOS/OFERTAS" ou "DIA VERBO MISSÔES" | TIPO vazio, TIPO="Outro" |
| DOC.SOMA | Deve estar vazio | DOC.SOMA="4606815" |
| FINANCE | Deve estar vazio | FINANCE="Transferido" |
| VALOR | > 0 | VALOR="0", VALOR="", VALOR="-5" |
| DATA | Deve estar preenchida | DATA vazio |

## 📈 Status do Projeto

- ✅ Orquestrador implementado
- ✅ Validação de dados
- ✅ Deduplicação
- ✅ Transferência com mapeamento
- ✅ Atualização de status
- ✅ Logging completo
- ✅ Testes de importação
