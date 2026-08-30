"""
Entry Transfer Service

Transfers validated entries from DÍZIMOS/OFERTAS to CONTAORDEM.
Handles data mapping, deduplication, and status updates.
"""

import logging
from datetime import datetime
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class EntryTransferError(Exception):
    """Raised when entry transfer fails."""
    pass


class EntryTransferService:
    """Transfer entries from DÍZIMOS/OFERTAS to CONTAORDEM."""

    # Hardcoded values for CONTAORDEM transfer
    TIPO_FIXED = "Entrada"
    PLANO_CONTA_FIXED = "DOAÇÕES - DÍZIMOS E OFERTAS"
    CENTRO_CUSTO_FIXED = "10.10.01 - DÍZIMOS E OFERTAS"
    PROCESSO_FIXED = "DÍZIMOS/OFERTAS"
    FORMA_PAGAMENTO_FIXED = "DINHEIRO"
    CAIXA_FIXED = "CAIXA DIÁRIO"

    MESES = [
        "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
        "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
    ]

    def __init__(self, sheets_client: SheetsClient, spreadsheet_id: str):
        """
        Initialize transfer service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = "DÍZIMOS/OFERTAS"
        self.target_sheet = "CONTAORDEM"

        self.source_indices = self._load_column_indices(self.source_sheet)
        self.target_indices = self._load_column_indices(self.target_sheet)
        self.target_headers = self.sheets_client.get_headers(
            spreadsheet_id, self.target_sheet
        )

    def _load_column_indices(self, sheet_name: str) -> dict:
        """Load column indices from sheet header."""
        try:
            headers = self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)
            indices = {}

            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(f"Loaded {len(indices)} columns from {sheet_name}")
            return indices

        except Exception as e:
            logger.error(f"Failed to load columns from {sheet_name}: {e}")
            raise EntryTransferError(f"Failed to load columns: {e}") from e

    def build_target_row(self, source_row: list, numero_documento: str) -> list:
        """
        Build a CONTAORDEM row from DÍZIMOS/OFERTAS data.

        Args:
            source_row: Source row from DÍZIMOS/OFERTAS
            numero_documento: Número do documento field value

        Returns:
            Formatted row for CONTAORDEM
        """
        # Create empty row
        row = [""] * len(self.target_headers)

        # Extract source values
        data = self._get_source_field(source_row, "DATA")
        valor = self._get_source_field(source_row, "VALOR")
        id_interno = self._get_source_field(source_row, "ID_INTERNO")

        # Build description with número documento if present
        if numero_documento and str(numero_documento).strip():
            descricao = f"{numero_documento} - DÍZIMOS E OFERTAS (CULTO)"
        else:
            descricao = "DÍZIMOS E OFERTAS (CULTO)"

        # Extract period (month) from data
        periodo = self._get_month_from_date(data)

        # Format valor
        valor_formatado = self._format_valor(valor)

        # Map fields to target row
        field_mapping = {
            "DATA MOV.": data,
            "DESCRIÇÃO": descricao,
            "DESCRIÇÃO SOMA": descricao,
            "IMPORTÂNCIA": valor_formatado,
            "TIPO": self.TIPO_FIXED,
            "PLANO DE CONTA": self.PLANO_CONTA_FIXED,
            "CENTRO DE CUSTO": self.CENTRO_CUSTO_FIXED,
            "PROCESSO": self.PROCESSO_FIXED,
            "PERÍODO": periodo,
            "FORMA DE PAGAMENTO": self.FORMA_PAGAMENTO_FIXED,
            "CAIXA": self.CAIXA_FIXED,
            "ID_INTERNO": id_interno,
        }

        for field_name, value in field_mapping.items():
            idx = self.target_indices.get(field_name.upper())
            if idx is not None and idx < len(row):
                row[idx] = str(value) if value else ""

        return row

    def _get_source_field(self, row: list, field_name: str) -> Optional[str]:
        """
        Get field value from source row.

        Args:
            row: Source row data
            field_name: Column name (case-insensitive)

        Returns:
            Field value or None
        """
        key = field_name.upper().strip()
        idx = self.source_indices.get(key)

        if idx is None or idx >= len(row):
            return None

        value = row[idx]
        return str(value).strip() if value else None

    @staticmethod
    def _format_valor(valor_str: str) -> str:
        """
        Format value for CONTAORDEM.

        Ensures proper decimal formatting with comma.

        Args:
            valor_str: Value string (may have comma or dot)

        Returns:
            Formatted value (with comma decimal)
        """
        if not valor_str:
            return "0,00"

        try:
            # Convert to float (normalize decimal)
            valor_decimal = float(str(valor_str).replace(",", "."))
            # Format with comma
            return f"{valor_decimal:.2f}".replace(".", ",")
        except (ValueError, TypeError):
            return str(valor_str)

    @staticmethod
    def _get_month_from_date(data_str: str) -> str:
        """
        Extract month from date string (DD/MM/YYYY).

        Args:
            data_str: Date in DD/MM/YYYY format

        Returns:
            Month name in Portuguese uppercase
        """
        if not data_str:
            return ""

        try:
            date_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
            meses = [
                "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
                "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
            ]
            return meses[date_obj.month - 1]
        except (ValueError, IndexError):
            return ""

    def append_row_to_target(self, row: list) -> bool:
        """
        Append row to CONTAORDEM sheet.

        Args:
            row: Row to append

        Returns:
            True if successful
        """
        try:
            result = self.sheets_client.append_rows(
                self.spreadsheet_id,
                self.target_sheet,
                [row]
            )

            if result:
                logger.debug(f"Row appended to {self.target_sheet}")
                return True
            else:
                logger.warning("Failed to append row")
                return False

        except Exception as e:
            logger.error(f"Failed to append row: {e}")
            raise EntryTransferError(f"Failed to append row: {e}") from e

    def sort_by_date(self) -> None:
        """Sort CONTAORDEM by DATA MOV. in descending order."""
        try:
            logger.info(f"Sorting {self.target_sheet} by DATA MOV. (descending)...")

            # Get last row
            last_row = self.sheets_client.get_last_row(
                self.spreadsheet_id, self.target_sheet
            )

            if last_row <= 2:
                logger.info("No data to sort")
                return

            # Get sheet ID
            result = self.sheets_client.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties"
            ).execute()

            sheet_id = None
            for sheet in result.get("sheets", []):
                if sheet["properties"]["title"] == self.target_sheet:
                    sheet_id = sheet["properties"]["sheetId"]
                    break

            if sheet_id is None:
                logger.warning(f"Could not find sheet ID for {self.target_sheet}")
                return

            # Get DATA MOV. column index
            data_idx = self.target_indices.get("DATA MOV.")
            if data_idx is None:
                logger.warning("DATA MOV. column not found")
                return

            # Create sort request
            request = {
                "sortRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,  # Skip header
                        "endRowIndex": last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(self.target_headers),
                    },
                    "sortSpecs": [
                        {
                            "dimensionIndex": data_idx,
                            "sortOrder": "DESCENDING"
                        }
                    ]
                }
            }

            self.sheets_client.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [request]}
            ).execute()

            logger.info("Sort completed successfully")

        except Exception as e:
            logger.error(f"Failed to sort sheet: {e}")
            # Don't raise - sorting is not critical
