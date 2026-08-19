"""Compatibility wrapper for the extrato transfer + matching service."""

from __future__ import annotations

from src.gmail_to_sheets.processes.extrato import transfer_matching_service as _impl


class _BatchWriterProxy:
    def __call__(self, *args, **kwargs):
        from src.gmail_to_sheets.services import transfer_matching_service as module

        return module.BatchWriter(*args, **kwargs)


class _BatchUpdaterProxy:
    def __call__(self, *args, **kwargs):
        from src.gmail_to_sheets.services import transfer_matching_service as module

        return module.BatchUpdater(*args, **kwargs)


BatchWriter = _BatchWriterProxy()
BatchUpdater = _BatchUpdaterProxy()
_impl.BatchWriter = BatchWriter
_impl.BatchUpdater = BatchUpdater
TransferMatchingService = _impl.TransferMatchingService

__all__ = ["BatchUpdater", "BatchWriter", "TransferMatchingService"]
