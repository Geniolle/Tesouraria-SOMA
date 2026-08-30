from pathlib import Path
from unittest.mock import Mock, patch

from src.gmail_to_sheets.orchestration.models import ProcessContext
from src.gmail_to_sheets.orchestration.processes import (
    ConciliacaoProcess,
    DizimosOfertasProcess,
    EntradasProcess,
    ExtratoProcess,
    SaidasProcess,
)


def _make_settings():
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.gmail = Mock()
    settings.gmail.search_query = "in:inbox has:attachment"
    settings.gmail.client_secrets_path = Path("/tmp/secret.json")
    settings.gmail.credentials_path = Path("/tmp/token.json")
    settings.sheets = Mock()
    settings.sheets.spreadsheet_id = "sheet-123"
    settings.sheets.service_account_path = Path("/tmp/service.json")
    settings.sheets.sheet_name = "T_EXTRATO"
    return settings


def _make_sheet_client(headers_by_sheet, values_by_sheet):
    client = Mock()
    client.get_headers.side_effect = (
        lambda spreadsheet_id, sheet_name: headers_by_sheet.get(
            sheet_name,
            [],
        )
    )

    def values_get(spreadsheetId, range):
        sheet_name = str(range).split("!", 1)[0].replace("'", "")
        payload = values_by_sheet.get(sheet_name, {"values": []})
        return Mock(execute=Mock(return_value=payload))

    client.service = Mock()
    client.service.spreadsheets.return_value.values.return_value.get.side_effect = (
        values_get
    )
    client.append_rows = Mock()
    client.update_cell = Mock()
    return client


class TestProcessContext:
    def test_headers_are_cached_for_service_lifetime(self):
        settings = _make_settings()
        sheet_client = Mock()
        sheet_client.get_headers.return_value = ["A", "B"]
        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        assert context.get_sheet_headers("T_EXTRATO") == ["A", "B"]
        assert context.get_sheet_headers("T_EXTRATO") == ["A", "B"]
        sheet_client.get_headers.assert_called_once_with(
            "sheet-123",
            "T_EXTRATO",
        )


class TestExtratoProcess:
    def test_check_pending_is_read_only_and_uses_one_message(self):
        settings = _make_settings()
        gmail_client = Mock()
        gmail_client.search_messages.return_value = ["msg-1"]
        context = ProcessContext(
            settings=settings,
            gmail_client=gmail_client,
            sheets_client=Mock(),
        )

        pending = ExtratoProcess(context).check_pending()

        assert pending.has_work is True
        assert pending.count == 1
        gmail_client.search_messages.assert_called_once_with(
            query="in:inbox has:attachment",
            max_results=1,
        )
        gmail_client.get_message.assert_not_called()

    def test_check_pending_reports_no_work(self):
        settings = _make_settings()
        gmail_client = Mock()
        gmail_client.search_messages.return_value = []
        context = ProcessContext(
            settings=settings,
            gmail_client=gmail_client,
            sheets_client=Mock(),
        )

        pending = ExtratoProcess(context).check_pending()

        assert pending.has_work is False
        assert pending.count == 0


