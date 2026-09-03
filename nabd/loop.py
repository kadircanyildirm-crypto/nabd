"""The plain runner: the same pass as `nabd/graph.py`, with no framework.

Exists so the LangGraph binding can be proven to wrap the core rather than
contain it: `tests/test_nabd_scenes` runs a scene through both and diffs the
evidence byte for byte. It also means the demonstration cannot be taken down by
a wheel that fails to install on the machine in the room.
"""

from __future__ import annotations

from nabd.brief import Composer, compose
from nabd.detector import DEFAULT_POLICY, Policy, State, assess
from nabd.log import EvidenceLog, Record, grid_string, record_from
from nabd.model import Grid, Maintenance, Person, Reading, Snapshot
from nabd.triage import TriageState, run as run_triage


def sense(gateway, grid: Grid, t: float) -> Snapshot:
    """Two calls per monitored cell: reachability first, then congestion.

    The order is fixed so both runners' evidence files line up call for call.
    """
    snapshot: Snapshot = {}
    for cell in grid.monitored():
        reach = gateway.reachability(cell.sentinel)
        level, confidence = gateway.congestion(cell.sentinel)
        snapshot[cell.id] = Reading(cell.id, t, reach, level, confidence)
    return snapshot


class NabdLoop:
    def __init__(
        self,
        gateway,
        grid: Grid,
        registry: tuple[Person, ...] = (),
        calendar: tuple[Maintenance, ...] = (),
        policy: Policy = DEFAULT_POLICY,
        name: str = "nabd",
        composer: Composer | None = None,
    ) -> None:
        self.gw = gateway
        self.grid = grid
        self.registry = registry
        self.calendar = calendar
        self.policy = policy
        self.composer = composer
        self.state = State()
        self.triage = TriageState()
        self.log = EvidenceLog(name)

    def step(self, t: float) -> Record:
        self.gw.tick(t)
        before = len(self.gw.calls)
        snapshot = sense(self.gw, self.grid, t)
        verdict = assess(snapshot, self.state, self.grid, self.calendar, self.policy, t)
        triage = None
        if verdict.footprint_active:
            triage = run_triage(self.gw, self.registry, verdict.cells, self.triage, t)
        brief = compose(verdict, triage, self.grid, self.composer)
        api_calls = [c.name for c in self.gw.calls[before:]]
        return self.log.add(record_from(verdict, triage, api_calls, brief, grid_string(snapshot, self.grid)))
