from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.orchestration.models import ProcessContext
from src.gmail_to_sheets.orchestration.processes import VerboCafeProcess
from src.gmail_to_sheets.processes.verbo_cafe._format import (
    format_amount_pt,
    format_date_ddmmyyyy,
    month_name_pt,
    strip_accents_upper,
    to_number,
)
from src.gmail_to_sheets.processes.verbo_cafe.config import PAGAMENTOS, VENDAS
from src.gmail_to_sheets.processes.verbo_cafe.daily_sequence import (
    DailySequenceService,
)
from src.gmail_to_sheets.processes.verbo_cafe.status_updater import (
    VerboCafeStatusUpdater,
)
from src.gmail_to_sheets.processes.verbo_cafe.transfer_service import (
    VerboCafeTransferService,
)
from src.gmail_to_sheets.processes.verbo_cafe.validator import (
    VerboCafeValidator,
    VerboCafeValidatorError,
)

VENDAS_HEADERS = [
    "STATUS DA TESOURARIA",
    "FORMA DE PAGAMENTO",
    "DATA",
    "TIPO",
    "ID_INTERNO",
    "VALOR A PAGAR",
]

FINANCEIRO_HEADERS = [
    "STATUS DA TESOURARIA",
    "DATA",
    "TIPO",
    "ID_INTERNO",
    "MONTANTE",
]

TARGET_HEADERS = [
    "DATA MOV.",
    "DESCRIÇÃO",
    "IMPORTÂNCIA",
    "TIPO",
    "PLANO DE CONTA",
    "CENTRO DE CUSTO",
    "DESCRIÇÃO SOMA",
    "FORMA DE PAGAMENTO",
    "CAIXA",
    "PERÍODO",
    "PROCESSO",
    "ID_INTERNO",
]


def _vendas_row(**overrides):
    values = {
        "STATUS DA TESOURARIA": "EM ABERTO",
        "FORMA DE PAGAMENTO": "DINHEIRO",
        "DATA": "30/08/2026",
        "TIPO": "VENDA",
        "ID_INTERNO": "VC0000000010",
        "VALOR A PAGAR": "12,50",
    }
    values.update(overrides)
    return [values.get(h, "") for h in VENDAS_HEADERS]


def _financeiro_row(**overrides):
    values = {
        "STATUS DA TESOURARIA": "EM ABERTO",
        "DATA": "30/08/2026",
        "TIPO": "PAGAMENTO",
        "ID_INTERNO": "FIN0000000007",
        "MONTANTE": "1.234,56",
    }
    values.update(overrides)
    return [values.get(h, "") for h in FINANCEIRO_HEADERS]


def _sheet_client(headers_by_key, values_by_sheet):
    """headers_by_key: {(spreadsheet_id, sheet): [...]}; values_by_sheet: {sheet: {"values": [...]}}."""
    client = Mock()
    client.get_headers.side_effect = lambda sid, sheet: headers_by_key.get(
        (sid, sheet), headers_by_key.get(sheet, [])
    )

    def values_get(spreadsheetId, range):
        sheet = str(range).split("!", 1)[0].replace("'", "")
        return Mock(
            execute=Mock(
                return_value=values_by_sheet.get(sheet, {"values": []})
            )
        )

    client.service = Mock()
    client.service.spreadsheets.return_value.values.return_value.get.side_effect = (
        values_get
    )
    client.append_rows = Mock(return_value={"updates": {"updatedRows": 1}})
    client.update_cell = Mock()
    return client


def _settings():
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.sheets = Mock()
    settings.sheets.spreadsheet_id = "main-sheet"
    settings.sheets.service_account_path = "/tmp/service.json"
    settings.verbo_cafe = Mock()
    settings.verbo_cafe.source_spreadsheet_id = "verbo-sheet"
    settings.verbo_cafe.vendas_sheet_name = "VC_VENDAS"
    settings.verbo_cafe.pagamentos_sheet_name = "Financeiro"
    settings.verbo_cafe.service_account_path = None
    return settings


class TestFormatHelpers:
    def test_to_number_handles_thousands_and_decimal_comma(self):
        assert to_number("1.234,56") == pytest.approx(1234.56)
        assert to_number("25") == pytest.approx(25.0)
        assert to_number("") == 0.0

    def test_format_amount_pt(self):
        assert format_amount_pt("1.234,56") == "1234,56"
        assert format_amount_pt("25") == "25,00"

    def test_strip_accents_upper(self):
        assert strip_accents_upper("Concluído") == "CONCLUIDO"
        assert strip_accents_upper("  em   aberto ") == "EM ABERTO"

    def test_month_and_date(self):
        assert format_date_ddmmyyyy("2026-08-30") == "30/08/2026"
        assert month_name_pt("30/08/2026") == "AGOSTO"
        assert month_name_pt("") == ""


