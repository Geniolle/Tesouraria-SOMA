"""Orchestrator for the Faturas Email process.

For each configured route (one per sender): pick the oldest matching inbox
message, upload every matching attachment to the route's Drive folder
(never overwriting - a name clash gets a ``(1)`` suffix), then apply the
route's Gmail label and archive the message so it leaves the queue.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.gmail_to_sheets.clients.drive_client import DriveClient
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import FaturasEmailRoute, load_settings

from .filename import build_drive_filename, next_available_name

logger = logging.getLogger(__name__)


class FaturasEmailOrchestrator:
    """Run the Gmail -> Drive attachment archiving pipeline."""

    def __init__(
        self,
        settings=None,
        gmail_client: GmailClient | None = None,
        drive_client: DriveClient | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.gmail_client = gmail_client
        self.drive_client = drive_client

    def run(self) -> dict[str, Any]:
        cfg = self.settings.faturas_email
        if not cfg.routes:
            logger.info("Faturas Email: nenhuma rota configurada")
            return self._summary()

        assert self.gmail_client is not None
        assert self.drive_client is not None

        tz = ZoneInfo(getattr(self.settings, "timezone", "Europe/Lisbon"))
        max_results = int(getattr(self.settings, "batch_size", 50) or 50)

        summary = self._summary()
        for route in cfg.routes:
            try:
                self._run_route(route, cfg.attachment_ext, tz, max_results, summary)
            except Exception:
                summary["errors"] += 1
                logger.exception(
                    "Faturas Email: falha na rota %s", route.sender
                )

        logger.info(
            "Faturas Email concluido: processados=%s enviados=%s "
            "renomeados=%s sem_anexo=%s erros=%s",
            summary["processed"],
            summary["uploaded"],
            summary["renamed"],
            summary["skipped_no_attachment"],
            summary["errors"],
        )
        return summary

    def _run_route(
        self,
        route: FaturasEmailRoute,
        default_ext: str,
        tz: ZoneInfo,
        max_results: int,
        summary: dict[str, Any],
    ) -> None:
        gmail = self.gmail_client
        drive = self.drive_client
        assert gmail is not None and drive is not None

        message_ids = gmail.search_messages(
            query=route.gmail_query(), max_results=max_results
        )
        if not message_ids:
            return

        message_id = self._select_oldest(message_ids)
        message = gmail.get_message(message_id)
        received = self._received_at(message, tz)
        ext = route.resolved_ext(default_ext)

        attachments = self._collect_attachments(message.get("payload", {}), ext)
        taken: set[str] | None = None
        uploaded_here = 0

        for att in attachments:
            if taken is None:
                taken = drive.list_child_names(route.drive_folder_id)
            base = build_drive_filename(
                received, route.filename_token, att["filename"]
            )
            final = next_available_name(base, taken)
            data = gmail.download_attachment(message_id, att["attachment_id"])
            drive.upload_bytes(
                final,
                data,
                att.get("mime_type") or "application/octet-stream",
                route.drive_folder_id,
            )
            taken.add(final)
            uploaded_here += 1
            summary["uploaded"] += 1
            if final != base:
                summary["renamed"] += 1

        if uploaded_here == 0:
            summary["skipped_no_attachment"] += 1
            logger.warning(
                "Faturas Email: email %s de %s sem anexo %s",
                message_id,
                route.sender,
                ext,
            )

        # Mark processed regardless: label + archive so the message leaves
        # the inbox and is not seen again on the next tick.
        gmail.add_label(message_id, route.label)
        gmail.archive_message(message_id)
        summary["processed"] += 1

    def _select_oldest(self, message_ids: list[str]) -> str:
        assert self.gmail_client is not None
        dated: list[tuple[str, int]] = []
        for msg_id in message_ids:
            try:
                msg = self.gmail_client.get_message(msg_id)
                internal = msg.get("internalDate")
                if internal:
                    dated.append((msg_id, int(internal)))
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Faturas Email: metadados falharam para %s: %s",
                    msg_id,
                    error,
                )
        if not dated:
            return message_ids[0]
        return min(dated, key=lambda item: item[1])[0]

    @staticmethod
    def _received_at(message: dict[str, Any], tz: ZoneInfo) -> datetime:
        internal = message.get("internalDate")
        if internal:
            return datetime.fromtimestamp(int(internal) / 1000, tz=tz)
        return datetime.now(tz)

    @staticmethod
    def _collect_attachments(
        payload: dict[str, Any],
        extension: str,
    ) -> list[dict[str, Any]]:
        """Walk the MIME tree and return parts whose filename matches."""
        want = (extension or "").lower()
        found: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = [payload]
        while stack:
            part = stack.pop()
            for child in part.get("parts", []) or []:
                stack.append(child)
            filename = (part.get("filename") or "").strip()
            attachment_id = (part.get("body", {}) or {}).get("attachmentId")
            if not filename or not attachment_id:
                continue
            if want and not filename.lower().endswith(want):
                continue
            found.append(
                {
                    "filename": filename,
                    "attachment_id": attachment_id,
                    "mime_type": part.get("mimeType", ""),
                }
            )
        return found

    @staticmethod
    def _summary() -> dict[str, Any]:
        return {
            "processed": 0,
            "uploaded": 0,
            "renamed": 0,
            "skipped_no_attachment": 0,
            "errors": 0,
        }
