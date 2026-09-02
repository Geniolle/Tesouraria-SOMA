from unittest.mock import Mock

from src.gmail_to_sheets.services.contaordem_sequence import (
    ContaOrdemSequenceService,
    build_descricao_soma,
    strip_sequence_suffix,
)

HEADERS = ["DATA MOV.", "DESCRIÇÃO SOMA", "PROCESSO"]


def _client(rows):
    client = Mock()

    def values_get(spreadsheetId, range):
        return Mock(execute=Mock(return_value={"values": rows}))

    client.service = Mock()
    client.service.spreadsheets.return_value.values.return_value.get.side_effect = (
        values_get
    )
    return client


class TestStripSequenceSuffix:
    def test_removes_trailing_suffix(self):
        assert strip_sequence_suffix("COMPRA X N001") == "COMPRA X"
        assert strip_sequence_suffix("COMPRA X  N123 ") == "COMPRA X"

    def test_leaves_text_without_suffix(self):
        assert strip_sequence_suffix("COMPRA X") == "COMPRA X"
        assert strip_sequence_suffix("") == ""
        assert strip_sequence_suffix(None) == ""


class TestBuildDescricaoSoma:
    def test_appends_zero_padded_suffix(self):
        assert build_descricao_soma("COMPRA X", 7) == "COMPRA X N007"

    def test_replaces_existing_suffix(self):
        assert build_descricao_soma("COMPRA X N001", 12) == "COMPRA X N012"


class TestContaOrdemSequenceService:
    def test_next_number_per_day_and_processo(self):
        rows = [
            ["30/08/2026", "BASE N002", "SAÍDAS"],
            ["30/08/2026", "BASE N005", "SAÍDAS"],
            ["30/08/2026", "BASE N009", "VC_VENDAS"],
            ["31/08/2026", "BASE N001", "SAÍDAS"],
        ]
        seq = ContaOrdemSequenceService(
            _client(rows), "sheet-1", HEADERS, "SAÍDAS"
        )

        assert seq.next_for("30/08/2026") == 6
        assert seq.next_for("30/08/2026") == 7
        assert seq.next_for("31/08/2026") == 2
        assert seq.next_for("01/09/2026") == 1

    def test_ignores_other_processo_and_starts_at_one(self):
        rows = [["30/08/2026", "BASE N009", "VC_VENDAS"]]
        seq = ContaOrdemSequenceService(
            _client(rows), "sheet-1", HEADERS, "SAÍDAS"
        )

        assert seq.next_for("30/08/2026") == 1