class TestDizimosOfertasProcess:
    def test_backward_alias_points_to_named_process(self):
        assert EntradasProcess is DizimosOfertasProcess
        assert DizimosOfertasProcess.name == "DizimosOfertas"
        assert DizimosOfertasProcess.priority == 20

    @patch(
        "src.gmail_to_sheets.orchestration.processes."
        "EntryDeduplicationService"
    )
    @patch(
        "src.gmail_to_sheets.orchestration.processes.EntryValidator"
    )
    def test_pending_requires_valid_non_duplicate_row(
        self,
        mock_validator_cls,
        mock_dedup_cls,
    ):
        settings = _make_settings()
        source_headers = [
            "PERIODO",
            "MÊS",
            "DIA DA SEMANA",
            "DATA",
            "TIPO",
            "DOC. SOMA",
            "NÚMERO DOCUMENTO",
            "VALOR",
            "RECIBO",
            "AUXILIAR TESOURARIA1",
            "AUXILIAR TESOURARIA2",
            "AUXILIAR SUBSTITUTO",
            "FINANCE",
            "COMENTÁRIOS",
            "ID_INTERNO",
        ]
        target_headers = [
            "DATA MOV.",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "ID_INTERNO",
        ]
        projected_row = [
            "30/08/2026",
            "DÍZIMOS/OFERTAS",
            "5459999",
            "R260830",
            "70,00",
            "",
            "",
            "",
            "",
            "",
            "",
            "ENT0000000277",
        ]
        sheet_client = _make_sheet_client(
            {
                "DÍZIMOS/OFERTAS": source_headers,
                "CONTAORDEM": target_headers,
            },
            {
                "DÍZIMOS/OFERTAS": {
                    "values": [projected_row],
                },
            },
        )
        validator = Mock()
        validator.column_indices = {
            str(header).upper(): index
            for index, header in enumerate(source_headers)
        }
        validator.is_valid_entry.return_value = (True, None)
        mock_validator_cls.return_value = validator

        dedup = Mock()
        dedup.is_duplicate.return_value = False
        mock_dedup_cls.return_value = dedup

        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = DizimosOfertasProcess(context).check_pending()

        assert pending.has_work is True
        assert pending.count == 1
        dedup.is_duplicate.assert_called_once_with(
            "30/08/2026",
            "70,00",
            "R260830 - DÍZIMOS E OFERTAS (CULTO)",
            id_interno="ENT0000000277",
        )
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()

    @patch(
        "src.gmail_to_sheets.orchestration.processes.EntryValidator"
    )
    def test_no_valid_row_does_not_load_target_dedup(
        self,
        mock_validator_cls,
    ):
        settings = _make_settings()
        headers = [
            "PERIODO",
            "MÊS",
            "DIA DA SEMANA",
            "DATA",
            "TIPO",
            "DOC. SOMA",
            "NÚMERO DOCUMENTO",
            "VALOR",
            "RECIBO",
            "AUXILIAR TESOURARIA1",
            "AUXILIAR TESOURARIA2",
            "AUXILIAR SUBSTITUTO",
            "FINANCE",
            "COMENTÁRIOS",
            "ID_INTERNO",
        ]
        sheet_client = _make_sheet_client(
            {"DÍZIMOS/OFERTAS": headers},
            {
                "DÍZIMOS/OFERTAS": {
                    "values": [["30/08/2026"] + [""] * 11],
                },
            },
        )
        validator = Mock()
        validator.column_indices = {
            str(header).upper(): index
            for index, header in enumerate(headers)
        }
        validator.is_valid_entry.return_value = (
            False,
            "DOC.SOMA vazio",
        )
        mock_validator_cls.return_value = validator

        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = DizimosOfertasProcess(context).check_pending()

        assert pending.has_work is False
        assert "CONTAORDEM" not in context.headers_cache


