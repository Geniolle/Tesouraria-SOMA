"""Row matching and build helpers for the integrated transfer flow."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.gmail_to_sheets.processes.extrato.transfer_matching_layout import TransferMatchingLayout
from src.gmail_to_sheets.services.batch_updater import CLEAR_CELL

logger = logging.getLogger(__name__)

# Escrito em DOC. SOMA quando não há correspondência na CONSTANTES.
# Mantém a linha elegível para nova tentativa de matching em execuções futuras.
NO_MATCH_DOC_SOMA = "ANALISAR"

# Regra de reprocessamento de uma linha de CONTAORDEM já existente:
# procura-se referência na CONSTANTES apenas quando
#   - DOC. SOMA está vazio ou com o texto "ANALISAR" (ou "EM ERRO"), E
#   - PLANO DE CONTA está vazio.
# Se o PLANO DE CONTA já está preenchido, a linha está classificada e não é
# tocada (não fazer nada), mesmo que o DOC. SOMA ainda seja "ANALISAR".
_REPROCESSABLE_DOC_SOMA = {"", NO_MATCH_DOC_SOMA, "EM ERRO"}


def should_reprocess_row(doc_soma: str | None, plano_conta: str | None) -> bool:
    """True se DOC. SOMA está por resolver (vazio/ANALISAR/EM ERRO) e o
    PLANO DE CONTA está vazio."""
    doc_por_resolver = str(doc_soma or "").strip().upper() in _REPROCESSABLE_DOC_SOMA
    plano_vazio = not str(plano_conta or "").strip()
    return doc_por_resolver and plano_vazio


class TransferMatchingRowBuilder:
    """Builds target rows and resolves reference matches."""

    def __init__(self, layout: TransferMatchingLayout):
        self.layout = layout

    def prepare_with_matching(self, source_rows: list[list], source_ids_set: set[str] | None = None) -> dict:
        target_rows: list[list] = []
        status_updates: dict[int, str] = {}
        update_rows: dict[int, dict[str, str]] = {}
        stats = {
            "transferred": 0,
            "already_exists": 0,
            "updated": 0,
            "skipped_resolved": 0,
            "empty_id": 0,
            "with_status": 0,
            "matched": 0,
            "no_match": 0,
            "total_processed": 0,
        }

        for idx, source_row in enumerate(source_rows):
            row_number = idx + 2
            id_interno = self.layout.get_cell_value(source_row, "ID_INTERNO", self.layout.source_indices)
            id_normalized = self.layout.normalize_text(id_interno)

            if source_ids_set is not None and id_normalized not in source_ids_set:
                logger.debug(f"Row {row_number}: ID {id_interno} not in source_ids, skipping")
                continue

            stats["total_processed"] += 1

            if not id_interno:
                status_updates[row_number] = "Erro: ID vazio"
                stats["empty_id"] += 1
                continue

            status_idx = self.layout.get_index("STATUS", self.layout.source_indices)
            status_val = ""
            if status_idx is not None and status_idx < len(source_row):
                status_val = str(source_row[status_idx]).strip()
            if status_val and status_val.startswith("Erro"):
                stats["with_status"] += 1
                continue

            try:
                is_existing = id_normalized in self.layout.existing_ids
                current_doc_soma = ""
                if is_existing:
                    current_doc_soma = self.layout.existing_doc_soma.get(
                        id_normalized, ""
                    ).strip()
                    current_plano_conta = self.layout.existing_plano_conta.get(
                        id_normalized, ""
                    ).strip()
                    # Regra: só reprocessa se DOC. SOMA estiver por resolver
                    # (vazio/ANALISAR/EM ERRO) E PLANO DE CONTA estiver vazio.
                    # Se já está classificada, não faz nada.
                    if not should_reprocess_row(current_doc_soma, current_plano_conta):
                        stats["already_exists"] += 1
                        stats["skipped_resolved"] += 1
                        logger.debug(
                            f"Row {row_number}: DOC. SOMA '{current_doc_soma}' / "
                            f"PLANO DE CONTA '{current_plano_conta}' - não reprocessa"
                        )
                        continue

                match = self.find_match(source_row)
                if match:
                    stats["matched"] += 1
                    logger.debug(f"Row {row_number}: Match found")
                else:
                    stats["no_match"] += 1
                    logger.debug(f"Row {row_number}: No match - marking DOC.SOMA as {NO_MATCH_DOC_SOMA}")

                if is_existing:
                    target_row_num = self.layout.existing_ids[id_normalized]
                    stats["already_exists"] += 1
                    if match:
                        row_update = {
                            "PLANO DE CONTA": match.get("plano_conta", ""),
                            "CENTRO DE CUSTO": match.get("centro_custo", ""),
                            "DESCRIÇÃO SOMA": match.get("desc_soma", ""),
                            "TIPO": match.get("tipo", ""),
                            "FORMA DE PAGAMENTO": match.get("forma_pag", ""),
                            "CAIXA": match.get("caixa", ""),
                            "CAIXA SAIDA": match.get("caixa_saida", ""),
                        }
                        matched_doc_soma = match.get("doc_soma", "")
                        if matched_doc_soma:
                            row_update["DOC. SOMA"] = matched_doc_soma
                        elif current_doc_soma:
                            # Match sem DOC. SOMA na CONSTANTES: limpa o sentinela
                            # (ANALISAR/EM ERRO); o documento real é atribuído a
                            # jusante pelo push do SOMA.
                            row_update["DOC. SOMA"] = CLEAR_CELL
                        update_rows[target_row_num] = row_update
                        stats["updated"] += 1
                    elif current_doc_soma.upper() != NO_MATCH_DOC_SOMA:
                        update_rows[target_row_num] = {"DOC. SOMA": NO_MATCH_DOC_SOMA}
                        stats["updated"] += 1
                else:
                    target_row = self.build_target_row(source_row)
                    if match:
                        target_row = self.enrich_with_match(target_row, match, source_row)
                    else:
                        self.layout.set_cell_value(
                            target_row,
                            "DOC. SOMA",
                            NO_MATCH_DOC_SOMA,
                            self.layout.target_indices,
                        )
                    target_rows.append(target_row)
                    self.layout.existing_ids[id_normalized] = len(target_rows)
                    status_updates[row_number] = "Transferido"
                    stats["transferred"] += 1
            except Exception as e:
                status_updates[row_number] = f"Erro: {str(e)[:40]}"
                logger.error(f"Row {row_number}: {e}")

        return {
            "target_rows": target_rows,
            "status_updates": status_updates,
            "update_rows": update_rows,
            "stats": stats,
        }

    def find_match(self, source_row: list) -> Optional[dict]:
        desc_norm = self.layout.normalize_match_text(
            self.layout.get_cell_value(source_row, "DESCRIÇÃO", self.layout.source_indices)
        )
        tipo = self.layout.get_cell_value(source_row, "TIPO", self.layout.source_indices).upper()
        valor = self.layout.parse_amount(
            self.layout.get_cell_value(source_row, "IMPORTÂNCIA", self.layout.source_indices)
        )

        for ref_row in self.layout.ref_data:
            ref_texto = self.layout.get_cell_value(ref_row, "TEXTO", self.layout.ref_indices)
            ref_tipo = self.layout.get_cell_value(ref_row, "TIPO", self.layout.ref_indices).upper()
            ref_valor_raw = self.layout.get_cell_value(ref_row, "VALOR", self.layout.ref_indices)

            ref_texto_norm = self.layout.normalize_match_text(ref_texto)
            if not ref_texto_norm:
                continue

            text_ok = (desc_norm in ref_texto_norm) or (ref_texto_norm in desc_norm)
            type_ok = (tipo == ref_tipo) or (
                self.layout.normalize_text(tipo) == self.layout.normalize_text(ref_tipo)
            )

            value_ok = True
            if ref_valor_raw and ref_valor_raw.strip():
                ref_valor = self.layout.parse_amount(ref_valor_raw)
                value_ok = abs(valor - ref_valor) < 0.01

            if text_ok and type_ok and value_ok:
                return {
                    "ref_texto": ref_texto,
                    "doc_soma": self.layout.get_cell_value(ref_row, "DOC. SOMA", self.layout.ref_indices),
                    "plano_conta": self.layout.get_cell_value(ref_row, "PLANO DE CONTA", self.layout.ref_indices),
                    "centro_custo": self.layout.get_cell_value(ref_row, "CENTRO DE CUSTO", self.layout.ref_indices),
                    "desc_soma": self.layout.get_cell_value(ref_row, "DESCRIÇÃO SOMA", self.layout.ref_indices),
                    "tipo": self.layout.get_cell_value(ref_row, "TIPO", self.layout.ref_indices),
                    "forma_pag": self.layout.get_cell_value(ref_row, "FORMA DE PAGAMENTO", self.layout.ref_indices),
                    "caixa": self.layout.get_cell_value(ref_row, "CAIXA", self.layout.ref_indices),
                    "caixa_saida": self.layout.get_cell_value(ref_row, "CAIXA SAIDA", self.layout.ref_indices),
                }

        return None

    def build_target_row(self, source_row: list) -> list:
        row = [""] * len(self.layout.target_headers)
        data_mov = self.layout.get_cell_value(source_row, "DATA MOV.", self.layout.source_indices)
        desc = self.layout.get_cell_value(source_row, "DESCRIÇÃO", self.layout.source_indices)
        valor = self.layout.get_cell_value(source_row, "IMPORTÂNCIA", self.layout.source_indices)
        tipo = self.layout.get_cell_value(source_row, "TIPO", self.layout.source_indices)
        id_interno = self.layout.get_cell_value(source_row, "ID_INTERNO", self.layout.source_indices)

        values_dict = {
            "DATA MOV.": data_mov,
            "DESCRIÇÃO": self.layout.normalize_text(desc),
            "IMPORTÂNCIA": self.layout.format_number(abs(self.layout.parse_amount(valor))),
            "TIPO": tipo,
            "PERÍODO": self.layout.get_month_text(data_mov),
            "PROCESSO": "T_EXTRATO",
            "ID_INTERNO": id_interno,
        }

        for col_name, col_value in values_dict.items():
            self.layout.set_cell_value(row, col_name, col_value, self.layout.target_indices)

        logger.debug(f"Built row with {len([v for v in row if v])} non-empty cells out of {len(row)} total")
        return row

    def generate_sequential_description(self, data_mov: str, desc_soma_base: str) -> str:
        data_key = self.layout.get_day_key(data_mov)
        if not data_key:
            raise RuntimeError(f"DATA MOV. inválida para gerar sequencial: {data_mov!r}")
        desc_base_key = self.layout.normalize_match_text(desc_soma_base)
        if not desc_base_key:
            raise RuntimeError(f"Descrição SOMA inválida para gerar sequencial: {desc_soma_base!r}")
        key = f"{data_key}||{desc_base_key}"
        if key not in self.layout.seq_state:
            self.layout.seq_state[key] = {"max": 0, "base": desc_soma_base}
        self.layout.seq_state[key]["max"] += 1
        next_num = self.layout.seq_state[key]["max"]
        return f"{desc_soma_base} N{next_num:03d}"

    def enrich_with_match(
        self,
        target_row: list[Any],
        match: dict[str, Any],
        source_row: list[Any] | None = None,
    ) -> list[Any]:
        if match.get("plano_conta"):
            self.layout.set_cell_value(target_row, "PLANO DE CONTA", match["plano_conta"], self.layout.target_indices)
        if match.get("centro_custo"):
            self.layout.set_cell_value(target_row, "CENTRO DE CUSTO", match["centro_custo"], self.layout.target_indices)

        if match.get("desc_soma"):
            data_mov = self.layout.get_cell_value(source_row, "DATA MOV.", self.layout.source_indices) if source_row else ""
            desc_soma_base = match.get("desc_soma")
            if data_mov and desc_soma_base:
                desc_soma_sequential = self.generate_sequential_description(data_mov, desc_soma_base)
                self.layout.set_cell_value(target_row, "DESCRIÇÃO SOMA", desc_soma_sequential, self.layout.target_indices)
            else:
                self.layout.set_cell_value(target_row, "DESCRIÇÃO SOMA", desc_soma_base, self.layout.target_indices)

        if match.get("tipo"):
            self.layout.set_cell_value(target_row, "TIPO", match["tipo"], self.layout.target_indices)
        if match.get("forma_pag"):
            self.layout.set_cell_value(target_row, "FORMA DE PAGAMENTO", match["forma_pag"], self.layout.target_indices)
        if match.get("caixa"):
            self.layout.set_cell_value(target_row, "CAIXA", match["caixa"], self.layout.target_indices)
        if match.get("caixa_saida"):
            self.layout.set_cell_value(target_row, "CAIXA SAIDA", match["caixa_saida"], self.layout.target_indices)
        if match.get("doc_soma"):
            self.layout.set_cell_value(target_row, "DOC. SOMA", match["doc_soma"], self.layout.target_indices)
        return target_row

    def batch_update_existing(self, update_rows: dict) -> None:
        doc_soma_idx = self.layout.target_indices.get("DOC. SOMA")
        desc_soma_idx = self.layout.target_indices.get("DESCRIÇÃO SOMA")
        if not update_rows or (doc_soma_idx is None and desc_soma_idx is None):
            logger.warning("No valid columns to update")
            return

        requests = []
        for row_num, updates in update_rows.items():
            if "DOC. SOMA" in updates and doc_soma_idx is not None:
                requests.append({
                    "updateCells": {
                        "range": {
                            "sheetId": self.layout.get_sheet_id(self.layout.target_sheet),
                            "rowIndex": row_num - 1,
                            "columnIndex": doc_soma_idx,
                            "endColumnIndex": doc_soma_idx + 1,
                        },
                        "rows": [{"values": [{"userEnteredValue": {"stringValue": updates["DOC. SOMA"]}}]}],
                        "fields": "userEnteredValue",
                    }
                })
            if "DESCRIÇÃO SOMA" in updates and desc_soma_idx is not None:
                requests.append({
                    "updateCells": {
                        "range": {
                            "sheetId": self.layout.get_sheet_id(self.layout.target_sheet),
                            "rowIndex": row_num - 1,
                            "columnIndex": desc_soma_idx,
                            "endColumnIndex": desc_soma_idx + 1,
                        },
                        "rows": [{"values": [{"userEnteredValue": {"stringValue": updates["DESCRIÇÃO SOMA"]}}]}],
                        "fields": "userEnteredValue",
                    }
                })

        if requests:
            body = {"requests": requests}
            self.layout.sheets_client.service.spreadsheets().batchUpdate(
                spreadsheetId=self.layout.spreadsheet_id,
                body=body,
            ).execute()
            logger.info(f"Updated {len(update_rows)} existing rows")
