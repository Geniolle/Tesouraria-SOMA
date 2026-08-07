# Processo de Conciliação

## Overview

O processo de **Conciliação** valida e preenche o campo `DOC.SOMA` em sheets de origem (como `T_EXTRATO`) pesquisando correspondências em `CONTAORDEM`.

**Objetivo:** Reconciliar registros entre múltiplas sheets usando `ID_INTERNO` como chave.

## Pipeline

```
1. Autenticação com Sheets API
2. Carregamento e validação de candidatos
   - DOC.SOMA deve estar vazio
   - ID_INTERNO deve estar preenchido
3. Carregamento de dados de referência (CONTAORDEM)
4. Conciliação
   - Lookup de ID_INTERNO em CONTAORDEM
   - Validação de formato DOC.SOMA (7 dígitos)
   - Batch update em sheet de origem
```

## Arquitetura

### Services

#### `ConciliationValidator`
Valida se um registro é candidato para conciliação:
- Verifica se `DOC.SOMA` está vazio
- Verifica se `ID_INTERNO` está preenchido
- Extrai chave de busca

#### `LookupService`
Pesquisa dados em `CONTAORDEM`:
- Carrega e indexa todos os dados
- Lookup rápido por `ID_INTERNO`
- Validação de formato `DOC.SOMA` (7 dígitos numéricos)

#### `ReconciliationService`
Escreve dados na sheet de origem:
- Batch updates para performance
- Operações imediatas (single cell) para testes
- Rastreamento de atualizações

#### `ConciliationOrchestrator`
Coordena o pipeline completo:
- Manage lifecycle de services
- Logging estruturado
- Error handling

## Uso

### Básico

```python
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator

orchestrator = ConciliationOrchestrator(source_sheet="T_EXTRATO")
orchestrator.run()
```

### Com sheet customizado

```python
from src.gmail_to_sheets.processes.conciliacao.orchestrator import run_conciliation_process

run_conciliation_process(source_sheet="OUTRA_SHEET")
```

### CLI

```bash
python -m src.gmail_to_sheets.processes.conciliacao.orchestrator
```

## Configuração

### Column Indices

**T_EXTRATO (sheet de origem):**
- Coluna 11 (índice 10): `DOC.SOMA`
- Coluna 15 (índice 14): `ID_INTERNO`

**CONTAORDEM (referência):**
- Coluna 3 (índice 2): `DOC.SOMA`
- Coluna 15 (índice 14): `ID_INTERNO`

### Formato DOC.SOMA

- **Tipo:** Numérico
- **Comprimento:** 7 dígitos
- **Exemplo:** `5408307`

## Fluxo Detalhado

### Phase 1: Validação de Candidatos

Para cada linha em `T_EXTRATO` (começando em linha 2):

1. Verifica se `DOC.SOMA` está vazio
2. Verifica se `ID_INTERNO` está preenchido
3. Se ambas condições forem verdadeiras, adiciona à lista de candidatos

### Phase 2: Lookup em CONTAORDEM

Para cada candidato:

1. Extrai `ID_INTERNO`
2. Pesquisa em cache de `CONTAORDEM`
3. Se encontrado, obtém `DOC.SOMA`
4. Valida formato (7 dígitos numéricos)

### Phase 3: Batch Update

Se validação passou:

1. Adiciona à fila de atualizações
2. Após processar todos, aplica em batch (única chamada API)
3. Registra resultado

## Exemplo de Fluxo

```
T_EXTRATO (linha 5):
  ID_INTERNO: "ABC123"
  DOC.SOMA: [vazio] ← Candidato para conciliação

CONTAORDEM (lookup por ID_INTERNO):
  ID_INTERNO: "ABC123"
  DOC.SOMA: "5408307" ← Encontrado e válido

Resultado:
  T_EXTRATO linha 5 atualizada com DOC.SOMA = "5408307"
```

## Logging

O processo gera logs detalhados:

```
[1/4] Autenticando com Google Sheets...
[2/4] Carregando e validando registros...
[3/4] Carregando dados de referência...
[4/4] Realizando conciliação...
```

Cada operação é registrada com:
- Timestamp
- Nível (INFO, DEBUG, WARNING, ERROR)
- Contexto (linha, ID_INTERNO, status)

## Tratamento de Erros

### Candidato não encontrado em CONTAORDEM
- Contabilizado em `not_found`
- Registro não é atualizado
- Pode ser processado novamente em próxima execução

### DOC.SOMA em formato inválido
- Contabilizado em `invalid_format`
- Registro não é atualizado
- Log de aviso com valor rejeitado

### Falha na atualização
- Falha isolada (não impacta outros registros)
- Contabilizado em resultado final
- Pode ser retry em próxima execução

## Extensibilidade

Para adicionar conciliação em nova sheet:

```python
run_conciliation_process(source_sheet="NOVA_SHEET")
```

Basta que a sheet tenha:
- Coluna 11: `DOC.SOMA`
- Coluna 15: `ID_INTERNO`

Se as colunas forem diferentes, customize em `ConciliationValidator` e `ReconciliationService`.

## Roadmap

- [ ] Suporte a múltiplos campos de lookup (não apenas ID_INTERNO)
- [ ] Histórico de conciliações (audit trail)
- [ ] Validação de dados antes/depois
- [ ] Scheduler automático (integração com Entradas)
- [ ] Reconciliação bidirecional
