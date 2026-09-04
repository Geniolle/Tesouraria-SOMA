from unittest.mock import Mock, patch

from src.gmail_to_sheets.processes.extrato.transfer_matching_layout import TransferMatchingLayout
from src.gmail_to_sheets.services.batch_updater import CLEAR_CELL
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


def test_matching_without_reference_marks_doc_soma_as_analisar():
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
    assert target_row[_target_row_index(headers, "DOC. SOMA")] == "ANALISAR"
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == ""


def test_matching_ignores_spaces_between_bank_text_and_constants_key():
    # Descritivo cru do banco vem com espaços; a chave da CONSTANTES não tem.
    source_rows = [
        ["04/08/2026", "FECHO TPA  01433272 015", "28,00", "ENTRADA", "EXT0000000010", ""],
    ]
    target_rows = []
    ref_rows = [
        [
            "FECHOTPA01433272",
            "ENTRADA",
            "",
            "DOC777",
            "Venda de Livros",
            "PC10",
            "CC10",
            "Numerario",
            "Caixa L",
            "Caixa Saida L",
            "",
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

        result = service.process_with_matching(["EXT0000000010"])

    assert result["matched"] == 1
    assert result["no_match"] == 0

    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers
    assert target_row[_target_row_index(headers, "DOC. SOMA")] == "DOC777"
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == "Venda de Livros N001"


def test_matching_transferencia_accent_insensitive():
    # Source row has Transferência from parser; CONSTANTES has TRANSFERENCIA (unaccented)
    source_rows = [
        ["04/08/2026", "ENT.NUMERARIO  CH24 0006774253", "500,00", "Transferência", "EXT0000000015", ""],
    ]
    target_rows = []
    ref_rows = [
        [
            "ENT.NUMERARIO",
            "TRANSFERENCIA",
            "",
            "DOC888",
            "Depósito Numerário",
            "PC20",
            "CC20",
            "Numerario",
            "Caixa Geral",
            "Banco",
            "",
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

        result = service.process_with_matching(["EXT0000000015"])

    assert result["matched"] == 1
    assert result["no_match"] == 0

    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers
    assert target_row[_target_row_index(headers, "DOC. SOMA")] == "DOC888"
    assert target_row[_target_row_index(headers, "TIPO")] == "TRANSFERENCIA"
    assert target_row[_target_row_index(headers, "DESCRIÇÃO SOMA")] == "Depósito Numerário N001"


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


def _contaordem_row(id_interno, doc_soma, plano_conta=""):
    # Ordem: DATA MOV., DESCRIÇÃO, IMPORTÂNCIA, TIPO, PERÍODO, PROCESSO, ID_INTERNO,
    # PLANO DE CONTA, CENTRO DE CUSTO, DESCRIÇÃO SOMA, FORMA DE PAGAMENTO, CAIXA,
    # CAIXA SAIDA, DOC. SOMA
    return [
        "04/08/2026", "FECHOTPA999", "10,00", "ENTRADA", "AGOSTO", "T_EXTRATO",
        id_interno, plano_conta, "", "", "", "", "", doc_soma,
    ]


_REF_NO_DOC_SOMA = [
    ["FECHOTPA999", "ENTRADA", "", "", "Venda X", "PCX", "CCX", "FP", "CX", "CXS", ""],
]


def test_existing_row_match_clears_analisar_sentinel_when_constants_has_no_doc_soma():
    source_rows = [
        ["04/08/2026", "FECHO TPA 999", "10,00", "ENTRADA", "EXT0000000020", ""],
    ]
    target_rows = [_contaordem_row("EXT0000000020", "ANALISAR")]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, _REF_NO_DOC_SOMA)
    service = TransferMatchingService(
        mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
    )

    norm_id = TransferMatchingLayout.normalize_text("EXT0000000020")
    prepared = service.row_builder.prepare_with_matching(source_rows, {norm_id})

    assert prepared["stats"]["matched"] == 1
    row_update = prepared["update_rows"][2]
    assert row_update["DOC. SOMA"] == CLEAR_CELL
    assert row_update["DESCRIÇÃO SOMA"] == "Venda X"


def test_existing_row_with_resolved_doc_soma_is_not_reprocessed():
    # DOC. SOMA com nº real -> linha resolvida -> NÃO é reprocessada nem tocada.
    source_rows = [
        ["04/08/2026", "FECHO TPA 999", "10,00", "ENTRADA", "EXT0000000021", ""],
    ]
    target_rows = [_contaordem_row("EXT0000000021", "5469672")]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, _REF_NO_DOC_SOMA)
    service = TransferMatchingService(
        mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
    )

    norm_id = TransferMatchingLayout.normalize_text("EXT0000000021")
    prepared = service.row_builder.prepare_with_matching(source_rows, {norm_id})

    assert prepared["stats"]["skipped_resolved"] == 1
    assert prepared["stats"]["matched"] == 0
    assert prepared["update_rows"] == {}


def test_existing_row_with_plano_conta_filled_is_not_reprocessed():
    # DOC. SOMA = ANALISAR mas PLANO DE CONTA já preenchido -> não faz nada.
    source_rows = [
        ["04/08/2026", "FECHO TPA 999", "10,00", "ENTRADA", "EXT0000000024", ""],
    ]
    target_rows = [
        _contaordem_row("EXT0000000024", "ANALISAR", plano_conta="RECEITAS DE LIVRARIA")
    ]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, _REF_NO_DOC_SOMA)
    service = TransferMatchingService(
        mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
    )

    norm_id = TransferMatchingLayout.normalize_text("EXT0000000024")
    prepared = service.row_builder.prepare_with_matching(source_rows, {norm_id})

    assert prepared["stats"]["skipped_resolved"] == 1
    assert prepared["stats"]["matched"] == 0
    assert prepared["update_rows"] == {}


def test_existing_row_with_empty_doc_soma_is_reprocessed():
    # DOC. SOMA vazio -> linha é reprocessada e recebe a classificação.
    source_rows = [
        ["04/08/2026", "FECHO TPA 999", "10,00", "ENTRADA", "EXT0000000022", ""],
    ]
    target_rows = [_contaordem_row("EXT0000000022", "")]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, _REF_NO_DOC_SOMA)
    service = TransferMatchingService(
        mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
    )

    norm_id = TransferMatchingLayout.normalize_text("EXT0000000022")
    prepared = service.row_builder.prepare_with_matching(source_rows, {norm_id})

    assert prepared["stats"]["skipped_resolved"] == 0
    assert prepared["stats"]["matched"] == 1
    row_update = prepared["update_rows"][2]
    assert row_update["DESCRIÇÃO SOMA"] == "Venda X"
    assert row_update["PLANO DE CONTA"] == "PCX"
    # DOC. SOMA já estava vazio e a CONSTANTES não traz nº -> não é escrito.
    assert "DOC. SOMA" not in row_update


