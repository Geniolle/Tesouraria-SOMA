"""Serviço de lookup para pesquisar DOC.SOMA em CONTAORDEM.

Pesquisa linhas em CONTAORDEM usando o ID_INTERNO como chave.
"""

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.clients.sheets_projection import read_projected_rows

logger = logging.getLogger(__name__)

DOC_SOMA_LENGTH = 7


def is_valid_doc_soma(value: str | None) -> bool:
    """Return whether a CONTAORDEM ``DOC. SOMA`` value is conciliável.

    Must be exactly 7 numeric characters, e.g. ``"5470146"``. Anything
    else (empty, ``ANALISAR``, wrong length, non-digits) is rejected.
    """
    text = str(value or "").strip()
    return len(text) == DOC_SOMA_LENGTH and text.isdigit()


class LookupService:
    """Serviço de lookup em CONTAORDEM."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        headers: list[str] | None = None,
    ):
        """Inicializa o serviço de lookup.

        Args:
            sheets_client: Cliente Sheets autenticado
            spreadsheet_id: ID da planilha
            headers: Cabeçalho opcional previamente carregado
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.contaordem_cache: dict[str, dict] = {}
        self.column_indices = self._load_column_indices(headers=headers)

    def _load_column_indices(self, headers: list[str] | None = None) -> dict:
        """Carrega índices de colunas dinamicamente da header."""
        try:
            if headers is None:
                headers = self.sheets_client.get_headers(
                    self.spreadsheet_id, "CONTAORDEM"
                )
            indices = {}

            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(f"Carregados {len(indices)} campos de CONTAORDEM")
            return indices

        except Exception as e:
            logger.error(f"Erro ao carregar campos de CONTAORDEM: {e}")
            raise

    def load_contaordem_data(
        self,
        required_ids: set[str] | None = None,
    ) -> None:
        """Carrega somente ID_INTERNO e DOC.SOMA em cache.

        Quando required_ids é informado, ignora IDs não necessários e
        interrompe a leitura lógica assim que todos os IDs procurados forem
        encontrados. A leitura é somente leitura e preserva os índices de
        colunas originais através de projeção.
        """
        try:
            self.contaordem_cache = {}

            if required_ids is not None and not required_ids:
                return

            logger.info("Carregando dados projetados de CONTAORDEM...")

            rows = read_projected_rows(
                self.sheets_client,
                self.spreadsheet_id,
                "CONTAORDEM",
                self.column_indices,
                ["ID_INTERNO", "DOC. SOMA"],
            )
            logger.info(
                "      Carregadas %s linhas projetadas de CONTAORDEM",
                len(rows),
            )

            id_interno_idx = self.column_indices.get("ID_INTERNO")
            doc_soma_idx = self.column_indices.get("DOC. SOMA")
            if id_interno_idx is None:
                raise RuntimeError(
                    "Coluna ID_INTERNO não encontrada em CONTAORDEM"
                )
            if doc_soma_idx is None:
                raise RuntimeError(
                    "Coluna DOC. SOMA não encontrada em CONTAORDEM"
                )

            remaining = set(required_ids) if required_ids is not None else None

            for row_num, row in rows:
                if id_interno_idx >= len(row):
                    continue

                id_interno = (
                    str(row[id_interno_idx]).strip()
                    if row[id_interno_idx]
                    else ""
                )
                if not id_interno:
                    continue

                if remaining is not None and id_interno not in remaining:
                    continue

                doc_soma = (
                    str(row[doc_soma_idx]).strip()
                    if doc_soma_idx < len(row) and row[doc_soma_idx]
                    else ""
                )
                self.contaordem_cache[id_interno] = {
                    "row_number": row_num,
                    "row_data": row,
                    "doc_soma": doc_soma,
                }

                if remaining is not None:
                    remaining.discard(id_interno)
                    if not remaining:
                        break

            logger.info(
                "      Cache construído com %s registros indexados",
                len(self.contaordem_cache),
            )

        except Exception as e:
            logger.error(f"Erro ao carregar CONTAORDEM: {e}")
            raise

    def lookup_doc_soma(self, id_interno: str) -> dict | None:
        """Pesquisa DOC.SOMA em CONTAORDEM usando ID_INTERNO.

        Só devolve ``found=True`` quando o ``DOC. SOMA`` da CONTAORDEM
        passa a validação de formato (7 caracteres numéricos). Valores
        vazios ou fora do formato (ex. ``ANALISAR``) são tratados como
        "não encontrado" e podem ser reprocessados num run seguinte.
        """
        if id_interno in self.contaordem_cache:
            cached = self.contaordem_cache[id_interno]
            doc_soma = cached["doc_soma"]

            if doc_soma:
                if is_valid_doc_soma(doc_soma):
                    return {
                        "found": True,
                        "doc_soma": doc_soma,
                        "row_number": cached["row_number"],
                    }
                logger.warning(
                    "DOC.SOMA inválido em CONTAORDEM para %s: %r "
                    "(esperado %s dígitos numéricos)",
                    id_interno,
                    doc_soma,
                    DOC_SOMA_LENGTH,
                )

        return {"found": False, "doc_soma": None}
