"""Compatibility wrapper for the extrato transfer service."""

from __future__ import annotations

from src.gmail_to_sheets.processes.extrato import transfer_service as _impl


class _BatchWriterProxy:
    def __call__(self, *args, **kwargs):
        from src.gmail_to_sheets.services import transfer_service as module

        return module.BatchWriter(*args, **kwargs)


BatchWriter = _BatchWriterProxy()
_impl.BatchWriter = BatchWriter
TransferService = _impl.TransferService

__all__ = ["BatchWriter", "TransferService"]
