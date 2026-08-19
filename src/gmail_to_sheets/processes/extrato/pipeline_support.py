"""Shared helpers for the extrato pipeline."""

from __future__ import annotations

import logging
from decimal import Decimal

from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.models.transaction import MT940File
from src.gmail_to_sheets.processes.extrato.attachment_processor import AttachmentProcessor

logger = logging.getLogger(__name__)


def select_latest_message(gmail_client: GmailClient, message_ids: list[str]) -> str:
    """Select the message with the greatest internalDate."""
    if not message_ids:
        raise ValueError("No messages to select from")

    logger.info(f"      Selecting latest from {len(message_ids)} message(s)...")
    messages: list[tuple[str, int]] = []
    for msg_id in message_ids:
        try:
            msg = gmail_client.get_message(msg_id)
            internal_date = msg.get("internalDate")
            if internal_date:
                messages.append((msg_id, int(internal_date)))
            else:
                logger.warning(f"Message {msg_id} has no internalDate")
        except Exception as e:
            logger.warning(f"Failed to get metadata for {msg_id}: {e}")

    if not messages:
        raise ValueError(f"No messages with valid internalDate found (checked {len(message_ids)})")

    selected_id, selected_date = max(messages, key=lambda item: item[1])
    logger.info(f"      Selected message: {selected_id}")
    logger.info(f"      internalDate: {selected_date}")
    logger.info(f"      Total messages with valid dates: {len(messages)}")
    return selected_id


def validate_mt940_reconciliation(mt940_file: MT940File) -> dict:
    """Validate opening + transactions = closing."""
    opening_balance = mt940_file.header.saldo_abertura
    closing_balance = mt940_file.footer.saldo_fecho
    transaction_total = sum((transaction.valor for transaction in mt940_file.transactions), Decimal("0.00"))
    calculated_balance = opening_balance + transaction_total
    difference = (closing_balance - calculated_balance).quantize(Decimal("0.01"))

    logger.info(f"      Opening balance: {opening_balance}")
    logger.info(f"      Transaction sum: {transaction_total}")
    logger.info(f"      Closing balance: {closing_balance}")
    logger.info(f"      Difference: {difference}")

    if abs(difference) > Decimal("0.01"):
        raise ValueError(
            f"Reconciliation failed: opening ({opening_balance}) + transactions ({transaction_total}) = "
            f"calculated ({calculated_balance}), but closing is {closing_balance} (difference: {difference})"
        )

    logger.info("      ✓ Reconciliation validated")
    return {
        "opening_balance": opening_balance,
        "transaction_total": transaction_total,
        "closing_balance": closing_balance,
        "calculated_balance": calculated_balance,
        "difference": difference,
    }


def download_and_parse_attachment(gmail_client: GmailClient, message_id: str):
    """Download the first attachment and parse it as MT940."""
    attachments = gmail_client.get_attachments(message_id)
    if not attachments:
        logger.warning("No .txt attachments found")
        return None

    processor = AttachmentProcessor(gmail_client)
    mt940_file = processor.process_attachment(
        message_id=message_id,
        attachment_id=attachments[0].get("attachment_id"),
        filename=attachments[0]["filename"],
    )
    logger.info(f"      Parsed {mt940_file.total_transactions} transactions")
    return mt940_file


def archive_email(gmail_client: GmailClient, message_id: str, backup_label_name: str) -> None:
    """Move an email to the backup folder."""
    label_id = gmail_client.get_or_create_label_id(backup_label_name)
    logger.info(f"      Resolved label ID: {label_id}")
    gmail_client.service.users().messages().modify(
        userId="me",
        id=message_id,
        body={
            "addLabelIds": [label_id],
            "removeLabelIds": ["INBOX"],
        },
    ).execute()
    logger.info(f"      Added backup label '{backup_label_name}'")
    logger.info("      Email removed from INBOX")
    logger.info("      Email archived successfully")
