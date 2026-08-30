"""Persistent process health state for the central orchestrator."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ProcessHealthState(str, Enum):
    """Operational state exposed by the orchestrator health view."""

    IDLE = "IDLE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(slots=True)
class ProcessHealth:
    """Persistent health snapshot for one managed process."""

    process_name: str
    state: ProcessHealthState = ProcessHealthState.IDLE
    last_check_at: str | None = None
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    last_duration_seconds: float = 0.0
    last_error: str | None = None
    last_pending_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict) -> "ProcessHealth":
        """Build a health object from persisted JSON data."""
        raw_state = payload.get("state", ProcessHealthState.IDLE.value)
        try:
            state = ProcessHealthState(raw_state)
        except ValueError:
            state = ProcessHealthState.IDLE

        return cls(
            process_name=str(payload.get("process_name", "")),
            state=state,
            last_check_at=payload.get("last_check_at"),
            last_run_at=payload.get("last_run_at"),
            last_success_at=payload.get("last_success_at"),
            last_failure_at=payload.get("last_failure_at"),
            consecutive_failures=int(payload.get("consecutive_failures", 0) or 0),
            last_duration_seconds=float(payload.get("last_duration_seconds", 0.0) or 0.0),
            last_error=payload.get("last_error"),
            last_pending_count=int(payload.get("last_pending_count", 0) or 0),
        )


def utc_now_iso() -> str:
    """Return an RFC3339-compatible UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HealthStore:
    """Atomic JSON persistence for process health."""

    def __init__(self, path: Path | str = Path("data/orchestrator-health.json")) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, ProcessHealth]:
        """Load persisted health, tolerating missing/corrupt state."""
        if not self.path.exists():
            return {}

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_processes = payload.get("processes", {})
            health: dict[str, ProcessHealth] = {}
            for name, raw in raw_processes.items():
                if not isinstance(raw, dict):
                    continue
                raw = dict(raw)
                raw.setdefault("process_name", name)
                item = ProcessHealth.from_dict(raw)
                health[item.process_name] = item
            return health
        except Exception as error:
            logger.warning("Unable to load orchestrator health file: %s", error)
            return {}

    def save(self, health: dict[str, ProcessHealth]) -> None:
        """Persist health atomically without interrupting active data files."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "updated_at": utc_now_iso(),
            "processes": {
                name: asdict(item)
                for name, item in sorted(health.items())
            },
        }
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)
