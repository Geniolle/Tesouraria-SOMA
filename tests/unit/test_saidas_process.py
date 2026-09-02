from unittest.mock import Mock

from src.gmail_to_sheets.processes.saidas.status_updater import (
    SaidaStatusUpdater,
)
from src.gmail_to_sheets.processes.saidas.transfer_service import (
    SaidaTransferService,
)
from src.gmail_to_sheets.processes.saidas.validator import SaidaValidator

HEADERS = [
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
    "IDUSER",
    "TIMESTAMP",
    "SEQUENCIA_INTERNA",
    "DESCRIÇÃO SOMA",
]

TARGET_HEADERS = [
    "DATA MOV.",
    "DATA VALOR",
    "DESCRIÇÃO",
    "IMPORTÂNCIA",
    "DOC. SOMA",
    "LINK",
    "TIPO",
    "PLANO DE CONTA",
    "CENTRO DE CUSTO",
    "DESCRIÇÃO SOMA",
    "FORMA DE PAGAMENTO",
    "CAIXA",
    "CAIXA SAIDA",
    "PERÍODO",
    "TERMINALCODE",
    "PROCESSO",
    "ID_INTERNO",
    "AUDITORIA",
    "IDUSER",
    "TIMESTAMP",
    "STATUS",
    "DADOS DOC",
]


def _row(**overrides):
    values = {
        "ID_INTERNO": "SAI0000000239",
        "FORMA DE PAGAMENTO": "Cartão Crédito",
        "DATA": "30/08/2026",
        "DATA VALOR": "29/08/2026",
        "TIPO": "PAGAMENTO",
        "DOC. SOMA": "",
        "Nº RECIBO": "FT-1",
        "VALOR DA COMPRA": "25,00",
        "DESCRIÇÃO DA COMPRA": "MATERIAL DE LIMPEZA",
        "NOME RECEBEDOR DO PAGAMENTO": "",
        "TELEFONE RECEBEDOR": "",
        "EMAIL RECEBEDOR": "",
        "NOME DO FORNECEDOR": "Fornecedor",
        "TELEFONE FORNECEDOR": "",
        "EMAIL FORNECEDOR": "",
        "PLANO DE CONTA": "MATERIAL DE LIMPEZA",
        "CENTRO DE CUSTO": "30.10.10 - MATERIAL DE LIMPEZA",
        "CAIXA": "CAIXA ECONÔMICA MONTEPIO GERAL [CONTA CORRENTE]",
        "IMAGEM DO RECIBO": "",
        "STATUS DA TESOURARIA": "Concluído",
        "STATUS PROCESSAMENTO": "",
        "FINANCE": "",
        "IDUSER": "",
        "TIMESTAMP": "",
        "SEQUENCIA_INTERNA": "239",
        "DESCRIÇÃO SOMA": "MATERIAL DE LIMPEZA N001",
    }
    values.update(overrides)
    return [values.get(header, "") for header in HEADERS]


class TestSaidaValidator:
    def test_accepts_finance_ready_row(self):
        validator = SaidaValidator(
            Mock(),
            "sheet-123",
            headers=HEADERS,
        )

        valid, error = validator.is_valid_entry(_row(), 2)

        assert valid is True
        assert error is None

    def test_rejects_filled_doc_soma(self):
        validator = SaidaValidator(
            Mock(),
            "sheet-123",
            headers=HEADERS,
        )

        valid, error = validator.is_valid_entry(
            _row(**{"DOC. SOMA": "5459998"}),
            2,
        )

        assert valid is False
        assert error == "DOC.SOMA não está vazio"

    def test_requires_concluido_status(self):
        validator = SaidaValidator(
            Mock(),
            "sheet-123",
            headers=HEADERS,
        )

        valid, error = validator.is_valid_entry(
            _row(**{"STATUS DA TESOURARIA": ""}),
            2,
        )

        assert valid is False
        assert error == "STATUS DA TESOURARIA não está Concluído"

    def test_requires_empty_finance(self):
        validator = SaidaValidator(
            Mock(),
            "sheet-123",
            headers=HEADERS,
        )

        valid, error = validator.is_valid_entry(
            _row(FINANCE="Enviado"),
            2,
        )

        assert valid is False
        assert error == "FINANCE já está preenchido"

    def test_allows_duplicado_finance_for_recheck(self):
        validator = SaidaValidator(
            Mock(),
            "sheet-123",
            headers=HEADERS,
        )

        valid, error = validator.is_valid_entry(
            _row(FINANCE="duplicado"),
            2,
        )

        assert valid is True
        assert error is None


