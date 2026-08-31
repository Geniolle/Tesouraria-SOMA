"""Mark transferred Verbo Café source rows as CONCLUÍDO.

Unlike ``Saidas`` / ``DizimosOfertas`` (which flip a ``FINANCE`` column),
the Verbo Café source uses ``STATUS DA TESOURARIA`` for its lifecycle:
``EM ABERTO`` -> ``CONCLUÍDO``. The write targets the *source* spreadsheet,
which is separate from the main treasury spreadsheet.
"""

from __future__ import annotations

import logging

from .config import STATUS_DONE, STATUS_FIELD, VerboCafePhase

logger = logging.getLogger(__name__)


class VerboCafeStatusUpdater:
    """Set ``STATUS DA TESOURARIA = CONCLUÍDO`` for transferred rows."""

    status_field = STATUS_FIELD
    status_value = STATUS_DONE

    def __init__(
        self,
        sheets_client,
        source_spreadsheet_id: str,
        source_headers: list[str],
        phase: VerboCafePhase,
    ) -> None:
        self.sheets_client = sheets_client
        self.source_spreadsheet_id = source_spreadsheet_id
        self.source_sheet = phase.source_sheet
        self.status_index = next(
            (
                index
                for index, header in enumerate(source_headers)
                if str(header).upper().strip() == self.status_field
            ),
            None,
        )

    def mark_batch_as_concluido(self, row_numbers: list[int]) -> dict:
        if not row_numbers:
            return {"updated": 0, "failed": 0, "errors": []}

        if self.status_index is None:
            return {
                "updated": 0,
                "failed": len(row_numbers),
                "errors": [f"{self.status_field} column not found"],
            }

        column_number = self.status_index + 1
        updated = 0
        errors: list[str] = []

        for row_number in sorted(set(row_numbers)):
            try:
                self.sheets_client.update_cell(
                    self.source_spreadsheet_id,
                    self.source_sheet,
                    row_number,
                    column_number,
                    self.status_value,
                )
                updated += 1
            except Exception as error:  # noqa: BLE001
                message = f"Row {row_number}: {error}"
                errors.append(message)
                logger.error(
                    "Failed to update %s %s: %s",
                    self.source_sheet,
                    self.status_field,
                    message,
                )

        return {"updated": updated, "failed": len(errors), "errors": errors}
