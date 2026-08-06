# Processos de Negócio - AppExtrato

Estrutura modular de processos de negócio independentes com seus próprios serviços especializados.

## 📁 Estrutura

```
processes/
├── extrato/          → Processo de Extrato Bancário (MT940)
│   ├── README.md
│   ├── attachment_processor.py
│   ├── smart_deduplication_service.py
│   ├── transaction_recovery_service.py
│   ├── sheets_writer.py
│   ├── transfer_service.py
│   ├── transfer_matching_service.py
│   ├── cash_balance_service.py
│   └── matching_service.py
│
└── entradas/         → Processo de Entradas Manuais (Em desenvolvimento)
    └── README.md
```

## ✅ Processos Implementados

### 1. **Extrato** (`extrato/`)

Processamento de extratos bancários (MT940) baixados via Gmail.

**Responsabilidade:** Orquestrar o pipeline completo de:
- Download de MT940 do Gmail
- Parsing e validação de dados
- Deduplicação inteligente
- Escrita em Google Sheets
- Transferência e matching com referências

**Serviços Principais:**
- `AttachmentProcessor` → Download de anexos
- `SmartDeduplicationService` → Deduplicação por data+valor
- `TransactionRecoveryService` → Recuperação de IDs
- `SheetsWriter` → Escrita em T_EXTRATO
- `TransferService` → Transferência simples
- `TransferMatchingService` → Transferência + matching
- `CashBalanceService` → Atualização de saldo
- `MatchingService` → Lógica de matching

**Entrada:** Email com arquivo MT940
**Saída:** Transações em CONTAORDEM com matching automático

---

## 🚀 Processos em Desenvolvimento

### 2. **Entradas** (`entradas/`)

Processamento de entradas manuais (a implementar).

**Responsabilidade:** Processar entradas de dados inseridas manualmente nos formulários.

**Status:** ⏳ Planejamento

---

## 🏗️ Arquitetura de um Processo

Cada processo deve ter:

1. **Pasta dedicada** → `processes/[nome-processo]/`
2. **Arquivo README.md** → Documentação do pipeline
3. **Serviços especializados** → Lógica de negócio do processo
4. **Imports centralizados** → Facilita manutenção

```python
# Estrutura recomendada para um novo processo
processes/novo-processo/
├── README.md                          # Documentação
├── orchestrator.py                    # (opcional) Orquestrador local
├── service_a.py                       # Serviço 1
├── service_b.py                       # Serviço 2
└── service_c.py                       # Serviço 3
```

---

## 📝 Criando um Novo Processo

### 1. Criar a estrutura
```bash
mkdir -p src/gmail_to_sheets/processes/novo-processo
touch src/gmail_to_sheets/processes/novo-processo/__init__.py
touch src/gmail_to_sheets/processes/novo-processo/README.md
```

### 2. Documentar o pipeline
Criar README.md com:
- Descrição do processo
- Fases/etapas
- Serviços envolvidos
- Fluxo de dados

### 3. Implementar serviços
Criar arquivos `.py` com lógica especializada.

### 4. Atualizar imports
Se o processo for invocado do orchestrator principal:
```python
from src.gmail_to_sheets.processes.novo_processo.service import ServiceName
```

---

## 🔗 Interoperabilidade

### Serviços Compartilhados
Alguns serviços são genéricos e compartilhados entre processos:

- `src/gmail_to_sheets/services/batch_writer.py`
- `src/gmail_to_sheets/services/batch_updater.py`
- `src/gmail_to_sheets/services/balance_protection_service.py`

### Clientes Reutilizáveis
Todos os processos usam os mesmos clientes:
- `GmailClient` → Acesso ao Gmail
- `SheetsClient` → Acesso ao Google Sheets

---

## 📊 Estado Atual

| Processo | Status | Fases | Serviços |
|----------|--------|-------|----------|
| **Extrato** | ✅ Completo | 9 | 8 |
| **Entradas** | ⏳ Planejamento | - | - |

---

## 💡 Próximos Passos

1. Implementar Processo de **Entradas**
2. Documentar pipeline específico
3. Criar serviços especializados
4. Integrar ao orchestrador principal
