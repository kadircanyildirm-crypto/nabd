"""The deterministic core, one pass at a time, plus the two fuzzed invariants.

    python -m tests.test_nabd_detector

Every test here drives `nabd.detector` with synthetic snapshots: no gateway, no
framework, no world. The two fuzz tests at the end are the claims the privacy and
false-alarm arguments rest on, so they run thousands of random passes rather
than a handful of hand-picked ones.
"""

from __future__ import annotations

import random

from nabd import detector as D
from nabd.detector import Policy, State, assess
from nabd.gateway import OfflineGateway
from nabd.model import Confidence, Kind, Level, Maintenance, Reach, Reading, Snapshot
from nabd.triage import TriageState, run as run_triage
from nabd.world import Quake, World, make_grid, make_registry

GRID = make_grid()
POLICY = Policy()


def snap(dark=(), hot=(), t: float = 0.0) -> Snapshot:
    out: Snapshot = {}
    for cell in GRID.cells:
        if cell.id in dark:
            out[cell.id] = Reading(cell.id, t, Reach.UNREACHABLE, Level.UNKNOWN, None)
        elif cell.id in hot:
            out[cell.id] = Reading(cell.id, t, Reach.REACHABLE, Level.HIGH, 80)
        else:
            out[cell.id] = Reading(cell.id, t, Reach.REACHABLE, Level.LOW, 85)
    return out


CORE = GRID.block("F5", 1)
RING = GRID.ring(CORE)


def test_quiet_grid_is_quiet():
    state = State()
    v = assess(snap(), state, GRID, (), POLICY, 0)
    assert v.kind is Kind.QUIET, v
    assert not state.footprint


def test_single_cell_silence_abstains():
    state = State()
    v = assess(snap(dark=("C3",)), state, GRID, (), POLICY, 0)
    assert v.kind is Kind.ABSTAIN and "single-cell" in v.reason, v
    assert "C3" in v.reason


def test_two_cells_are_below_the_floor():
    state = State()
    v = assess(snap(dark=("C3", "C4")), state, GRID, (), POLICY, 0)
    assert v.kind is Kind.ABSTAIN and "below the 3-cell floor" in v.reason, v


def test_block_with_hot_ring_declares_high_after_confirmation():
    state = State()
    first = assess(snap(dark=CORE, hot=RING, t=0), state, GRID, (), POLICY, 0)
    assert first.kind is Kind.CANDIDATE, first
    second = assess(snap(dark=CORE, hot=RING, t=30), state, GRID, (), POLICY, 30)
    assert second.kind is Kind.DECLARE, second
    assert second.confidence is Confidence.HIGH
    assert set(second.cells) == set(CORE)
    assert any("hot ring" in s for s in second.signals), second.signals
    assert any("synchronised" in s for s in second.signals), second.signals
    assert state.footprint == second.cells and state.declared_at == 30


def test_block_without_ring_declares_medium():
    state = State()
    assess(snap(dark=CORE, t=0), state, GRID, (), POLICY, 0)
    v = assess(snap(dark=CORE, t=30), state, GRID, (), POLICY, 30)
    assert v.kind is Kind.DECLARE and v.confidence is Confidence.MEDIUM, v


def test_staggered_onset_without_ring_is_held():
    """Cells that go dark one by one over minutes, with no ring, never declare."""
    state = State()
    a = assess(snap(dark=("F5",), t=0), state, GRID, (), POLICY, 0)
    assert a.kind is Kind.ABSTAIN
    b = assess(snap(dark=("F5", "F6"), t=200), state, GRID, (), POLICY, 200)
    assert b.kind is Kind.ABSTAIN
    c = assess(snap(dark=("F5", "F6", "F4"), t=400), state, GRID, (), POLICY, 400)
    assert c.kind is Kind.ABSTAIN and "nothing corroborates" in c.reason, c
    assert any("staggered" in s for s in c.signals) and any("no hot ring" in s for s in c.signals), c.signals
    d = assess(snap(dark=("F5", "F6", "F4"), t=430), state, GRID, (), POLICY, 430)
    assert d.kind is Kind.QUIET and d.reason.startswith("holding"), d
    assert not state.footprint


def test_maintenance_block_is_expected_silence():
    ticket = Maintenance("MNT-1", ("I2", "I3", "J2", "J3"), 0, 600)
    state = State()
    v = assess(snap(dark=ticket.cells, t=10), state, GRID, (ticket,), POLICY, 10)
    assert v.kind is Kind.ABSTAIN and "MNT-1" in v.reason, v
    again = assess(snap(dark=ticket.cells, t=40), state, GRID, (ticket,), POLICY, 40)
    assert again.kind is Kind.QUIET and again.reason.startswith("holding"), again
    # Outside the window the same silence is no longer explained.
    state = State()
    late = assess(snap(dark=ticket.cells, t=700), state, GRID, (ticket,), POLICY, 700)
    assert late.kind is Kind.CANDIDATE, late


