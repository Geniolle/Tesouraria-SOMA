# Auditoria Financeira de Duplicados — Desenho

## Objetivo

Auditar, em modo exclusivamente de leitura, movimentos repetidos da `CONTAORDEM` contra as folhas de origem. A primeira execução cobre outubro de 2026.

## Limites de segurança

- `DRY_RUN=true` e `APPLY=false`.
- Nenhuma escrita no Google Sheets ou noutro sistema financeiro.
- Nenhuma correção automática.
- Todos os registos do período entram na análise, independentemente dos campos de estado.
- Cabeçalhos identificam colunas; nunca usar posições fixas.

## Reutilização

O fluxo reutiliza:

- `SheetsClient` para leituras autenticadas.
- `ORIGIN_SPECS` e `OriginAuditSpec` de `processes/origem_audit/specs.py` para mapear `PROCESSO`, folha, spreadsheet e adaptação canónica.
- Normalizações existentes de texto, data e valor quando compatíveis.
- `Decimal` para valores monetários.

Não será criada nova integração com Google Sheets.

## Seleção e agrupamento

1. Ler cabeçalhos e linhas atuais de `CONTAORDEM`.
2. Validar cabeçalhos obrigatórios sem depender da posição.
3. Selecionar `DATA MOV.` pertencente ao ano e mês solicitados.
4. Preservar linhas com campos de estado preenchidos ou vazios.
5. Normalizar `IMPORTÂNCIA` com `Decimal`.
6. Agrupar por `TIPO` e valor normalizado.
7. Investigar apenas grupos com pelo menos duas ocorrências.
8. Ordenar tipos e valores, com valores em ordem decrescente.

Datas ou valores inválidos ficam como evidência inconclusiva. Não serão atribuídos arbitrariamente ao período.

## Resolução da origem

O `PROCESSO` da `CONTAORDEM` seleciona uma especificação existente:

- `T_EXTRATO` → `T_EXTRATO`.
- `DÍZIMOS/OFERTAS` → `DÍZIMOS/OFERTAS`.
- `SAÍDAS` → `SAÍDAS`.
- `VC_VENDAS` → `VC_VENDAS` no spreadsheet Verbo Café.
- `FINANCEIRO` → `Financeiro` no spreadsheet Verbo Café.

Processos desconhecidos não serão adivinhados. O resultado será `INCONCLUSIVO`.

## Comparação

Cada ocorrência repetida é comparada com a origem aplicável usando:

- `PROCESSO`.
- `ID_INTERNO`.
- `IMPORTÂNCIA`.
- `DATA MOV.`.
- `DESCRIÇÃO`.
- Identificadores adicionais expostos pela origem, incluindo `DOC. SOMA` quando disponível.

`ID_INTERNO` é a chave principal de prova quando existe e é único. Valor igual nunca prova duplicação sozinho.

## Período incorreto

Uma divergência de data exige investigação adicional. O fluxo considera, quando presentes:

- `DATA VALOR`.
- Data original da origem.
- Período ou número do extrato.
- Registos adjacentes e históricos carregados da mesma origem.

Só classifica `DIVERGÊNCIA DE PERÍODO` quando a evidência demonstra que o movimento pertence a outro período. Sem prova suficiente, classifica `INCONCLUSIVO`.

## Classificações

- `VALIDADO`: ocorrência única e coerente com a origem.
- `POSSÍVEL DUPLICADO`: duas ou mais ocorrências concorrentes apontam para o mesmo movimento de origem.
- `DIVERGÊNCIA DE PERÍODO`: origem inequívoca, mas período da `CONTAORDEM` está errado.
- `DIVERGÊNCIA DE VALOR`: origem inequívoca, mas valor diverge.
- `EM FALTA`: origem esperada não foi encontrada.
- `INCONCLUSIVO`: processo desconhecido, chave ambígua, dados inválidos ou evidência insuficiente.

## Saídas

Diretório por execução: `logs/financial_duplicate_audit/2026-10/`.

- `audit.json`: resultado estruturado completo.
- `audit.md`: relatório humano por ano, mês, tipo e valor decrescente.
- `correction_plan.json`: plano separado, sem autorização de escrita.

Cada ocorrência inclui linha, campos da `CONTAORDEM`, origem consultada, candidatos, diferenças, classificação e justificação. O resumo inclui contagens e impacto financeiro potencial sem somar grupos ambíguos como perda confirmada.

## Interface

CLI manual:

```powershell
.\.venv\Scripts\python.exe -m src.gmail_to_sheets.processes.financial_duplicate_audit.cli --ano 2026 --mes 10 --dry-run
```

Ausência de `--dry-run` não ativa escrita. Esta primeira versão não oferece `--apply`.

## Verificação

Testes cobrem seleção mensal, normalização monetária, grupos repetidos, origens diferentes, duplicidade comprovada, divergências de período e valor, ausência, ambiguidade e garantia de zero escritas.

