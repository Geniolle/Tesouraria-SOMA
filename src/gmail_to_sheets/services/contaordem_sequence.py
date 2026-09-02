"""Per-day ``DESCRIÇÃO SOMA`` sequence numbers for ``CONTAORDEM`` writers.

Global rule (see ``AGENTS.md``): every row written to ``CONTAORDEM`` must
end its ``DESCRIÇÃO SOMA`` with an ``N###`` suffix. The counter restarts at
1 for each ``DATA MOV.`` day *and* each ``PROCESSO`` tag.

This service rebuilds that state from ``CONTAORDEM`` once per run and hands
out the next number, keeping the counter in memory so a batch stays
consistent before it is written back.
"""

from __future__ import annotations

import logging
import re

from src.gmail_to_sheets.clients.sheets_projection import read_projected_rows
from src.gmail_to_sheets.services.pt_format import format_date_ddmmyyyy

logger = logging.getLogger(__name__)

_SEQ_SUFFIX = re.compile(r"\s*N\d{3}\s*$")
_SEQ_SUFFIX_NUM = re.compile(r"N(\d{3})\s*$")


def strip_sequence_suffix(text: str | None) -> str:
    """Return ``text`` without a trailing ``N###`` sequence suffix."""
    return _SEQ_SUFFIX.sub("", str(text or "")).strip()


def build_descricao_soma(base: str | None, sequence_number: int) -> str:
    """Attach the ``N###`` suffix to a base ``DESCRIÇÃO SOMA`` text.

    Any existing suffix on ``base`` is removed first so the number is not
    duplicated when a source row already carries one.
    """
    clean_base = strip_sequence_suffix(base)
    suffix = f"N{sequence_number:03d}"
    return f"{clean_base} {suffix}".strip()


class ContaOrdemSequenceService:
    """Track the next ``N###`` per ``DATA MOV.`` day for one PROCESSO tag."""

    target_sheet = "CONTAORDEM"

    def __init__(
        self,
        sheets_client,
        target_spreadsheet_id: str,
        headers: list[str],
        processo_tag: str,
    ) -> None:
        self.sheets_client = sheets_client
        self.target_spreadsheet_id = target_spreadsheet_id
        self.processo_tag = processo_tag
        self.column_indices = {
            str(header).upper().strip(): index
            for index, header in enumerate(headers)
            if header
        }
        self._max_by_day: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        rows = read_projected_rows(
            self.sheets_client,
            self.target_spreadsheet_id,
            self.target_sheet,
            self.column_indices,
            ["DATA MOV.", "DESCRIÇÃO SOMA", "PROCESSO"],
        )
        data_idx = self.column_indices["DATA MOV."]
        desc_idx = self.column_indices["DESCRIÇÃO SOMA"]
        proc_idx = self.column_indices["PROCESSO"]

        target_proc = self.processo_tag.strip().casefold()
        for _, row in rows:
            if self._value(row, proc_idx).strip().casefold() != target_proc:
                continue
            day = format_date_ddmmyyyy(self._value(row, data_idx)) or self._value(
                row, data_idx
            ).strip()
            if not day:
                continue
            match = _SEQ_SUFFIX_NUM.search(self._value(row, desc_idx))
            if not match:
                continue
            number = int(match.group(1))
            self._max_by_day[day] = max(self._max_by_day.get(day, 0), number)

        logger.info(
            "%s: %s day(s) with existing DESCRIÇÃO SOMA sequence numbers",
            self.processo_tag,
            len(self._max_by_day),
        )

    def next_for(self, data_ddmmyyyy: str) -> int:
        """Return (and reserve) the next sequence number for a day."""
        nxt = self._max_by_day.get(data_ddmmyyyy, 0) + 1
        self._max_by_day[data_ddmmyyyy] = nxt
        return nxt

    @staticmethod
    def _value(row: list, index: int) -> str:
        if index >= len(row) or row[index] is None:
            return ""
        return str(row[index]).strip()