def test_maintenance_cells_are_removed_before_clustering():
    """A real block next to a maintenance block must not inherit the ticket's cells."""
    ticket = Maintenance("MNT-2", ("E3", "F3", "G3"), 0, 600)
    state = State()
    dark = CORE + ticket.cells
    assess(snap(dark=dark, hot=RING, t=0), state, GRID, (ticket,), POLICY, 0)
    v = assess(snap(dark=dark, hot=RING, t=30), state, GRID, (ticket,), POLICY, 30)
    assert v.kind is Kind.DECLARE, v
    assert set(v.cells) == set(CORE), v.cells


def test_congestion_without_silence_abstains():
    state = State()
    v = assess(snap(hot=GRID.block("D8", 1)), state, GRID, (), POLICY, 0)
    assert v.kind is Kind.ABSTAIN and "congestion without silence" in v.reason, v


def test_abstention_is_reported_once():
    state = State()
    kinds = [assess(snap(dark=("C3",), t=t), state, GRID, (), POLICY, t).kind for t in (0, 30, 60, 90)]
    assert kinds == [Kind.ABSTAIN, Kind.QUIET, Kind.QUIET, Kind.QUIET], kinds


def test_footprint_updates_when_the_block_grows():
    state = State()
    for t in (0, 30):
        assess(snap(dark=CORE, hot=RING, t=t), state, GRID, (), POLICY, t)
    bigger = GRID.block("F5", 1) + ("E7", "F7", "G7")
    v = assess(snap(dark=bigger, hot=GRID.ring(bigger), t=60), state, GRID, (), POLICY, 60)
    assert v.kind is Kind.UPDATE and "+3" in v.reason, v
    assert set(state.footprint) == set(bigger)


def test_footprint_clears_after_recovery():
    policy = Policy(clear_after_s=60)
    state = State()
    for t in (0, 30):
        assess(snap(dark=CORE, hot=RING, t=t), state, GRID, (), policy, t)
    held = assess(snap(t=60), state, GRID, (), policy, 60)
    assert held.kind is Kind.SUSTAIN and "reachable again" in held.reason, held
    cleared = assess(snap(t=120), state, GRID, (), policy, 120)
    assert cleared.kind is Kind.CLEAR, cleared
    assert not state.footprint


def test_no_declaration_without_a_contiguous_block():
    """Fuzz: whatever the noise, a footprint is always ≥ min_cells and contiguous."""
    rng = random.Random(11)
    checked = 0
    for _ in range(600):
        state = State()
        n_dark = rng.randint(0, 12)
        dark = tuple(rng.sample([c.id for c in GRID.cells], n_dark))
        hot = tuple(rng.sample([c.id for c in GRID.cells], rng.randint(0, 20)))
        for t in (0, 30, 60):
            v = assess(snap(dark=dark, hot=hot, t=t), state, GRID, (), POLICY, t)
            checked += 1
            if v.kind in (Kind.DECLARE, Kind.UPDATE, Kind.CANDIDATE):
                assert len(v.cells) >= POLICY.min_cells, v
                assert len(D.clusters(v.cells, GRID)) == 1, ("not contiguous", v.cells)
                assert set(v.cells) <= set(dark), ("footprint outside the dark set", v.cells)
    print(f"        {checked:,} fuzzed passes checked")


def test_triage_never_queries_outside_the_footprint():
    """Fuzz: every personal-device call is a registry member whose home is inside."""
    rng = random.Random(5)
    grid = make_grid()
    registry = make_registry(grid, n=60, seed=3)
    by_msisdn = {p.msisdn: p for p in registry}
    calls_checked = 0
    for _ in range(150):
        centre = rng.choice(grid.cells).id
        core = grid.block(centre, rng.randint(1, 2))
        world = World(grid, registry, events=(Quake(0.0, core, grid.ring(core)),), seed=rng.randint(0, 999))
        gateway = OfflineGateway(world)
        gateway.tick(10.0)
        result = run_triage(gateway, registry, core, TriageState(), 10.0)
        for call in gateway.calls:
            device = call.request["device"]["phoneNumber"]
            person = by_msisdn.get(device)
            assert person is not None, ("triage touched a non-registry device", device)
            assert person.home_cell in core, ("triage left the footprint", person)
            calls_checked += 1
        assert result.inside == sum(1 for p in registry if p.home_cell in core)
        assert all(e.location is not None for e in result.entries if e.reach is Reach.UNREACHABLE)
    print(f"        {calls_checked:,} personal-device calls, all inside a footprint")


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_detector"]))
