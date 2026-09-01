"""Schema and cache helpers for the integrated transfer+matching flow."""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


@dataclass
class TransferMatchingLayout:
    """Keeps sheet metadata, indices and cached state."""

    sheets_client: SheetsClient
    spreadsheet_id: str
    source_sheet: str = "T_EXTRATO"
    target_sheet: str = "CONTAORDEM"
    reference_sheet: str = "CONSTANTES"
    source_headers: list[str] = field(default_factory=list)
    target_headers: list[str] = field(default_factory=list)
    ref_headers: list[str] = field(default_factory=list)
    source_indices: dict[str, int] = field(default_factory=dict)
    target_indices: dict[str, int] = field(default_factory=dict)
    ref_indices: dict[str, int] = field(default_factory=dict)
    ref_data: list[list] = field(default_factory=list)
    existing_ids: dict[str, int] = field(default_factory=dict)
    existing_doc_soma: dict[str, str] = field(default_factory=dict)
    existing_plano_conta: dict[str, str] = field(default_factory=dict)
    sheet_ids_cache: dict[str, int] = field(default_factory=dict)
    seq_state: dict[str, dict[str, int | str]] = field(default_factory=dict)

    def load(self) -> None:
        self.source_headers = self._load_headers(self.source_sheet)
        self.target_headers = self._load_headers(self.target_sheet)
        self.ref_headers = self._load_headers(self.reference_sheet)

        self.source_indices = self._map_columns(self.source_headers)
        self.target_indices = self._map_columns(self.target_headers)
        self.ref_indices = self._map_columns(self.ref_headers)

        self._validate_columns()
        self.ref_data = self._load_reference_data()
        self.existing_ids = self._load_existing_ids()
        self._init_sequential_state()

    def _load_headers(self, sheet_name: str) -> list[str]:
        headers = self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)
        logger.info(f"Loaded {len(headers)} columns from {sheet_name}")
        return headers

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, int]:
        indices: dict[str, int] = {}
        for idx, header in enumerate(headers):
            indices[str(header).strip().upper()] = idx
        return indices

    def _validate_columns(self) -> None:
        required = {
            "SOURCE": ["DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "ID_INTERNO", "STATUS"],
            "TARGET": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO"],
            "REFERENCE": ["TEXTO", "TIPO", "DOC. SOMA", "DESCRIÇÃO SOMA"],
        }

        for sheet_type, cols in required.items():
            if sheet_type == "SOURCE":
                indices = self.source_indices
                sheet_name = self.source_sheet
            elif sheet_type == "TARGET":
                indices = self.target_indices
                sheet_name = self.target_sheet
            else:
                indices = self.ref_indices
                sheet_name = self.reference_sheet

            missing = [col for col in cols if col.upper() not in indices]
            if missing:
                raise RuntimeError(f"Missing columns in {sheet_name}: {missing}")

        logger.info("✓ All columns validated")

    def _load_reference_data(self) -> list[list]:
        range_name = self.sheets_client.get_data_range(self.spreadsheet_id, self.reference_sheet)
        if not isinstance(range_name, str) or not range_name:
            range_name = f"{self.reference_sheet}!A2:Z99999"
        result = self.sheets_client.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
        ).execute()
        rows = result.get("values", [])
        logger.info(f"Loaded {len(rows)} reference rows")
        return rows

    def _init_sequential_state(self) -> None:
        try:
            range_name = self.sheets_client.get_data_range(self.spreadsheet_id, self.target_sheet)
            if not isinstance(range_name, str) or not range_name:
                range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            data_idx = self.target_indices.get("DATA MOV.")
            desc_soma_idx = self.target_indices.get("DESCRIÇÃO SOMA")
            if data_idx is None or desc_soma_idx is None:
                return

            for row in rows:
                if data_idx >= len(row) or desc_soma_idx >= len(row):
                    continue
                data_mov = str(row[data_idx]).strip()
                desc_soma = str(row[desc_soma_idx]).strip()
                if not data_mov or not desc_soma:
                    continue
                parts = desc_soma.rsplit(" ", 1)
                if len(parts) == 2 and parts[1].startswith("N"):
                    desc_base = parts[0]
                    desc_base_key = self.normalize_match_text(desc_base)
                    if not desc_base_key:
                        continue
                    try:
                        seq_num = int(parts[1][1:])
                        data_key = self.get_day_key(data_mov)
                        if not data_key:
                            continue
                        key = f"{data_key}||{desc_base_key}"
                        if key not in self.seq_state:
                            self.seq_state[key] = {"max": 0, "base": desc_base}
                        self.seq_state[key]["max"] = max(self.seq_state[key]["max"], seq_num)
                    except (ValueError, IndexError):
                        pass
            logger.info(f"Initialized sequential state with {len(self.seq_state)} entries")
        except Exception as e:
            logger.warning(f"Failed to initialize sequential state: {e}")

    def _load_existing_ids(self) -> dict[str, int]:
        range_name = self.sheets_client.get_data_range(self.spreadsheet_id, self.target_sheet)
        if not isinstance(range_name, str) or not range_name:
            range_name = f"{self.target_sheet}!A2:Z99999"
        result = self.sheets_client.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
        ).execute()
        rows = result.get("values", [])
        id_idx = self.target_indices.get("ID_INTERNO")
        if id_idx is None:
            return {}

        doc_soma_idx = self.target_indices.get("DOC. SOMA")
        plano_conta_idx = self.target_indices.get("PLANO DE CONTA")
        existing: dict[str, int] = {}
        for i, row in enumerate(rows):
            if id_idx < len(row) and row[id_idx]:
                id_norm = self.normalize_text(str(row[id_idx]))
                existing[id_norm] = i + 2
                if doc_soma_idx is not None and doc_soma_idx < len(row):
                    self.existing_doc_soma[id_norm] = str(row[doc_soma_idx]).strip()
                if plano_conta_idx is not None and plano_conta_idx < len(row):
                    self.existing_plano_conta[id_norm] = str(row[plano_conta_idx]).strip()
        logger.info(f"Loaded {len(existing)} existing IDs in target sheet")
        return existing

    def get_sheet_id(self, sheet_name: str) -> int:
        if sheet_name in self.sheet_ids_cache:
            return self.sheet_ids_cache[sheet_name]

        result = self.sheets_client.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties",
        ).execute()

        for sheet in result.get("sheets", []):
            if sheet["properties"]["title"] == sheet_name:
                sheet_id = sheet["properties"]["sheetId"]
                self.sheet_ids_cache[sheet_name] = sheet_id
                return sheet_id

        raise ValueError(f"Sheet '{sheet_name}' not found")

    @staticmethod
    def get_index(column_name: str, indices: dict[str, int]) -> int | None:
        return indices.get(column_name.upper())

    @classmethod
    def get_cell_value(cls, row: list, column_name: str, indices: dict[str, int]) -> str:
        idx = cls.get_index(column_name, indices)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    @staticmethod
    def set_cell_value(row: list, column_name: str, value: str, indices: dict[str, int]) -> None:
        idx = indices.get(column_name.upper())
        if idx is None or idx < 0 or idx >= len(row):
            return
        row[idx] = str(value) if value else ""

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""

        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    @staticmethod
    def normalize_match_text(text: str) -> str:
        if not text:
            return ""

        # Remove espaços (não só nas pontas): as chaves TEXTO da CONSTANTES são
        # escritas sem espaços (ex.: "FECHOTPA01433272"), mas o descritivo cru do
        # banco vem com espaços ("FECHO TPA  01433272 016"). Sem isto o teste de
        # substring do matching falha.
        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    @staticmethod
    def parse_sheet_date(value) -> datetime | None:
        if value is None or value == "":
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)

        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except (OverflowError, OSError, ValueError):
                return None

        text = str(value).strip()
        if not text:
            return None

        for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @classmethod
    def get_day_key(cls, data_str: str) -> str:
        parsed = cls.parse_sheet_date(data_str)
        return parsed.strftime("%Y-%m-%d") if parsed else ""

    @classmethod
    def format_day_display(cls, data_str: str) -> str:
        parsed = cls.parse_sheet_date(data_str)
        return parsed.strftime("%d/%m/%Y") if parsed else ""

    @staticmethod
    def parse_amount(value: str) -> float:
        if not value:
            return 0.0
        try:
            return float(str(value).strip().replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def format_number(value: float) -> str:
        return f"{value:.2f}".replace(".", ",")

    @classmethod
    def get_month_text(cls, data_str: str) -> str:
        if not data_str:
            return ""
        from datetime import datetime

        meses = [
            "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
            "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
        ]
        try:
            date_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
            return meses[date_obj.month - 1]
        except (ValueError, IndexError):
            return ""
