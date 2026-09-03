"""Pure helpers for naming the Drive file: ``AAAA_MM_DD_<token>_<original>``.

Separated from the orchestrator so the naming rules are trivially testable.
"""

from __future__ import annotations

import re
from datetime import datetime

_UNSAFE = re.compile(r'[\\/:*?"<>|]+')
_COPY_SUFFIX = re.compile(r"^(?P<stem>.*) \((?P<n>\d+)\)$")


def sanitize(name: str) -> str:
    """Drop characters that are awkward in file names; collapse whitespace."""
    cleaned = _UNSAFE.sub("_", str(name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "anexo"


def build_drive_filename(
    received: datetime,
    token: str,
    original_name: str,
) -> str:
    """``2026_02_15_Aluguel_fatura.pdf`` from the email date + token + name."""
    date_prefix = received.strftime("%Y_%m_%d")
    token_part = sanitize(token).replace(" ", "_")
    original = sanitize(original_name)
    return f"{date_prefix}_{token_part}_{original}"


def _split_ext(name: str) -> tuple[str, str]:
    dot = name.rfind(".")
    if dot > 0:
        return name[:dot], name[dot:]
    return name, ""


def next_available_name(name: str, taken: set[str]) -> str:
    """Return ``name`` or ``name (1)`` / ``name (2)`` ... not in ``taken``.

    The ``(n)`` counter is inserted before the extension, matching the way
    Google Drive itself disambiguates duplicate uploads.
    """
    if name not in taken:
        return name

    stem, ext = _split_ext(name)
    match = _COPY_SUFFIX.match(stem)
    if match:
        stem = match.group("stem")

    counter = 1
    while True:
        candidate = f"{stem} ({counter}){ext}"
        if candidate not in taken:
            return candidate
        counter += 1
