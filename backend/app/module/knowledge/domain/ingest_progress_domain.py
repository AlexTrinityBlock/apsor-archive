"""Thread-safe granular progress for one durable ingestion attempt.

Extraction runs inside the worker's bounded thread pool, while the job row and
its progress reporter live on the event loop. This tracker is the only shared
mutable object: it is lock-protected, performs no I/O, and never imports
``asyncio`` or a database module. Threads publish their position and the
reporter reads immutable snapshots at its own cadence.
"""

import threading
from dataclasses import dataclass
from typing import Final, Literal, cast

ProgressPhase = Literal["idle", "parsing", "chunking"]
ProgressUnit = Literal["page", "chunk", "sheet", "paragraph", "image"]

PHASE_IDLE: Final[ProgressPhase] = "idle"
PHASE_PARSING: Final[ProgressPhase] = "parsing"
PHASE_CHUNKING: Final[ProgressPhase] = "chunking"
PROGRESS_PHASES: Final[frozenset[str]] = frozenset(
    {PHASE_IDLE, PHASE_PARSING, PHASE_CHUNKING}
)

STAGE_UNITS: Final[frozenset[str]] = frozenset(
    {"page", "chunk", "sheet", "paragraph", "image"}
)

MAX_STAGE_UNIT_LENGTH: Final[int] = 16


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    """An immutable view of the tracker at one point in time.

    ``version`` increases on every mutation, so a reporter can tell an
    unchanged heartbeat from a real progress change.
    """

    phase: ProgressPhase
    done: int
    total: int | None
    unit: ProgressUnit | None
    version: int


class ProgressTracker:
    """Lock-protected parse/chunk counters shared with extraction threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._phase: ProgressPhase = PHASE_IDLE
        self._done = 0
        self._total: int | None = None
        self._unit: ProgressUnit | None = None
        self._version = 0

    @staticmethod
    def _validate_unit(unit: str) -> ProgressUnit:
        if unit not in STAGE_UNITS:
            raise ValueError(f"Unsupported progress unit: {unit!r}")
        return cast(ProgressUnit, unit)

    def begin(self, phase: ProgressPhase, total: int, unit: str) -> ProgressSnapshot:
        """Start one phase with a known unit count.

        ``total`` may be zero for an empty document; the reporter then keeps the
        phase at its starting percentage instead of dividing by zero.
        """
        if phase not in PROGRESS_PHASES or phase == PHASE_IDLE:
            raise ValueError(f"Unsupported progress phase: {phase!r}")
        if total < 0:
            raise ValueError("Progress total must not be negative")
        resolved_unit = self._validate_unit(unit)
        with self._lock:
            self._phase = phase
            self._done = 0
            self._total = total
            self._unit = resolved_unit
            self._version += 1
            return self._snapshot_locked()

    def advance(self, n: int = 1) -> ProgressSnapshot:
        """Advance by ``n`` units, clamped to the known total when present."""
        if n < 0:
            raise ValueError("Progress advance must not be negative")
        with self._lock:
            self._done = self._clamped(self._done + n)
            self._version += 1
            return self._snapshot_locked()

    def advance_to(self, done: int) -> ProgressSnapshot:
        """Set an absolute position, clamped to the known total when present."""
        if done < 0:
            raise ValueError("Progress position must not be negative")
        with self._lock:
            self._done = self._clamped(done)
            self._version += 1
            return self._snapshot_locked()

    def finish(self) -> ProgressSnapshot:
        """End granular reporting; the reporter falls back to heartbeats."""
        with self._lock:
            self._phase = PHASE_IDLE
            self._done = 0
            self._total = None
            self._unit = None
            self._version += 1
            return self._snapshot_locked()

    def snapshot(self) -> ProgressSnapshot:
        """Return an immutable, lock-consistent view."""
        with self._lock:
            return self._snapshot_locked()

    def _clamped(self, value: int) -> int:
        if self._total is None:
            return value
        return min(value, self._total)

    def _snapshot_locked(self) -> ProgressSnapshot:
        return ProgressSnapshot(
            phase=self._phase,
            done=self._done,
            total=self._total,
            unit=self._unit,
            version=self._version,
        )


__all__ = [
    "MAX_STAGE_UNIT_LENGTH",
    "PHASE_CHUNKING",
    "PHASE_IDLE",
    "PHASE_PARSING",
    "PROGRESS_PHASES",
    "STAGE_UNITS",
    "ProgressPhase",
    "ProgressSnapshot",
    "ProgressTracker",
    "ProgressUnit",
]
