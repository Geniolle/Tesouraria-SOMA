# Financial Duplicate Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Criar uma auditoria mensal, somente leitura, que investigue valores repetidos da `CONTAORDEM` nas folhas de origem e gere relatório e plano de correção.

**Architecture:** Um novo pacote de workflow usa `SheetsClient` e `ORIGIN_SPECS`. O domínio puro seleciona, agrupa e classifica; o runner apenas lê e entrega dados; o report writer grava artefactos locais.

**Tech Stack:** Python 3.10+, biblioteca padrão, `Decimal`, Google Sheets client existente, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-31-financial-duplicate-audit-design.md`

---

## Task 1: Fixar contratos puros e classificações

**Files:**
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/models.py`
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/engine.py`
- Create: `tests/unit/test_financial_duplicate_audit_engine.py`

1. Escrever testes falhos para valor monetário PT, período, agrupamento por `TIPO`, ordenação decrescente e campos inválidos.
2. Executar o teste isolado e confirmar falha esperada.
3. Implementar dataclasses, enumeração das seis classificações e funções puras mínimas.
4. Executar o teste isolado até passar.
5. Executar `ruff check` nos três ficheiros.

## Task 2: Reutilizar origens e provar correspondências

**Files:**
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/origins.py`
- Modify: `src/gmail_to_sheets/processes/financial_duplicate_audit/engine.py`
- Modify: `tests/unit/test_financial_duplicate_audit_engine.py`

1. Escrever testes falhos para `T_EXTRATO`, `DÍZIMOS/OFERTAS`, `SAÍDAS`, `VC_VENDAS`, `FINANCEIRO` e processo desconhecido.
2. Testar correspondência única, candidatos concorrentes e `ID_INTERNO` ausente.
3. Implementar adaptador fino sobre `ORIGIN_SPECS`; não duplicar adaptadores existentes.
4. Comparar processo, ID, valor, data, descrição e identificadores disponíveis.
5. Executar testes isolados e `ruff check`.

## Task 3: Classificar os dez cenários obrigatórios

**Files:**
- Modify: `src/gmail_to_sheets/processes/financial_duplicate_audit/engine.py`
- Modify: `tests/unit/test_financial_duplicate_audit_engine.py`

1. Adicionar testes para: válido; possível duplicado; período divergente por `DATA VALOR`; período divergente por metadados do extrato; valor divergente; em falta; ambíguo; data inválida; valor inválido; mesmo valor em tipos distintos.
2. Confirmar falhas antes da implementação.
3. Implementar a menor árvore de decisão que produza classificação e evidência.
4. Garantir que igualdade de valor isolada nunca produz duplicado confirmado.
5. Executar testes isolados.

## Task 4: Criar runner de leitura com cabeçalhos dinâmicos

**Files:**
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/runner.py`
- Create: `tests/unit/test_financial_duplicate_audit_runner.py`

1. Escrever testes com serviço Sheets falso para cabeçalhos dinâmicos, dois spreadsheets, período e ausência de escrita.
2. Confirmar que os testes falham.
3. Implementar leituras de `CONTAORDEM` e somente das origens necessárias.
4. Rejeitar cabeçalhos obrigatórios ausentes ou duplicados.
5. Expor resultado em memória sem chamar `append`, `update`, `batchUpdate` ou ordenação.
6. Executar testes isolados e `ruff check`.

## Task 5: Gerar relatórios e plano separado

**Files:**
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/report.py`
- Create: `tests/unit/test_financial_duplicate_audit_report.py`

1. Escrever testes falhos para JSON, Markdown, hierarquia ano/mês/tipo/valor, contagens e impacto potencial.
2. Testar escrita atómica dos três ficheiros e ausência de segredos.
3. Implementar serialização com biblioteca padrão.
4. Manter `correction_plan.json` separado e não executável.
5. Executar testes isolados.

## Task 6: Adicionar CLI segura

**Files:**
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/__init__.py`
- Create: `src/gmail_to_sheets/processes/financial_duplicate_audit/cli.py`
- Create: `tests/unit/test_financial_duplicate_audit_cli.py`

1. Escrever testes falhos para `--ano`, `--mes`, `--dry-run`, mês inválido e falta de dry-run.
2. Implementar CLI que só aceita execução com `--dry-run` e não possui `--apply`.
3. Reutilizar `Settings` e `SheetsClient`; não criar autenticação paralela.
4. Definir saída em `logs/financial_duplicate_audit/AAAA-MM/`.
5. Executar testes isolados.

## Task 7: Verificar qualidade e regressões

**Files:** Nenhuma alteração planeada.

1. Executar testes novos.
2. Executar suite completa com `.\.venv\Scripts\python.exe -m pytest`.
3. Executar `.\.venv\Scripts\python.exe -m ruff check src tests`.
4. Executar `.\.venv\Scripts\python.exe -m mypy src`.
5. Corrigir somente regressões causadas pelo novo pacote.

## Task 8: Executar dry-run real de outubro de 2026

**Files:**
- Create at runtime: `logs/financial_duplicate_audit/2026-10/audit.json`
- Create at runtime: `logs/financial_duplicate_audit/2026-10/audit.md`
- Create at runtime: `logs/financial_duplicate_audit/2026-10/correction_plan.json`

1. Confirmar credenciais e configuração sem imprimir valores sensíveis.
2. Executar a CLI com `--ano 2026 --mes 10 --dry-run`.
3. Verificar nos logs e mocks de fronteira que ocorreram somente leituras.
4. Conferir contagens, classificações, impacto e todas as ocorrências repetidas.
5. Apresentar resultado real e aguardar autorização separada antes de qualquer correção.

## Stop condition

Parar quando testes e gates passarem, os três relatórios de outubro existirem e nenhuma escrita remota tiver ocorrido. Não criar modo apply nesta fase.
