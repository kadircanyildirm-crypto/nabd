"""Nabd's vocabulary: cells, readings, verdicts, the registry.

Everything the detector reasons over is a frozen dataclass defined here, and
nothing here imports a framework or an SDK. The enums carry the platform's own
vocabulary — `Low` / `Medium` / `High` is what Congestion Insights returns, and
the reachability values map one-to-one onto Device Status — so no translation
layer appears between a live response and a decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    """CAMARA `congestionLevel`. UNKNOWN is a missing or empty response."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    UNKNOWN = "Unknown"


class Reach(str, Enum):
    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


class Vulnerability(str, Enum):
    """Registry classes, in triage order. Lower `priority` is served first."""

    MEDICAL_DEPENDENT = "medical-dependent"
    DISABLED = "disabled"
    ELDERLY = "elderly"
    PILGRIM_GROUP = "pilgrim-group"
    LONE_WORKER = "lone-worker"

    @property
    def priority(self) -> int:
        return list(Vulnerability).index(self)


@dataclass(frozen=True)
class Cell:
    """One cell of the monitored area, with the fixed sentinel device that reads it.

    `sentinel` is a municipal or operator-owned SIM, never a member of the public.
    A cell without a sentinel is unmonitored and is never counted as dark.
    """

    id: str
    row: int
    col: int
    lat: float
    lon: float
    sentinel: str | None = None


@dataclass(frozen=True)
class Grid:
    cells: tuple[Cell, ...]
    rows: int
    cols: int
    spacing_m: float

    def by_id(self, cell_id: str) -> Cell:
        for cell in self.cells:
            if cell.id == cell_id:
                return cell
        raise KeyError(cell_id)

    def at(self, row: int, col: int) -> Cell | None:
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self.cells[row * self.cols + col]
        return None

    def neighbours(self, cell_id: str) -> tuple[str, ...]:
        """Eight-way adjacency. Diagonal contact still counts as contiguous."""
        cell = self.by_id(cell_id)
        out = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                other = self.at(cell.row + dr, cell.col + dc)
                if other is not None:
                    out.append(other.id)
        return tuple(out)

    def monitored(self) -> tuple[Cell, ...]:
        return tuple(c for c in self.cells if c.sentinel)

    def area_km2(self, n_cells: int) -> float:
        return round(n_cells * (self.spacing_m / 1000.0) ** 2, 1)

    def centroid(self, cell_ids: tuple[str, ...]) -> tuple[float, float]:
        cells = [self.by_id(c) for c in cell_ids]
        return (
            sum(c.lat for c in cells) / len(cells),
            sum(c.lon for c in cells) / len(cells),
        )

    def block(self, centre: str, radius: int) -> tuple[str, ...]:
        """The square of cells within `radius` rows/cols of `centre`, in grid order."""
        c = self.by_id(centre)
        out = []
        for cell in self.cells:
            if abs(cell.row - c.row) <= radius and abs(cell.col - c.col) <= radius:
                out.append(cell.id)
        return tuple(out)

    def ring(self, cells: tuple[str, ...]) -> tuple[str, ...]:
        """Cells adjacent to `cells` but not in it."""
        inside = set(cells)
        out: list[str] = []
        for cell_id in cells:
            for n in self.neighbours(cell_id):
                if n not in inside and n not in out:
                    out.append(n)
        return tuple(out)


@dataclass(frozen=True)
class Reading:
    """What the two detection APIs said about one cell on one pass."""

    cell: str
    t: float
    reach: Reach
    congestion: Level
    confidence: int | None = None


Snapshot = dict[str, Reading]


@dataclass(frozen=True)
class Person:
    """One opt-in registry entry. Pseudonymous: the command centre sees the id."""

    id: str
    vulnerability: Vulnerability
    home_cell: str
    msisdn: str


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    radius_m: int
    age_s: float


@dataclass(frozen=True)
class Maintenance:
    """A scheduled outage the operator has told us about. Silence inside it is expected."""

    ticket: str
    cells: tuple[str, ...]
    start: float
    end: float

    def covers(self, cell: str, t: float) -> bool:
        return cell in self.cells and self.start <= t < self.end


@dataclass(frozen=True)
class Evidence:
    """One named observation the detector weighed, and what it measured.

    Evidence is how the detection layer stays extensible. Each signal is a small
    named function that turns the pass into one of these; the verdict is a count
    over them, never a hard-coded pair. A new network surface becomes a new
    entry in `detector.CORROBORATIONS` and nothing else moves — the reason a
    future aggregate API can be added as extra evidence rather than a redesign.

    `role` separates the two ways evidence acts. A *gate* is a necessary
    condition: it can veto a declaration on its own but never causes one. A
    *corroboration* is supporting evidence: one makes a MEDIUM footprint, two
    make a HIGH one, none is an abstention.
    """

    name: str
    role: str  # "gate" | "corroboration"
    present: bool
    detail: str
    source: str  # the surface it was read from

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "present": self.present,
            "detail": self.detail,
            "source": self.source,
        }


class Kind(str, Enum):
    QUIET = "QUIET"  # nothing anomalous, or an anomaly already explained
    CANDIDATE = "CANDIDATE"  # a footprint seen once; held for confirmation
    DECLARE = "DECLARE"  # a footprint confirmed and published
    UPDATE = "UPDATE"  # the published footprint changed shape
    SUSTAIN = "SUSTAIN"  # the published footprint holds
    ABSTAIN = "ABSTAIN"  # an anomaly seen, deliberately not declared, with the reason
    CLEAR = "CLEAR"  # the footprint has come back


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    t: float
    cells: tuple[str, ...] = ()
    confidence: Confidence | None = None
    reason: str = ""
    signals: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    # De-duplication key for an abstention: the same explained anomaly is
    # reported once, then held quietly rather than repeated every pass.
    key: str = ""

    @property
    def footprint_active(self) -> bool:
        return self.kind in (Kind.DECLARE, Kind.UPDATE, Kind.SUSTAIN)


@dataclass(frozen=True)
class TriageEntry:
    person: str
    vulnerability: Vulnerability
    cell: str
    reach: Reach
    location: Location | None
    unreachable_since: float | None

    def rank_key(self) -> tuple[int, float]:
        return (self.vulnerability.priority, self.unreachable_since or math.inf)
