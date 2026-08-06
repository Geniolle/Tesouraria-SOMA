# Processo Extrato

Processamento completo de extratos bancários (MT940) do Gmail para Google Sheets com matching automático.

## 📋 Pipeline (9 Fases)

### Fase 1: Configuração
Carrega configurações do ambiente e valida parâmetros.

### Fase 2: Autenticação Gmail
Autentica via OAuth 2.0 e valida credenciais.

### Fase 3: Autenticação Google Sheets
Autentica via Service Account e inicializa cliente Sheets.

### Fase 4: Busca de Emails
- Pesquisa emails com anexos MT940
- Filtra por query (ex: `has:attachment subject:MT940`)
- Seleciona o email mais recente por `internalDate`

### Fase 5: Download e Parse de MT940
- Baixa arquivo `.txt` do email
- Parseia formato MT940
- Extrai transações, saldos de abertura/fechamento
- Remove `INBOX`, adiciona label de backup

### Fase 5.5: Validação de Reconciliação Contábil
Verifica: `saldo_abertura + soma_transações = saldo_fechamento`
Para se houver discrepâncias.

### Fase 6: Deduplicação Inteligente
- Verifica transações por **data + valor** na sheet `T_EXTRATO`
- Evita duplicatas
- Recupera IDs de transações já existentes (fallback recovery)

### Fase 6.75: Escrita em Google Sheets
- Escreve transações novas em `T_EXTRATO`
- Aplica formatação e validação
- Gera IDs sequenciais (EXT0000NNNNN)

### Fase 7: Transferência + Matching (Integrado)
**Opção 1:** Transferência simples para `CONTAORDEM`
- Copia dados de T_EXTRATO para CONTAORDEM
- Marca transações como "Transferido"

**Opção 2:** Transferência + Matching (se `enable_matching=true`)
- Transfere para CONTAORDEM
- Faz matching com sheet `CONSTANTES`
- Preenchimento automático de campos adicionais
- Numeração sequencial para DESCRIÇÃO SOMA

### Fase 8: Atualização de Saldo de Caixa (Opcional)
- Atualiza saldo em `GERENCIAR CAIXAS`
- Proteção contra regressão de saldo (para arquivos históricos)
- Descoberta automática de coluna por rótulo de conta

### Fase 9: Arquivamento de Email (Opcional)
- Move email da INBOX para pasta de backup
- Preserva rastreabilidade

## 🔧 Serviços Especializados

```
processes/extrato/
├── attachment_processor.py          → Extrai conteúdo do email
├── smart_deduplication_service.py  → Evita duplicatas inteligentemente
├── transaction_recovery_service.py → Recupera IDs de transações existentes
├── sheets_writer.py                → Escreve transações em T_EXTRATO
├── transfer_service.py             → Transfere para CONTAORDEM (simples)
├── transfer_matching_service.py    → Transfere + faz matching integrado
├── cash_balance_service.py         → Atualiza saldo de caixa
└── matching_service.py             → Lógica de matching com CONSTANTES
```

## 📊 Fluxo de Dados

```
Gmail API
    ↓
[AttachmentProcessor] → baixa MT940
    ↓
[MT940Parser] → extrai transações
    ↓
[SmartDeduplicationService] → verifica duplicatas
    ↓
[TransactionRecoveryService] → recupera IDs parciais
    ↓
[SheetsWriter] → escreve em T_EXTRATO
    ↓
[TransferService] ou [TransferMatchingService]
    ↓
[MatchingService] → (opcional) matching com CONSTANTES
    ↓
[CashBalanceService] → (opcional) atualiza saldo
    ↓
[Archive] → move email para backup
    ↓
Google Sheets
```

## 🎯 Características Principais

### Idempotência
- Recupera transações já escritas
- Reutiliza IDs do run anterior
- Permite re-execução segura

### Deduplicação Inteligente
- Filtra por data (eficiente)
- Valida valor + descrição
- Cache em memória

### Matching Automático
- Busca em sheet `CONSTANTES`
- Preenche campos adicionais automaticamente
- Numeração sequencial (N001, N002...)

### Proteção de Saldo
- Detecta arquivos históricos
- Impede regressão de saldo
- Verifica após escrita

## 🚀 Uso Direto (sem Orquestrador)

```python
from src.gmail_to_sheets.processes.extrato.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.clients.gmail_client import GmailClient

processor = AttachmentProcessor(gmail_client)
mt940_file = processor.process_attachment(
    message_id="abc123",
    attachment_id="def456",
    filename="extract.txt"
)
```

## 📝 Notas

- Services originalmente em `src/gmail_to_sheets/services/` foram reorganizados para `src/gmail_to_sheets/processes/extrato/`
- Imports devem ser atualizados: `from src.gmail_to_sheets.processes.extrato.X` ao invés de `from src.gmail_to_sheets.services.X`
- Serviços genéricos (batch_writer, batch_updater, etc) permanecem em `services/`
