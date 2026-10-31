from decimal import Decimal

import pytest

from src.gmail_to_sheets.processes.financial_duplicate_audit.engine import (
    audit_group,
    group_repeated_amounts,
    normalize_amount,
    select_period_rows,
)
from src.gmail_to_sheets.processes.financial_duplicate_audit.models import Classification
from src.gmail_to_sheets.processes.financial_duplicate_audit.origins import (
    ORIGIN_SPECS,
    canonicalize_source,
)


def test_normalize_amount_accepts_portuguese_money() -> None:
    assert normalize_amount("1.234,56 €") == Decimal("1234.56")
    assert normalize_amount("-42,10") == Decimal("-42.10")


@pytest.mark.parametrize("value", ["", None, "abc"])
def test_normalize_amount_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="invalid amount"):
        normalize_amount(value)


def test_select_period_rows_keeps_all_statuses_and_reports_invalid_dates() -> None:
    rows = [
        (2, {"DATA MOV.": "01/10/2026", "SOMA": "VALIDADO"}),
        (3, {"DATA MOV.": "31/10/2026", "SOMA": ""}),
        (4, {"DATA MOV.": "01/11/2026", "SOMA": ""}),
        (5, {"DATA MOV.": "not-a-date", "SOMA": ""}),
    ]

    selected, invalid = select_period_rows(rows, year=2026, month=10)

    assert [row_number for row_number, _ in selected] == [2, 3]
    assert invalid == [(5, "not-a-date")]


def test_group_repeated_amounts_separates_types_and_sorts_amount_descending() -> None:
    rows = [
        (2, {"TIPO": "Entrada", "IMPORTÂNCIA": "10,00"}),
        (3, {"TIPO": "Entrada", "IMPORTÂNCIA": "10.00"}),
        (4, {"TIPO": "Entrada", "IMPORTÂNCIA": "20,00"}),
        (5, {"TIPO": "Entrada", "IMPORTÂNCIA": "20,00"}),
        (6, {"TIPO": "Saída", "IMPORTÂNCIA": "20,00"}),
        (7, {"TIPO": "Saída", "IMPORTÂNCIA": "20,00"}),
    ]

    groups, invalid = group_repeated_amounts(rows)

    assert [(group.movement_type, group.amount) for group in groups] == [
        ("Entrada", Decimal("20.00")),
        ("Entrada", Decimal("10.00")),
        ("Saída", Decimal("20.00")),
    ]
    assert [[item.row_number for item in group.occurrences] for group in groups] == [
        [4, 5],
        [2, 3],
        [6, 7],
    ]
    assert invalid == []


def test_classifications_are_stable_report_values() -> None:
    assert [item.value for item in Classification] == [
        "VALIDADO",
        "POSSÍVEL DUPLICADO",
        "DIVERGÊNCIA DE PERÍODO",
        "DIVERGÊNCIA DE VALOR",
        "EM FALTA",
        "INCONCLUSIVO",
    ]


@pytest.mark.parametrize(
    ("process", "row", "expected"),
    [
        (
            "T_EXTRATO",
            {"ID_INTERNO": "EXT1", "DATA MOV.": "02/10/2026", "DESCRIÇÃO": "Depósito", "IMPORTÂNCIA": "10,00"},
            ("02/10/2026", "Depósito", Decimal("10.00")),
        ),
        (
            "DÍZIMOS/OFERTAS",
            {"ID_INTERNO": "ENT1", "DATA": "03/10/2026", "NÚMERO DOCUMENTO": "42", "VALOR": "20,00"},
            ("03/10/2026", "42 - DÍZIMOS E OFERTAS (CULTO)", Decimal("20.00")),
        ),
        (
            "SAÍDAS",
            {"ID_INTERNO": "SAI1", "DATA": "04/10/2026", "DATA VALOR": "05/10/2026", "DESCRIÇÃO DA COMPRA": "Água", "VALOR DA COMPRA": "30,00"},
            ("04/10/2026", "Água", Decimal("30.00")),
        ),
        (
            "VC_VENDAS",
            {"ID_INTERNO": "VC1", "DATA": "05/10/2026", "TIPO": "Venda", "VALOR A PAGAR": "40,00"},
            ("05/10/2026", "Venda VC1", Decimal("40.00")),
        ),
        (
            "FINANCEIRO",
            {"ID_INTERNO": "FIN1", "DATA": "06/10/2026", "TIPO": "Fornecedor", "MONTANTE": "50,00"},
            ("06/10/2026", "Fornecedor FIN1", Decimal("50.00")),
        ),
    ],
)
def test_origin_specs_reuse_real_source_mappings(process, row, expected) -> None:
    canonical = canonicalize_source(ORIGIN_SPECS[process], row)
    assert (canonical["DATA MOV."], canonical["DESCRIÇÃO"], canonical["IMPORTÂNCIA"]) == expected


