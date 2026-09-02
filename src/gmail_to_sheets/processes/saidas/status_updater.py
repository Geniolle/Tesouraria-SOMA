"""Update FINANCE in SAÍDAS after successful transfer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SaidaStatusUpdater:
    """Mark processed SAÍDAS rows in the FINANCE column."""

    source_sheet = "SAÍDAS"
    status_field = "FINANCE"
    status_value = "Enviado"
    duplicate_value = "duplicado"

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        headers: list[str] | None = None,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        if headers is None:
            headers = sheets_client.get_headers(
                spreadsheet_id,
                self.source_sheet,
            )

        self.finance_index = next(
            (
                index
                for index, header in enumerate(headers)
                if str(header).upper().strip() == self.status_field
            ),
            None,
        )

    def mark_batch_as_sent(self, row_numbers: list[int]) -> dict:
        """Mark transferred rows as ``Enviado``."""
        return self._mark_batch(row_numbers, self.status_value)

    def mark_batch_as_duplicate(self, row_numbers: list[int]) -> dict:
        """Mark rows already present in CONTAORDEM as ``duplicado``."""
        return self._mark_batch(row_numbers, self.duplicate_value)

    def _mark_batch(self, row_numbers: list[int], value: str) -> dict:
        if not row_numbers:
            return {"updated": 0, "failed": 0, "errors": []}

        if self.finance_index is None:
            return {
                "updated": 0,
                "failed": len(row_numbers),
                "errors": ["FINANCE column not found"],
            }

        updated = 0
        errors: list[str] = []
        column_number = self.finance_index + 1

        for row_number in sorted(set(row_numbers)):
            try:
                self.sheets_client.update_cell(
                    self.spreadsheet_id,
                    self.source_sheet,
                    row_number,
                    column_number,
                    value,
                )
                updated += 1
            except Exception as error:
                message = f"Row {row_number}: {error}"
                errors.append(message)
                logger.error("Failed to update SAÍDAS FINANCE: %s", message)

        return {
            "updated": updated,
            "failed": len(errors),
            "errors": errors,
        }
