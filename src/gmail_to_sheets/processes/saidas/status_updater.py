"""Update FINANCE in SAÍDAS after successful transfer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SaidaStatusUpdater:
    """Mark transferred SAÍDAS rows as Enviado."""

    source_sheet = "SAÍDAS"
    status_field = "FINANCE"
    status_value = "Enviado"

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
                    self.status_value,
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