def test_existing_row_no_match_keeps_analisar_without_redundant_write():
    # DOC. SOMA = ANALISAR e continua sem match -> nada a escrever (já está certo).
    source_rows = [
        ["04/08/2026", "SEM REFERENCIA NENHUMA", "10,00", "ENTRADA", "EXT0000000023", ""],
    ]
    target_rows = [_contaordem_row("EXT0000000023", "ANALISAR")]

    mock_sheets = _make_mock_sheets(source_rows, target_rows, _REF_NO_DOC_SOMA)
    service = TransferMatchingService(
        mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
    )

    norm_id = TransferMatchingLayout.normalize_text("EXT0000000023")
    prepared = service.row_builder.prepare_with_matching(source_rows, {norm_id})

    assert prepared["stats"]["no_match"] == 1
    assert prepared["stats"]["skipped_resolved"] == 0
    assert prepared["update_rows"] == {}


def test_matching_prioritizes_specific_rule_over_generic_prefix():
    # TR- is defined BEFORE TR-IPS in the sheet rows, but TR-IPS must match first for TR-IPS-CLAYTON
    source_rows = [
        ["04/08/2026", "TR-IPS-CLAYTON", "100,00", "ENTRADA", "EXT0000000030", ""],
    ]
    target_rows = []
    ref_rows = [
        [
            "TR-",
            "ENTRADA",
            "",
            "DOC_GENERIC",
            "Dizimos Generico",
            "PC_GENERIC",
            "CC_GENERIC",
            "FP",
            "CX",
            "CXS",
            "",
        ],
        [
            "TR-IPS",
            "ENTRADA",
            "",
            "DOC_SPECIFIC",
            "Dizimos Especifico",
            "PC_SPECIFIC",
            "CC_SPECIFIC",
            "FP",
            "CX",
            "CXS",
            "",
        ],
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

        result = service.process_with_matching(["EXT0000000030"])

    assert result["matched"] == 1
    target_row = mock_batch.batch_write_with_updates.call_args.kwargs["target_data"][0]
    headers = service.target_headers
    assert target_row[_target_row_index(headers, "DOC. SOMA")] == "DOC_SPECIFIC"
    assert target_row[_target_row_index(headers, "PLANO DE CONTA")] == "PC_SPECIFIC"
    assert target_row[_target_row_index(headers, "CENTRO DE CUSTO")] == "CC_SPECIFIC"

