from unittest.mock import Mock

from src.gmail_to_sheets.processes.conciliacao.lookup_service import (
    LookupService,
    is_valid_doc_soma,
)


class TestIsValidDocSoma:
    def test_accepts_exactly_7_digits(self):
        assert is_valid_doc_soma("5470146") is True
        assert is_valid_doc_soma("  5470146 ") is True

    def test_rejects_wrong_length(self):
        assert is_valid_doc_soma("547014") is False
        assert is_valid_doc_soma("54701466") is False

    def test_rejects_non_digits_and_empty(self):
        assert is_valid_doc_soma("ANALISAR") is False
        assert is_valid_doc_soma("54701AB") is False
        assert is_valid_doc_soma("547-146") is False
        assert is_valid_doc_soma("") is False
        assert is_valid_doc_soma(None) is False


class TestLookupDocSoma:
    def _service(self, doc_soma):
        svc = LookupService(
            Mock(), "sheet-1", headers=["ID_INTERNO", "DOC. SOMA"]
        )
        svc.contaordem_cache = {
            "EXT0000000001": {
                "row_number": 5,
                "row_data": ["EXT0000000001", doc_soma],
                "doc_soma": doc_soma,
            }
        }
        return svc

    def test_found_for_valid_7_digit_doc_soma(self):
        result = self._service("5470146").lookup_doc_soma("EXT0000000001")
        assert result == {
            "found": True,
            "doc_soma": "5470146",
            "row_number": 5,
        }

    def test_not_found_for_invalid_format(self):
        for bad in ("ANALISAR", "547014", "54701466", "DOC-123", ""):
            result = self._service(bad).lookup_doc_soma("EXT0000000001")
            assert result == {"found": False, "doc_soma": None}

    def test_not_found_for_missing_id(self):
        result = self._service("5470146").lookup_doc_soma("EXT9999999999")
        assert result == {"found": False, "doc_soma": None}