class TestSaidasProcess:
    @patch(
        "src.gmail_to_sheets.orchestration.processes."
        "EntryDeduplicationService"
    )
    def test_pending_requires_finance_ready_non_duplicate_row(
        self,
        mock_dedup_cls,
    ):
        settings = _make_settings()
        source_headers = [
            "ID_INTERNO",
            "FORMA DE PAGAMENTO",
            "DATA",
            "DATA VALOR",
            "TIPO",
            "DOC. SOMA",
            "Nº RECIBO",
            "VALOR DA COMPRA",
            "DESCRIÇÃO DA COMPRA",
            "NOME RECEBEDOR DO PAGAMENTO",
            "TELEFONE RECEBEDOR",
            "EMAIL RECEBEDOR",
            "NOME DO FORNECEDOR",
            "TELEFONE FORNECEDOR",
            "EMAIL FORNECEDOR",
            "PLANO DE CONTA",
            "CENTRO DE CUSTO",
            "CAIXA",
            "IMAGEM DO RECIBO",
            "STATUS DA TESOURARIA",
            "STATUS PROCESSAMENTO",
            "FINANCE",
        ]
        target_headers = [
            "DATA MOV.",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "ID_INTERNO",
        ]
        source_row = [
            "SAI0000000239",
            "DINHEIRO",
            "30/08/2026",
            "",
            "PAGAMENTO",
            "5459998",
            "FT-1",
            "25,00",
            "MATERIAL DE LIMPEZA",
            "",
            "",
            "",
            "Fornecedor",
            "",
            "",
            "MATERIAL DE LIMPEZA",
            "30.10.10 - MATERIAL DE LIMPEZA",
            "CAIXA DIÁRIO",
            "",
            "Concluído",
            "",
            "",
        ]
        sheet_client = _make_sheet_client(
            {
                "SAÍDAS": source_headers,
                "CONTAORDEM": target_headers,
            },
            {
                "SAÍDAS": {"values": [source_row]},
            },
        )
        dedup = Mock()
        dedup.is_duplicate.return_value = False
        mock_dedup_cls.return_value = dedup

        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = SaidasProcess(context).check_pending()

        assert pending.has_work is True
        assert pending.count == 1
        dedup.is_duplicate.assert_called_once_with(
            "30/08/2026",
            "25,00",
            "MATERIAL DE LIMPEZA",
            id_interno="SAI0000000239",
        )
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()

    @patch(
        "src.gmail_to_sheets.orchestration.processes."
        "EntryDeduplicationService"
    )
    def test_duplicate_saidas_row_is_not_pending(
        self,
        mock_dedup_cls,
    ):
        settings = _make_settings()
        headers = [
            "ID_INTERNO",
            "FORMA DE PAGAMENTO",
            "DATA",
            "DATA VALOR",
            "TIPO",
            "DOC. SOMA",
            "Nº RECIBO",
            "VALOR DA COMPRA",
            "DESCRIÇÃO DA COMPRA",
            "NOME RECEBEDOR DO PAGAMENTO",
            "TELEFONE RECEBEDOR",
            "EMAIL RECEBEDOR",
            "NOME DO FORNECEDOR",
            "TELEFONE FORNECEDOR",
            "EMAIL FORNECEDOR",
            "PLANO DE CONTA",
            "CENTRO DE CUSTO",
            "CAIXA",
            "IMAGEM DO RECIBO",
            "STATUS DA TESOURARIA",
            "STATUS PROCESSAMENTO",
            "FINANCE",
        ]
        row = [
            "SAI0000000239",
            "DINHEIRO",
            "30/08/2026",
            "",
            "PAGAMENTO",
            "5459998",
            "FT-1",
            "25,00",
            "MATERIAL DE LIMPEZA",
            "",
            "",
            "",
            "Fornecedor",
            "",
            "",
            "MATERIAL DE LIMPEZA",
            "PADRÃO",
            "CAIXA DIÁRIO",
            "",
            "Concluído",
            "",
            "",
        ]
        sheet_client = _make_sheet_client(
            {
                "SAÍDAS": headers,
                "CONTAORDEM": [
                    "DATA MOV.",
                    "DESCRIÇÃO",
                    "IMPORTÂNCIA",
                    "ID_INTERNO",
                ],
            },
            {"SAÍDAS": {"values": [row]}},
        )
        dedup = Mock()
        dedup.is_duplicate.return_value = True
        mock_dedup_cls.return_value = dedup

        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = SaidasProcess(context).check_pending()

        assert pending.has_work is False
        assert pending.count == 0


class TestConciliacaoProcess:
    def test_check_pending_skips_without_doc_soma_in_target(self):
        settings = _make_settings()
        sheet_client = _make_sheet_client(
            {
                "T_EXTRATO": ["DOC. SOMA", "ID_INTERNO"],
                "CONTAORDEM": ["ID_INTERNO", "DOC. SOMA"],
            },
            {
                "T_EXTRATO": {
                    "values": [["", "EXT0000000001"]],
                },
                "CONTAORDEM": {
                    "values": [["EXT0000000001", ""]],
                },
            },
        )
        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = ConciliacaoProcess(context).check_pending()

        assert pending.has_work is False
        assert pending.count == 0

    def test_check_pending_runs_when_doc_soma_is_available(self):
        settings = _make_settings()
        sheet_client = _make_sheet_client(
            {
                "T_EXTRATO": ["DOC. SOMA", "ID_INTERNO"],
                "CONTAORDEM": ["ID_INTERNO", "DOC. SOMA"],
            },
            {
                "T_EXTRATO": {
                    "values": [["", "EXT0000000001"]],
                },
                "CONTAORDEM": {
                    "values": [["EXT0000000001", "DOC-1"]],
                },
            },
        )
        context = ProcessContext(
            settings=settings,
            sheets_client=sheet_client,
            gmail_client=Mock(),
        )

        pending = ConciliacaoProcess(context).check_pending()

        assert pending.has_work is True
        assert pending.count == 1
