# Verbo Café Process

Imports Verbo Café movements from a spreadsheet that is **separate** from
the main treasury spreadsheet into `CONTAORDEM`. Replaces the legacy Apps
Scripts `ImportarVendas_VerboCafe_Dinheiro_v6` and
`ImportarPagamentos_VerboCafe_Dinheiro_v5`.

## Configuration (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `VERBO_CAFE_SOURCE_SPREADSHEET_ID` | legacy Verbo Café id | Spreadsheet holding `VC_VENDAS` / `Financeiro` |
| `VERBO_CAFE_VENDAS_SHEET_NAME` | `VC_VENDAS` | Sales source sheet |
| `VERBO_CAFE_PAGAMENTOS_SHEET_NAME` | `Financeiro` | Supplier-payments source sheet |
| `VERBO_CAFE_SERVICE_ACCOUNT_PATH` | *(blank)* | Optional dedicated credentials; blank reuses `SHEETS_SERVICE_ACCOUNT_PATH` |

The Sheets service account must have **Editor** access to the source
spreadsheet: rows are read **and** their status is written back. Every other
value (fixed CONTAORDEM fields, filters) is a business constant in
`config.py`.

## Phases

| Phase | Source sheet | Amount column | CONTAORDEM `TIPO` | `PROCESSO` |
|-------|--------------|---------------|-------------------|------------|
| Vendas | `VC_VENDAS` | `VALOR A PAGAR` | `Entrada` | `VC_VENDAS` |
| Pagamentos | `Financeiro` | `MONTANTE` | `Saída` | `FINANCEIRO` |

Both run in one managed process (`VerboCafe`, priority 35), vendas first.

## Pending criteria (per source row)

- `STATUS DA TESOURARIA` = `EM ABERTO` (accent/case-insensitive)
- Vendas only: `FORMA DE PAGAMENTO` = `DINHEIRO`
- `DATA` present and parseable
- amount column > 0
- `ID_INTERNO` filled
- not already in `CONTAORDEM` (by `ID_INTERNO` or the
  `DATA + IMPORTÂNCIA + DESCRIÇÃO` business key)

## Transfer mapping (both phases)

| CONTAORDEM | Value |
|------------|-------|
| `DATA MOV.` | source `DATA` normalized to `dd/MM/yyyy` |
| `DESCRIÇÃO` | `"<TIPO da origem> <ID_INTERNO>"` |
| `IMPORTÂNCIA` | amount formatted `1234,56` |
| `TIPO` | `Entrada` (vendas) / `Saída` (pagamentos) |
| `PLANO DE CONTA` | `RECEITAS DE LANCHONETE` / `FORNECEDORES LANCHONETE` |
| `CENTRO DE CUSTO` | `10.10.05 - VERBO CAFE` |
| `DESCRIÇÃO SOMA` | `"<base> N###"` — per-day, per-`PROCESSO` sequence |
| `FORMA DE PAGAMENTO` | `DINHEIRO` |
| `CAIXA` | `VERBO CAFÉ` |
| `PERÍODO` | month name, uppercase (e.g. `AGOSTO`) |
| `PROCESSO` | `VC_VENDAS` / `FINANCEIRO` |
| `ID_INTERNO` | copied from source |

## Completion

After a successful append the source row's `STATUS DA TESOURARIA` is set
to `CONCLUÍDO`, which keeps it out of future runs. `CONTAORDEM` is sorted
by `DATA MOV.` descending at the end (also enforced centrally).

## Manual run

```
python -m src.gmail_to_sheets.app verbo-cafe
```
