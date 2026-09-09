"""The world the offline platform answers from: a grid, a registry, and events.

The simulator is a model of what the network *sees*, not of the disaster. A
quake here is nothing more than "these cells stop answering at t0 and the ring
around them goes to High" — which is exactly the shape the detector is built to
recognise, and exactly the shape a jury can check against the public record of
February 2023, when the cells around the epicentre fell silent while the
surviving ones drowned in calls.

The look-alikes matter as much as the disaster. A single-cell fault, a
maintenance window and a stadium crowd each reproduce one of the disaster's
signals without the others; the noise scene runs all three so the abstentions
are demonstrated, not asserted.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from nabd.model import Cell, Grid, Level, Location, Maintenance, Person, Reach, Vulnerability

# Kahramanmaraş city centre — the reference case, and a real place.
KAHRAMANMARAS = (37.5858, 36.9371)
ROW_LETTERS = "ABCDEFGHIJKLMNOPQRST"


def make_grid(
    rows: int = 10,
    cols: int = 10,
    centre: tuple[float, float] = KAHRAMANMARAS,
    spacing_m: float = 670.0,
) -> Grid:
    """A rows×cols grid of cells, one sentinel each, row A at the north."""
    lat0, lon0 = centre
    dlat = spacing_m / 111_000.0
    dlon = spacing_m / (111_000.0 * math.cos(math.radians(lat0)))
    cells = []
    for r in range(rows):
        for c in range(cols):
            cells.append(
                Cell(
                    id=f"{ROW_LETTERS[r]}{c + 1}",
                    row=r,
                    col=c,
                    lat=round(lat0 + (rows / 2 - 0.5 - r) * dlat, 5),
                    lon=round(lon0 + (c - cols / 2 + 0.5) * dlon, 5),
                    sentinel=f"+9990{r:02d}{c:02d}",
                )
            )
    return Grid(tuple(cells), rows, cols, spacing_m)


def assign_sentinels(grid: Grid, msisdns: list[str]) -> Grid:
    """Rebind the grid to real devices — the live backend's few allocated numbers.

    Cells beyond the allocation become unmonitored. This is what a live run
    looks like on a sandbox account: the contract proven on a handful of cells,
    not a city-wide grid.
    """
    cells = []
    for i, cell in enumerate(grid.cells):
        sentinel = msisdns[i] if i < len(msisdns) else None
        cells.append(Cell(cell.id, cell.row, cell.col, cell.lat, cell.lon, sentinel))
    return Grid(tuple(cells), grid.rows, grid.cols, grid.spacing_m)


def make_registry(grid: Grid, n: int = 48, seed: int = 7) -> tuple[Person, ...]:
    """An opt-in registry, denser toward the centre, pseudonymous ids only."""
    rng = random.Random(seed)
    weights = []
    for cell in grid.cells:
        d = math.hypot(cell.row - (grid.rows - 1) / 2, cell.col - (grid.cols - 1) / 2)
        weights.append(math.exp(-(d**2) / 8.0))
    classes = list(Vulnerability)
    class_weights = [3, 4, 8, 3, 2]
    people = []
    for i in range(n):
        home = rng.choices(grid.cells, weights=weights, k=1)[0]
        people.append(
            Person(
                id=f"R-{i + 1:03d}",
                vulnerability=rng.choices(classes, weights=class_weights, k=1)[0],
                home_cell=home.id,
                msisdn=f"+9991{i + 1:04d}",
            )
        )
    return tuple(people)


# ----------------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Quake:
    """Core cells go dark at t0; the ring goes High while everyone calls at once."""

    t0: float
    core: tuple[str, ...]
    ring: tuple[str, ...]
    ring_until: float | None = None
    casualty_rate: float = 0.7
    # person id -> time they are reachable again (found, moved, phone charged)
    recoveries: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CellFault:
    """One sentinel unreachable, neighbours unaffected. Equipment, not impact."""

    t0: float
    t1: float
    cell: str


@dataclass(frozen=True)
class Peak:
    """High congestion with every sentinel still answering. A crowd, not impact."""

    t0: float
    t1: float
    cells: tuple[str, ...]


@dataclass(frozen=True)
class Flaky:
    """A block that drops out on its own schedule. Chronic degradation, not impact.

    The hardest look-alike, because it reproduces every signal an impact has —
    a contiguous block, going dark together, with nothing on the maintenance
    calendar to explain it. A bad backhaul link, a rural edge, a site running on
    a generator that cuts out. The only thing that separates it from a disaster
    is history: here, silence is the local normal.
    """

    cells: tuple[str, ...]
    windows: tuple[tuple[float, float], ...]

    def dark_at(self, t: float) -> bool:
        return any(a <= t < b for a, b in self.windows)


@dataclass(frozen=True)
class Dropout:
    """Sentinels that fail on their own, at random, one at a time.

    Real fixed devices do this: a SIM loses registration for a pass, a modem
    reboots, a meter's battery dips. None of it is an impact, and a detector
    that cannot live with it would cry wolf every morning. Each cell is
    unreachable on each pass independently with probability `rate`, drawn from
    the world's seed so a run is repeatable.
    """

    rate: float
    t0: float = 0.0

    def dark(self, world: "World", cell_id: str, t: float) -> bool:
        return t >= self.t0 and world._unit("dropout", cell_id, int(t // 30)) < self.rate


@dataclass(frozen=True)
class Rupture:
    """Outage driven by a measured intensity field instead of a drawn shape.

    `mmi` is the estimated macroseismic intensity per cell, read from a real
    ShakeMap; see `nabd/shakemap.py` for the provenance and for why the two
    thresholds below are an assumption rather than a finding.

    Two mechanisms, both reported from the 2023 event. Above `collapse_mmi` the
    mast goes with the building it is mounted on, and the cell is dark from the
    first second. Between `power_mmi` and `collapse_mmi` the site survives the
    shaking and then loses mains power: it runs on battery and goes dark later,
    sooner where the shaking was worse. Below `power_mmi` it stays up and
    saturates, because everyone in reach is calling at once.
    """

    t0: float
    mmi: dict[str, float]
    collapse_mmi: float = 8.0
    power_mmi: float = 7.0
    battery_s: float = 180.0
    surge_s: float | None = None
    # Not everyone inside a dark cell is unreachable: some are picked up by a
    # neighbouring mast that survived. The rest are the people triage is for.
    covered_rate: float = 0.3

    def dark_from(self, cell_id: str) -> float | None:
        """When this cell stops answering, or None if it survives the scene."""
        v = self.mmi.get(cell_id)
        if v is None:
            return None
        if v >= self.collapse_mmi:
            return self.t0
        if v >= self.power_mmi:
            span = self.collapse_mmi - self.power_mmi
            drained = (self.collapse_mmi - v) / span  # 0 at the collapse edge, 1 at the power edge
            return self.t0 + self.battery_s * (1.0 + 2.0 * drained)
        return None


Event = Quake | CellFault | Peak | Flaky | Dropout | Rupture


class World:
    def __init__(
        self,
        grid: Grid,
        registry: tuple[Person, ...] = (),
        events: tuple[Event, ...] = (),
        maintenance: tuple[Maintenance, ...] = (),
        seed: int = 7,
        medium_rate: float = 0.08,
    ) -> None:
        self.grid = grid
        self.registry = registry
        self.events = events
        self.maintenance = maintenance
        self.seed = seed
        self.medium_rate = medium_rate

    # -- deterministic noise ------------------------------------------------

    def _unit(self, *parts: object) -> float:
        digest = hashlib.sha256("|".join(map(str, (self.seed, *parts))).encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    # -- what the network sees --------------------------------------------

    def cell_state(self, cell_id: str, t: float) -> tuple[Reach, Level]:
        for ev in self.events:
            if isinstance(ev, Quake) and t >= ev.t0 and cell_id in ev.core:
                return Reach.UNREACHABLE, Level.UNKNOWN
            if isinstance(ev, CellFault) and ev.t0 <= t < ev.t1 and cell_id == ev.cell:
                return Reach.UNREACHABLE, Level.UNKNOWN
            if isinstance(ev, Flaky) and cell_id in ev.cells and ev.dark_at(t):
                return Reach.UNREACHABLE, Level.UNKNOWN
            if isinstance(ev, Dropout) and ev.dark(self, cell_id, t):
                return Reach.UNREACHABLE, Level.UNKNOWN
            if isinstance(ev, Rupture):
                dark_at = ev.dark_from(cell_id)
                if dark_at is not None and t >= dark_at:
                    return Reach.UNREACHABLE, Level.UNKNOWN
        for m in self.maintenance:
            if m.covers(cell_id, t):
                return Reach.UNREACHABLE, Level.UNKNOWN
        for ev in self.events:
            if isinstance(ev, Quake) and t >= ev.t0 and cell_id in ev.ring:
                if ev.ring_until is None or t < ev.ring_until:
                    return Reach.REACHABLE, Level.HIGH
            if isinstance(ev, Peak) and ev.t0 <= t < ev.t1 and cell_id in ev.cells:
                return Reach.REACHABLE, Level.HIGH
            if isinstance(ev, Rupture) and t >= ev.t0 and cell_id in ev.mmi:
                # Still answering, inside the felt area: saturated, because
                # everyone who can call is calling at the same moment.
                if ev.surge_s is None or t < ev.t0 + ev.surge_s:
                    return Reach.REACHABLE, Level.HIGH
        # Routine background: an occasional Medium, stable over five-minute windows
        # so it reads as real traffic rather than flicker.
        if self._unit("bg", cell_id, int(t // 300)) < self.medium_rate:
            return Reach.REACHABLE, Level.MEDIUM
        return Reach.REACHABLE, Level.LOW

    def person_state(self, person: Person, t: float) -> tuple[Reach, Location]:
        home = self.grid.by_id(person.home_cell)
        jitter_lat = (self._unit("jlat", person.id) - 0.5) * 0.004
        jitter_lon = (self._unit("jlon", person.id) - 0.5) * 0.005
        lat, lon = round(home.lat + jitter_lat, 5), round(home.lon + jitter_lon, 5)
        for ev in self.events:
            if isinstance(ev, Rupture):
                dark_at = ev.dark_from(person.home_cell)
                if dark_at is not None and t >= dark_at:
                    if self._unit("cover", person.id) < ev.covered_rate:
                        # A neighbouring mast still reaches them.
                        return Reach.REACHABLE, Location(lat, lon, 900, age_s=25.0)
                    radius = 900 + int(self._unit("rad", person.id) * 900)
                    return Reach.UNREACHABLE, Location(lat, lon, radius, age_s=t - dark_at + 45.0)
            if isinstance(ev, Quake) and t >= ev.t0 and person.home_cell in ev.core:
                hit = self._unit("hit", person.id) < ev.casualty_rate
                back = ev.recoveries.get(person.id)
                if hit and (back is None or t < back):
                    # Last seen shortly before the event — the network keeps the
                    # last known position, which is what triage needs.
                    radius = 800 + int(self._unit("rad", person.id) * 700)
                    return Reach.UNREACHABLE, Location(lat, lon, radius, age_s=t - ev.t0 + 45.0)
                return Reach.REACHABLE, Location(lat, lon, 500, age_s=20.0)
        return Reach.REACHABLE, Location(lat, lon, 500, age_s=20.0)
