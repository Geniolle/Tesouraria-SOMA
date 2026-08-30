"""Process registry for ordered managed-process execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .protocols import ManagedProcess


@dataclass
class ProcessRegistry:
    """Registry that keeps managed processes ordered by priority."""

    _processes: list[ManagedProcess] = field(default_factory=list)

    def __init__(self, processes: Iterable[ManagedProcess] | None = None):
        self._processes = []
        if processes:
            for process in processes:
                self.register(process)

    def register(self, process: ManagedProcess) -> None:
        """Register a process and keep the registry ordered."""
        self._processes.append(process)
        self._processes.sort(key=lambda item: (item.priority, item.name))

    def __iter__(self) -> Iterator[ManagedProcess]:
        return iter(self._processes)

    def __len__(self) -> int:
        return len(self._processes)

    def list(self) -> list[ManagedProcess]:
        """Return processes in execution order."""
        return list(self._processes)
