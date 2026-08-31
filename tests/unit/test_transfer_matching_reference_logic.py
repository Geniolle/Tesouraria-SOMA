from unittest.mock import Mock, patch

from src.gmail_to_sheets.services.transfer_matching_service import TransferMatchingService


def _make_mock_sheets(source_rows, target_rows, ref_rows):
    client = Mock()
    client.get_headers = Mock(side_effect=lambda spreadsheet_id, sheet_name: {
        "T_EXTRATO": [
            "DATA MOV.",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "TIPO",
            "ID_INTERNO",
            "STATUS",
        ],
        "CONTAORDEM": [
            "DATA MOV.",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "TIPO",
            "PERÍODO",
            "PROCESSO",
            "ID_INTERNO",
            "PLANO DE CONTA",
            "CENTRO DE CUSTO",
            "DESCRIÇÃO SOMA",
            "FORMA DE PAGAMENTO",
            "CAIXA",
            "CAIXA SAIDA",
            "DOC. SOMA",
        ],
        "CONSTANTES": [
            "TEXTO",
            "TIPO",
            "VALOR",
            "DOC. SOMA",
            "DESCRIÇÃO SOMA",
            "PLANO DE CONTA",
            "CENTRO DE CUSTO",
            "FORMA DE PAGAMENTO",
            "CAIXA",
            "CAIXA SAIDA",
            "TIMESTAMP",
        ],
    }.get(sheet_name, []))
    client.get_data_range = Mock(side_effect=lambda spreadsheet_id, sheet_name: f"{sheet_name}!A1:Z99999")

    def get_side_effect(spreadsheetId, range):
        if "T_EXTRATO" in range:
            return Mock(execute=Mock(return_value={"values": source_rows}))
        if "CONTAORDEM" in range:
            return Mock(execute=Mock(return_value={"values": target_rows}))
        if "CONSTANTES" in range:
            return Mock(execute=Mock(return_value={"values": ref_rows}))
        return Mock(execute=Mock(return_value={"values": []}))

    client.service = Mock()
    client.service.spreadsheets = Mock(
        return_value=Mock(
            values=Mock(
                return_value=Mock(
                    get=Mock(side_effect=get_side_effect),
                )
            )
        )
    )
    return client


def _target_row_index(headers, column):
    return headers.index(column)


def test_matching_copies_reference_fields_and_keeps_doc_soma_from_constants():
    source_rows = [
        ["04/08/2026", "Pagamento Teste", "100,00", "SAIDA", "EXT0000000001", ""],
    ]
    target_rows = []
    ref_rows = [
        [
            "Pagamento Teste",
            "SAIDA",
            "100,00",
            "DOC123",
            "Base Soma",
            "PC01",
            "CC02",
            "Cartao",
            "Caixa A",
            "Caixa Saida B",
            "31/08/2026 10:00:00",
        ]
    ]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, ref_rows)

    with patch("src.gmail_to_sheets.services.transfer_matching_service.BatchWriter") as mock_batch_writer:
        mock_batch = Mock()
        mock_batch.batch_write_with_updates.return_value = {
            "target_rows_written": 1,
            "status_updates_applied": 1,
            "errors": [],
        }
        mock_batch_writer.return_value = mock_batch

        service = TransferMatchingService(
            mock_sheets,
            "spreadsheet",
            "T_EXTRATO",
            "CONTAORDEM",
            "CONSTANTES",
        )

        result = service.process_with_matching(["EXT0000000001"])

    assert result["matched"] == 1
    assert result["no_match"] == 0

    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers

    assert target_row[_target_row_index(headers, "DOC. SOMA")] == "DOC123"
    assert target_row[_target_row_index(headers, "PLANO DE CONTA")] == "PC01"
    assert target_row[_target_row_index(headers, "CENTRO DE CUSTO")] == "CC02"
    assert target_row[_target_row_index(headers, "FORMA DE PAGAMENTO")] == "Cartao"
    assert target_row[_target_row_index(headers, "CAIXA")] == "Caixa A"
    assert target_row[_target_row_index(headers, "CAIXA SAIDA")] == "Caixa Saida B"
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == "Base Soma N001"


def test_matching_without_reference_leaves_doc_soma_blank():
    source_rows = [
        ["04/08/2026", "Sem Referencia", "50,00", "SAIDA", "EXT0000000002", ""],
    ]
    target_rows = []
    ref_rows = []

    mock_sheets = _make_mock_sheets(source_rows, target_rows, ref_rows)

    with patch("src.gmail_to_sheets.services.transfer_matching_service.BatchWriter") as mock_batch_writer:
        mock_batch = Mock()
        mock_batch.batch_write_with_updates.return_value = {
            "target_rows_written": 1,
            "status_updates_applied": 1,
            "errors": [],
        }
        mock_batch_writer.return_value = mock_batch

        service = TransferMatchingService(
            mock_sheets,
            "spreadsheet",
            "T_EXTRATO",
            "CONTAORDEM",
            "CONSTANTES",
        )

        result = service.process_with_matching(["EXT0000000002"])

    assert result["matched"] == 0
    assert result["no_match"] == 1

    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers
    assert target_row[_target_row_index(headers, "DOC. SOMA")] == ""
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == ""


def test_sequential_description_resets_by_full_date_not_day_month_only():
    source_rows = [
        ["04/08/2026", "Pagamento Ano Novo", "75,00", "SAIDA", "EXT0000000003", ""],
    ]
    target_rows = [
        [
            "04/08/2025",
            "Pagamento Ano Novo",
            "75,00",
            "SAIDA",
            "AGOSTO",
            "T_EXTRATO",
            "EXT0000000999",
            "",
            "",
            "Base Soma N001",
            "",
            "",
            "",
            "DOC999",
        ]
    ]
    ref_rows = [
        [
            "Pagamento Ano Novo",
            "SAIDA",
            "75,00",
            "DOC321",
            "Base Soma",
            "PC09",
            "CC09",
            "Cartao",
            "Caixa C",
            "Caixa Saida D",
            "31/08/2026 11:00:00",
        ]
    ]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, ref_rows)

    with patch("src.gmail_to_sheets.services.transfer_matching_service.BatchWriter") as mock_batch_writer:
        mock_batch = Mock()
        mock_batch.batch_write_with_updates.return_value = {
            "target_rows_written": 1,
            "status_updates_applied": 1,
            "errors": [],
        }
        mock_batch_writer.return_value = mock_batch

        service = TransferMatchingService(
            mock_sheets,
            "spreadsheet",
            "T_EXTRATO",
            "CONTAORDEM",
            "CONSTANTES",
        )

        service.process_with_matching(["EXT0000000003"])

    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == "Base Soma N001"