class TestSaidaTransferService:
    def test_maps_bank_account_payment_to_contaordem(self):
        service = SaidaTransferService(
            Mock(),
            "sheet-123",
            source_headers=HEADERS,
            target_headers=TARGET_HEADERS,
        )

        target = service.build_target_row(_row(), 1)
        mapped = dict(zip(TARGET_HEADERS, target))

        assert mapped["DATA MOV."] == "30/08/2026"
        assert mapped["DATA VALOR"] == "29/08/2026"
        assert mapped["DESCRIÇÃO"] == "MATERIAL DE LIMPEZA"
        assert mapped["IMPORTÂNCIA"] == "25,00"
        assert mapped["DOC. SOMA"] == ""
        assert mapped["TIPO"] == "Saída"
        assert mapped["PLANO DE CONTA"] == "MATERIAL DE LIMPEZA"
        assert mapped["CENTRO DE CUSTO"] == (
            "30.10.10 - MATERIAL DE LIMPEZA"
        )
        assert mapped["DESCRIÇÃO SOMA"] == (
            "MATERIAL DE LIMPEZA N001"
        )
        assert mapped["FORMA DE PAGAMENTO"] == (
            "TRANSFERÊNCIA BANCÁRIA"
        )
        assert mapped["CAIXA"] == (
            "CAIXA ECONÔMICA MONTEPIO GERAL [CONTA CORRENTE]"
        )
        assert mapped["PERÍODO"] == "AGOSTO"
        assert mapped["PROCESSO"] == "SAÍDAS"
        assert mapped["ID_INTERNO"] == "SAI0000000239"

    def test_preserves_cash_payment_for_daily_cash(self):
        service = SaidaTransferService(
            Mock(),
            "sheet-123",
            source_headers=HEADERS,
            target_headers=TARGET_HEADERS,
        )

        target = service.build_target_row(
            _row(
                **{
                    "FORMA DE PAGAMENTO": "Dinheiro",
                    "CAIXA": "CAIXA DIÁRIO",
                }
            ),
            1,
        )
        mapped = dict(zip(TARGET_HEADERS, target))

        assert mapped["FORMA DE PAGAMENTO"] == "DINHEIRO"
        assert mapped["CAIXA"] == "CAIXA DIÁRIO"

    def test_non_cash_payment_becomes_bank_transfer(self):
        service = SaidaTransferService(
            Mock(),
            "sheet-123",
            source_headers=HEADERS,
            target_headers=TARGET_HEADERS,
        )

        target = service.build_target_row(
            _row(
                **{
                    "FORMA DE PAGAMENTO": "Multibanco",
                    "CAIXA": "CAIXA DIÁRIO",
                }
            ),
            1,
        )
        mapped = dict(zip(TARGET_HEADERS, target))

        assert mapped["FORMA DE PAGAMENTO"] == "TRANSFERÊNCIA BANCÁRIA"

    def test_blank_payment_stays_blank(self):
        service = SaidaTransferService(
            Mock(),
            "sheet-123",
            source_headers=HEADERS,
            target_headers=TARGET_HEADERS,
        )

        target = service.build_target_row(
            _row(**{"FORMA DE PAGAMENTO": ""}),
            1,
        )
        mapped = dict(zip(TARGET_HEADERS, target))

        assert mapped["FORMA DE PAGAMENTO"] == ""

    def test_descricao_soma_gets_sequence_suffix(self):
        service = SaidaTransferService(
            Mock(),
            "sheet-123",
            source_headers=HEADERS,
            target_headers=TARGET_HEADERS,
        )

        # source has no suffix -> DESCRIÇÃO DA COMPRA is used as the base
        target = service.build_target_row(
            _row(**{"DESCRIÇÃO SOMA": "", "DESCRIÇÃO DA COMPRA": "COMPRA X"}),
            7,
        )
        mapped = dict(zip(TARGET_HEADERS, target))
        assert mapped["DESCRIÇÃO SOMA"] == "COMPRA X N007"

        # source already carries a suffix -> it is replaced, not duplicated
        target = service.build_target_row(
            _row(**{"DESCRIÇÃO SOMA": "COMPRA X N001"}),
            12,
        )
        mapped = dict(zip(TARGET_HEADERS, target))
        assert mapped["DESCRIÇÃO SOMA"] == "COMPRA X N012"


class TestSaidaStatusUpdater:
    def test_marks_finance_as_enviado(self):
        client = Mock()
        updater = SaidaStatusUpdater(
            client,
            "sheet-123",
            headers=HEADERS,
        )

        result = updater.mark_batch_as_sent([7])

        assert result["updated"] == 1
        assert result["failed"] == 0
        finance_index = HEADERS.index("FINANCE")
        client.update_cell.assert_called_once_with(
            "sheet-123",
            "SAÍDAS",
            7,
            finance_index + 1,
            "Enviado",
        )

    def test_marks_finance_as_duplicado(self):
        client = Mock()
        updater = SaidaStatusUpdater(
            client,
            "sheet-123",
            headers=HEADERS,
        )

        result = updater.mark_batch_as_duplicate([9])

        assert result["updated"] == 1
        assert result["failed"] == 0
        finance_index = HEADERS.index("FINANCE")
        client.update_cell.assert_called_once_with(
            "sheet-123",
            "SAÍDAS",
            9,
            finance_index + 1,
            "duplicado",
        )