class TestVerboCafeValidator:
    def test_accepts_open_cash_sale(self):
        validator = VerboCafeValidator(VENDAS, VENDAS_HEADERS)
        assert validator.is_valid_entry(_vendas_row(), 2) == (True, None)

    def test_rejects_non_open_status(self):
        validator = VerboCafeValidator(VENDAS, VENDAS_HEADERS)
        ok, err = validator.is_valid_entry(
            _vendas_row(**{"STATUS DA TESOURARIA": "CONCLUÍDO"}), 2
        )
        assert ok is False
        assert "EM ABERTO" in err

    def test_rejects_non_cash_sale(self):
        validator = VerboCafeValidator(VENDAS, VENDAS_HEADERS)
        ok, err = validator.is_valid_entry(
            _vendas_row(**{"FORMA DE PAGAMENTO": "MULTIBANCO"}), 2
        )
        assert ok is False
        assert "DINHEIRO" in err

    def test_payments_phase_ignores_payment_method(self):
        validator = VerboCafeValidator(PAGAMENTOS, FINANCEIRO_HEADERS)
        assert validator.is_valid_entry(_financeiro_row(), 2) == (True, None)

    def test_rejects_zero_amount_and_bad_date(self):
        validator = VerboCafeValidator(PAGAMENTOS, FINANCEIRO_HEADERS)
        ok, _ = validator.is_valid_entry(
            _financeiro_row(**{"MONTANTE": "0"}), 2
        )
        assert ok is False
        ok, _ = validator.is_valid_entry(
            _financeiro_row(**{"DATA": "not-a-date"}), 2
        )
        assert ok is False

    def test_missing_required_header_raises(self):
        with pytest.raises(VerboCafeValidatorError):
            VerboCafeValidator(VENDAS, ["STATUS DA TESOURARIA", "DATA"])

    def test_build_descricao(self):
        validator = VerboCafeValidator(VENDAS, VENDAS_HEADERS)
        assert validator.build_descricao(_vendas_row()) == "VENDA VC0000000010"


class TestDailySequenceService:
    def _rows(self, rows):
        return {"CONTAORDEM": {"values": rows}}

    def test_extracts_max_per_day_per_processo(self):
        client = _sheet_client(
            {},
            self._rows(
                [
                    # DATA MOV., DESCRIÇÃO, IMPORTÂNCIA, TIPO, PLANO, CC,
                    # DESCRIÇÃO SOMA, FORMA, CAIXA, PERÍODO, PROCESSO, ID
                    ["30/08/2026", "x", "1", "", "", "", "BASE N002",
                     "", "", "", "VC_VENDAS", ""],
                    ["30/08/2026", "x", "1", "", "", "", "BASE N005",
                     "", "", "", "VC_VENDAS", ""],
                    ["30/08/2026", "x", "1", "", "", "", "BASE N009",
                     "", "", "", "FINANCEIRO", ""],
                ]
            ),
        )
        seq = DailySequenceService(
            client, "main-sheet", TARGET_HEADERS, "VC_VENDAS"
        )
        assert seq.next_for("30/08/2026") == 6
        assert seq.next_for("30/08/2026") == 7
        assert seq.next_for("31/08/2026") == 1

    def test_empty_target_starts_at_one(self):
        client = _sheet_client({}, self._rows([]))
        seq = DailySequenceService(
            client, "main-sheet", TARGET_HEADERS, "FINANCEIRO"
        )
        assert seq.next_for("01/01/2026") == 1


