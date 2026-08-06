# Migração para Estrutura de Processos

**Data:** 2026-08-06  
**Status:** ✅ Completo

## 📋 Resumo da Reorganização

A estrutura do projeto foi reorganizada para separar a lógica de negócio por **processos independentes**, facilitando:
- Manutenção de código
- Adição de novos processos
- Isolamento de dependências
- Escalabilidade

---

## 🗂️ Nova Estrutura

### Antes
```
src/gmail_to_sheets/
├── services/
│   ├── attachment_processor.py
│   ├── cash_balance_service.py
│   ├── matching_service.py
│   ├── sheets_writer.py
│   ├── smart_deduplication_service.py
│   ├── transfer_matching_service.py
│   ├── transfer_service.py
│   ├── transaction_recovery_service.py
│   ├── batch_writer.py          ← Compartilhado
│   ├── batch_updater.py         ← Compartilhado
│   └── balance_protection_service.py ← Compartilhado
```

### Depois
```
src/gmail_to_sheets/
├── services/                          ← Serviços compartilhados
│   ├── batch_writer.py
│   ├── batch_updater.py
│   ├── balance_protection_service.py
│   └── ...
│
└── processes/                         ← Processos de negócio
    ├── extrato/                       ← Processo Extrato
    │   ├── __init__.py
    │   ├── README.md
    │   ├── attachment_processor.py
    │   ├── cash_balance_service.py
    │   ├── matching_service.py
    │   ├── sheets_writer.py
    │   ├── smart_deduplication_service.py
    │   ├── transfer_matching_service.py
    │   ├── transfer_service.py
    │   └── transaction_recovery_service.py
    │
    └── entradas/                      ← Processo Entradas (em desenvolvimento)
        ├── __init__.py
        └── README.md
```

---

## 🔄 Migração de Imports

### Atualizações Necessárias

Se você estava importando dos `services/`, atualize para `processes/extrato/`:

#### Antes ❌
```python
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.services.sheets_writer import SheetsWriter
from src.gmail_to_sheets.services.transfer_service import TransferService
from src.gmail_to_sheets.services.matching_service import MatchingService
```

#### Depois ✅
```python
from src.gmail_to_sheets.processes.extrato.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.processes.extrato.sheets_writer import SheetsWriter
from src.gmail_to_sheets.processes.extrato.transfer_service import TransferService
from src.gmail_to_sheets.processes.extrato.matching_service import MatchingService
```

---

## 📦 Serviços Movidos

Os seguintes serviços foram movidos de `services/` para `processes/extrato/`:

| Serviço | Função |
|---------|--------|
| `attachment_processor.py` | Extrai conteúdo de emails |
| `smart_deduplication_service.py` | Evita duplicatas inteligentemente |
| `transaction_recovery_service.py` | Recupera IDs de transações |
| `sheets_writer.py` | Escreve transações em sheets |
| `transfer_service.py` | Transfere para CONTAORDEM (simples) |
| `transfer_matching_service.py` | Transfere + faz matching |
| `cash_balance_service.py` | Atualiza saldo de caixa |
| `matching_service.py` | Matching com CONSTANTES |

---

## ✅ Arquivos Atualizados

- ✅ `src/gmail_to_sheets/orchestrator.py` → Imports atualizados
- ✅ `src/gmail_to_sheets/processes/extrato/` → Novos services
- ✅ `src/gmail_to_sheets/processes/extrato/README.md` → Documentação
- ✅ `src/gmail_to_sheets/processes/README.md` → Índice de processos
- ✅ `src/gmail_to_sheets/processes/entradas/README.md` → Template para novo processo

---

## 🚀 Próximas Etapas

1. **Testes Regressivos**
   - Executar testes para garantir compatibilidade
   - Validar imports em todo o projeto

2. **Implementar Processo Entradas**
   - Definir estrutura de dados
   - Implementar serviços especializados
   - Documentar pipeline

3. **Documentação Adicional** (opcional)
   - Atualizar diagramas de arquitetura
   - Criar exemplos de uso
   - Guia para novos processos

---

## 📝 Changelog

### v2.0 - Reorganização em Processos
- ✅ Criada pasta `processes/` com subprocessos
- ✅ Movidos services do Extrato para `processes/extrato/`
- ✅ Atualizados imports no orchestrator
- ✅ Documentação completa da nova estrutura
- ✅ Template preparado para novo processo (Entradas)

---

## ⚠️ Notas Importantes

1. **Compatibilidade**: Os imports do orchestrator foram atualizados. Testes devem passar.

2. **Serviços Compartilhados**: `batch_writer`, `batch_updater` e `balance_protection_service` permanecem em `services/` (não são específicos do Extrato).

3. **Escalabilidade**: Novos processos devem seguir o mesmo padrão:
   - Pasta dedicada em `processes/[nome]/`
   - Seus próprios services especializados
   - Arquivo README com documentação

4. **Manutenção**: Cada processo é independente, facilitando manutenção e testes isolados.

---

## 🔗 Referências

- [README de Processos](src/gmail_to_sheets/processes/README.md)
- [README do Extrato](src/gmail_to_sheets/processes/extrato/README.md)
- [Documentação de Arquitetura](ARCHITECTURE.md)
