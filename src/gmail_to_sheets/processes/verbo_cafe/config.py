"""Static configuration for the two Verbo Café phases.

Both phases read from a spreadsheet that is separate from the main treasury
spreadsheet and append rows to ``CONTAORDEM``. The only things that differ
between "vendas" (sales, an ``Entrada``) and "pagamentos" (supplier payments,
a ``Saída``) are the source sheet, the amount column and a handful of fixed
CONTAORDEM values.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

TARGET_SHEET = "CONTAORDEM"

# Source status lifecycle (compared accent/case-insensitively).
STATUS_OPEN = "EM ABERTO"
STATUS_DONE = "CONCLUÍDO"

# Only cash rows are imported today (mirrors the "_Dinheiro_" scripts).
CASH_PAYMENT_METHOD = "DINHEIRO"

STATUS_FIELD = "STATUS DA TESOURARIA"


@dataclass(frozen=True)
class VerboCafePhase:
    """Everything the orchestrator needs to run one Verbo Café phase."""

    key: str
    source_sheet: str
    required_headers: tuple[str, ...]
    amount_field: str
    filter_cash: bool
    target_type: str
    plano_conta: str
    centro_custo: str
    desc_soma_base: str
    forma_pagamento: str
    caixa: str
    processo_tag: str
    # Source fields used to build the CONTAORDEM description / dedup key.
    tipo_field: str = "TIPO"
    id_field: str = "ID_INTERNO"
    data_field: str = "DATA"


VENDAS = VerboCafePhase(
    key="vendas",
    source_sheet="VC_VENDAS",
    required_headers=(
        "STATUS DA TESOURARIA",
        "FORMA DE PAGAMENTO",
        "DATA",
        "TIPO",
        "ID_INTERNO",
        "VALOR A PAGAR",
    ),
    amount_field="VALOR A PAGAR",
    filter_cash=True,
    target_type="Entrada",
    plano_conta="RECEITAS DE LANCHONETE",
    centro_custo="10.10.05 - VERBO CAFE",
    desc_soma_base="VENDA DA CANTINA (VERBO CAFÉ)",
    forma_pagamento="DINHEIRO",
    caixa="VERBO CAFÉ",
    processo_tag="VC_VENDAS",
)

PAGAMENTOS = VerboCafePhase(
    key="pagamentos",
    source_sheet="Financeiro",
    required_headers=(
        "STATUS DA TESOURARIA",
        "DATA",
        "TIPO",
        "ID_INTERNO",
        "MONTANTE",
    ),
    amount_field="MONTANTE",
    filter_cash=False,
    target_type="Saída",
    plano_conta="FORNECEDORES LANCHONETE",
    centro_custo="10.10.05 - VERBO CAFE",
    desc_soma_base="PAGAMENTO FORNECEDOR (VERBO CAFÉ)",
    forma_pagamento="DINHEIRO",
    caixa="VERBO CAFÉ",
    processo_tag="FINANCEIRO",
)

PHASES: tuple[VerboCafePhase, ...] = (VENDAS, PAGAMENTOS)


def resolve_phases(settings) -> tuple[VerboCafePhase, ...]:
    """Return the phases with source sheet names taken from settings.

    Only the source sheet names are configurable (``VERBO_CAFE_*_SHEET_NAME``);
    every other value is a business constant kept in this module.
    """
    verbo_cafe = settings.verbo_cafe
    return (
        replace(VENDAS, source_sheet=verbo_cafe.vendas_sheet_name),
        replace(PAGAMENTOS, source_sheet=verbo_cafe.pagamentos_sheet_name),
    )