class TestVerboCafeTransferService:
    def test_maps_sale_row(self):
        service = VerboCafeTransferService(
            Mock(),
            "main-sheet",
            source_headers=VENDAS_HEADERS,
            target_headers=TARGET_HEADERS,
            phase=VENDAS,
        )
        mapped = dict(
            zip(TARGET_HEADERS, service.build_target_row(_vendas_row(), 1))
        )
        assert mapped["DATA MOV."] == "30/08/2026"
        assert mapped["DESCRIÇÃO"] == "VENDA VC0000000010"
        assert mapped["IMPORTÂNCIA"] == "12,50"
        assert mapped["TIPO"] == "Entrada"
        assert mapped["PLANO DE CONTA"] == "RECEITAS DE LANCHONETE"
        assert mapped["CENTRO DE CUSTO"] == "10.10.05 - VERBO CAFE"
        assert mapped["DESCRIÇÃO SOMA"] == "VENDA DA CANTINA (VERBO CAFÉ) N001"
        assert mapped["FORMA DE PAGAMENTO"] == "DINHEIRO"
        assert mapped["CAIXA"] == "VERBO CAFÉ"
        assert mapped["PERÍODO"] == "AGOSTO"
        assert mapped["PROCESSO"] == "VC_VENDAS"
        assert mapped["ID_INTERNO"] == "VC0000000010"

    def test_maps_payment_row(self):
        service = VerboCafeTransferService(
            Mock(),
            "main-sheet",
            source_headers=FINANCEIRO_HEADERS,
            target_headers=TARGET_HEADERS,
            phase=PAGAMENTOS,
        )
        mapped = dict(
            zip(
                TARGET_HEADERS,
                service.build_target_row(_financeiro_row(), 12),
            )
        )
        assert mapped["TIPO"] == "Saída"
        assert mapped["PLANO DE CONTA"] == "FORNECEDORES LANCHONETE"
        assert mapped["IMPORTÂNCIA"] == "1234,56"
        assert mapped["DESCRIÇÃO SOMA"] == (
            "PAGAMENTO FORNECEDOR (VERBO CAFÉ) N012"
        )
        assert mapped["PROCESSO"] == "FINANCEIRO"


class TestVerboCafeStatusUpdater:
    def test_marks_status_as_concluido_on_source_spreadsheet(self):
        client = Mock()
        updater = VerboCafeStatusUpdater(
            client, "verbo-sheet", VENDAS_HEADERS, VENDAS
        )
        result = updater.mark_batch_as_concluido([5])
        assert result["updated"] == 1
        col = VENDAS_HEADERS.index("STATUS DA TESOURARIA") + 1
        client.update_cell.assert_called_once_with(
            "verbo-sheet", "VC_VENDAS", 5, col, "CONCLUÍDO"
        )


class TestVerboCafeProcessPending:
    def _context(self, sale_rows, payment_rows, is_duplicate=False):
        client = _sheet_client(
            {
                ("verbo-sheet", "VC_VENDAS"): VENDAS_HEADERS,
                ("verbo-sheet", "Financeiro"): FINANCEIRO_HEADERS,
                ("main-sheet", "CONTAORDEM"): [
                    "DATA MOV.",
                    "DESCRIÇÃO",
                    "IMPORTÂNCIA",
                    "ID_INTERNO",
                ],
            },
            {
                "VC_VENDAS": {"values": sale_rows},
                "Financeiro": {"values": payment_rows},
                "CONTAORDEM": {"values": []},
            },
        )
        ctx = ProcessContext(
            settings=_settings(),
            sheets_client=client,
            gmail_client=Mock(),
        )
        return ctx, client

    def test_reports_work_for_first_ready_sale(self, monkeypatch):
        ctx, _ = self._context([_vendas_row()], [])
        monkeypatch.setattr(
            "src.gmail_to_sheets.orchestration.processes."
            "EntryDeduplicationService",
            lambda *a, **k: Mock(is_duplicate=Mock(return_value=False)),
        )
        pending = VerboCafeProcess(ctx).check_pending()
        assert pending.has_work is True
        assert "vendas" in pending.reason

    def test_no_work_when_all_concluido(self, monkeypatch):
        ctx, _ = self._context(
            [_vendas_row(**{"STATUS DA TESOURARIA": "CONCLUÍDO"})],
            [_financeiro_row(**{"STATUS DA TESOURARIA": "CONCLUÍDO"})],
        )
        monkeypatch.setattr(
            "src.gmail_to_sheets.orchestration.processes."
            "EntryDeduplicationService",
            lambda *a, **k: Mock(is_duplicate=Mock(return_value=False)),
        )
        pending = VerboCafeProcess(ctx).check_pending()
        assert pending.has_work is False

    def test_no_work_when_duplicate(self, monkeypatch):
        ctx, _ = self._context([_vendas_row()], [])
        monkeypatch.setattr(
            "src.gmail_to_sheets.orchestration.processes."
            "EntryDeduplicationService",
            lambda *a, **k: Mock(is_duplicate=Mock(return_value=True)),
        )
        pending = VerboCafeProcess(ctx).check_pending()
        assert pending.has_work is False
