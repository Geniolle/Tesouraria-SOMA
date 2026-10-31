from src.gmail_to_sheets.processes.financial_duplicate_audit.models import Classification
from src.gmail_to_sheets.processes.financial_duplicate_audit.runner import (
    FinancialDuplicateAuditRunner,
    rows_from_values,
)


def test_rows_from_values_uses_dynamic_headers() -> None:
    rows = rows_from_values(
        ["IMPORTÂNCIA", "ID_INTERNO", "DATA MOV."],
        [["10,00", "EXT1", "02/10/2026"]],
        {"ID_INTERNO", "DATA MOV.", "IMPORTÂNCIA"},
    )
    assert rows == [
        (2, {"IMPORTÂNCIA": "10,00", "ID_INTERNO": "EXT1", "DATA MOV.": "02/10/2026"})
    ]


def test_rows_from_values_rejects_missing_or_duplicate_headers() -> None:
    for headers, message in [
        (["ID_INTERNO"], "missing headers"),
        (["ID_INTERNO", " id_interno "], "duplicate headers"),
    ]:
        try:
            rows_from_values(headers, [], {"ID_INTERNO", "DATA MOV."})
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("expected ValueError")


def test_runner_reads_only_needed_origins_and_never_writes() -> None:
    calls: list[tuple[str, str]] = []
    sheets = {
        ("main", "CONTAORDEM"): [
            (2, {"TIPO": "Entrada", "IMPORTÂNCIA": "10,00", "DATA MOV.": "02/10/2026", "DESCRIÇÃO": "A", "PROCESSO": "T_EXTRATO", "ID_INTERNO": "E1", "DOC. SOMA": "1"}),
            (3, {"TIPO": "Entrada", "IMPORTÂNCIA": "10,00", "DATA MOV.": "03/10/2026", "DESCRIÇÃO": "B", "PROCESSO": "DÍZIMOS/OFERTAS", "ID_INTERNO": "D1", "DOC. SOMA": "2"}),
            (4, {"TIPO": "Saída", "IMPORTÂNCIA": "5,00", "DATA MOV.": "02/11/2026", "DESCRIÇÃO": "C", "PROCESSO": "SAÍDAS", "ID_INTERNO": "S1", "DOC. SOMA": "3"}),
        ],
        ("main", "T_EXTRATO"): [
            (20, {"ID_INTERNO": "E1", "DATA MOV.": "02/10/2026", "DESCRIÇÃO": "A", "IMPORTÂNCIA": "10,00"})
        ],
        ("main", "DÍZIMOS/OFERTAS"): [
            (30, {"ID_INTERNO": "D1", "DATA": "03/10/2026", "NÚMERO DOCUMENTO": "", "VALOR": "10,00"})
        ],
    }

    def read_sheet(spreadsheet: str, sheet: str, required: frozenset[str]):
        calls.append((spreadsheet, sheet))
        return sheets[(spreadsheet, sheet)]

    runner = FinancialDuplicateAuditRunner(
        object(),
        "main",
        verbo_cafe_spreadsheet_id="verbo",
        read_sheet=read_sheet,
    )
    result = runner.run(year=2026, month=10)

    assert calls == [
        ("main", "CONTAORDEM"),
        ("main", "DÍZIMOS/OFERTAS"),
        ("main", "T_EXTRATO"),
    ]
    assert result.total_rows == 3
    assert result.period_rows == 2
    assert len(result.groups) == 1
    assert [finding.classification for finding in result.findings] == [
        Classification.VALIDATED,
        Classification.INCONCLUSIVE,
    ]