def _group_row(row_number: int, **changes: object):
    row = {
        "TIPO": "Entrada",
        "IMPORTÂNCIA": "10,00",
        "DATA MOV.": "02/10/2026",
        "DESCRIÇÃO": "Depósito",
        "PROCESSO": "T_EXTRATO",
        "ID_INTERNO": f"EXT{row_number}",
        "DOC. SOMA": "1234567",
    }
    row.update(changes)
    return row_number, row


def test_audit_group_validates_unique_matching_occurrences() -> None:
    groups, _ = group_repeated_amounts([_group_row(2), _group_row(3)])
    sources = {
        "T_EXTRATO": [
            (20, {**_group_row(2)[1]}),
            (21, {**_group_row(3)[1]}),
        ]
    }
    assert [item.classification for item in audit_group(groups[0], sources)] == [
        Classification.VALIDATED,
        Classification.VALIDATED,
    ]


def test_audit_group_marks_two_target_rows_for_one_source_as_possible_duplicate() -> None:
    rows = [_group_row(2, ID_INTERNO="EXT1"), _group_row(3, ID_INTERNO="EXT1")]
    groups, _ = group_repeated_amounts(rows)
    sources = {"T_EXTRATO": [(20, {**rows[0][1]})]}
    assert {item.classification for item in audit_group(groups[0], sources)} == {
        Classification.POSSIBLE_DUPLICATE
    }


@pytest.mark.parametrize(
    ("target_change", "source_change", "expected"),
    [
        ({"DATA MOV.": "02/10/2026"}, {"DATA MOV.": "30/09/2026", "DATA VALOR": "02/10/2026"}, Classification.PERIOD_DIVERGENCE),
        ({"DATA MOV.": "02/10/2026"}, {"DATA MOV.": "30/09/2026", "PERÍODO EXTRATO": "09/2026"}, Classification.PERIOD_DIVERGENCE),
        ({"IMPORTÂNCIA": "10,00"}, {"IMPORTÂNCIA": "11,00"}, Classification.AMOUNT_DIVERGENCE),
        ({"DESCRIÇÃO": "Depósito"}, {"DESCRIÇÃO": "Outra"}, Classification.INCONCLUSIVE),
    ],
)
def test_audit_group_classifies_field_divergences(target_change, source_change, expected) -> None:
    rows = [_group_row(2, **target_change), _group_row(3, ID_INTERNO="EXT3")]
    groups, _ = group_repeated_amounts(rows)
    source = {**rows[0][1], **source_change}
    sources = {"T_EXTRATO": [(20, source), (21, {**rows[1][1]})]}
    findings = audit_group(groups[0], sources)
    assert findings[0].classification == expected


def test_audit_group_reports_missing_ambiguous_unknown_and_empty_identifiers() -> None:
    rows = [
        _group_row(2, ID_INTERNO="MISSING"),
        _group_row(3, ID_INTERNO="AMB"),
        _group_row(4, PROCESSO="UNKNOWN"),
        _group_row(5, ID_INTERNO=""),
    ]
    groups, _ = group_repeated_amounts(rows)
    sources = {
        "T_EXTRATO": [
            (20, {**rows[1][1]}),
            (21, {**rows[1][1]}),
        ]
    }
    findings = audit_group(groups[0], sources)
    assert [item.classification for item in findings] == [
        Classification.MISSING,
        Classification.INCONCLUSIVE,
        Classification.INCONCLUSIVE,
        Classification.INCONCLUSIVE,
    ]
