# -*- coding: utf-8 -*-
"""The platform's silence is not the network's.

Every reading the agent has comes through an API. When that API stops
answering — key revoked, platform down, the operator's own link gone — the
agent knows nothing, and must say so, rather than reporting a quiet morning
or, worse, clearing a footprint because the cells it can no longer see are
"not dark".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nabd.detector import DEFAULT_POLICY, Policy, State, apply, blind, correlate, declare, exclude  # noqa: E402
from nabd.gateway import Call  # noqa: E402
from nabd.loop import NabdLoop  # noqa: E402
from nabd.model import Kind, Level, Reach  # noqa: E402
from nabd.scene import build  # noqa: E402


class Platform:
    """A gateway whose answers the test dictates, per device, per pass."""

    backend = "test"

    def __init__(self, grid, script):
        self.calls: list[Call] = []
        self.now = 0.0
        self.grid = grid
        self.script = script  # (device, t) -> Reach

    def tick(self, t):
        self.now = t

    def _log(self, name, device, ok):
        self.calls.append(Call(name=name, request={"device": device}, response={} if ok else None, ok=ok, t=self.now))

    def reachability(self, device):
        reach = self.script(device, self.now)
        self._log("device_status.connectivity", device, reach is not Reach.UNKNOWN)
        return reach

    def congestion(self, device):
        reach = self.script(device, self.now)
        self._log("congestion.query", device, reach is not Reach.UNKNOWN)
        return (Level.UNKNOWN, None) if reach is not Reach.REACHABLE else (Level.LOW, 85)

    def location(self, device, max_age_s=3600):
        self._log("location.retrieve", device, False)
        return None


def _agent(script):
    scene = build("quake")
    grid = scene.world.grid
    gw = Platform(grid, script)
    return NabdLoop(gw, grid, registry=(), calendar=(), name="test-blind"), grid


def test_a_dead_platform_is_an_abstention_not_a_quiet_morning():
    agent, _ = _agent(lambda device, t: Reach.UNKNOWN)
    rec = agent.step(0.0)
    assert rec.kind == Kind.ABSTAIN.value
    assert "no reading from 100 of 100" in rec.reason
    assert "not the network" in rec.reason
    assert any("no reading" in s for s in rec.signals)


def test_half_the_platform_missing_is_still_blind_and_a_third_is_not():
    devices = {}

    def script(device, t):
        return Reach.UNKNOWN if devices.setdefault(device, len(devices)) < 60 else Reach.REACHABLE

    agent, _ = _agent(script)
    assert agent.step(0.0).kind == Kind.ABSTAIN.value

    devices.clear()

    def script2(device, t):
        return Reach.UNKNOWN if devices.setdefault(device, len(devices)) < 30 else Reach.REACHABLE

    agent, _ = _agent(script2)
    assert agent.step(0.0).kind == Kind.QUIET.value, "a third missing is degraded, not blind"


def test_a_platform_outage_does_not_clear_a_footprint():
    """Declare a block, then lose the platform for longer than clear_after_s.
    The footprint must be held every pass and never cleared."""
    scene = build("quake")
    grid = scene.world.grid
    block = {c.id for c in grid.cells if 3 <= c.row <= 5 and 3 <= c.col <= 5}
    ring = {n for c in block for n in grid.neighbours(c)} - block
    cell_of = {}

    def script(device, t):
        cell = cell_of[device]
        if t >= 120:  # the platform dies after the declaration
            return Reach.UNKNOWN
        return Reach.UNREACHABLE if cell in block else Reach.REACHABLE

    gw = Platform(grid, script)
    # congestion must make the ring hot for the declaration to happen
    def congestion(device):
        reach = script(device, gw.now)
        gw._log("congestion.query", device, reach is not Reach.UNKNOWN)
        if reach is Reach.UNKNOWN:
            return Level.UNKNOWN, None
        return (Level.HIGH, 80) if cell_of[device] in ring else (Level.LOW, 85)

    gw.congestion = congestion
    for c in grid.cells:
        if c.sentinel:
            cell_of[c.sentinel] = c.id
    agent = NabdLoop(gw, grid, registry=(), calendar=(), name="test-blind")

    kinds = []
    t = 0.0
    while t <= 1500:
        kinds.append(agent.step(t).kind)
        t += 30.0
    assert Kind.DECLARE.value in kinds[:4]
    after = kinds[4:]
    assert Kind.CLEAR.value not in after, "the instrument failed; the disaster did not end"
    assert all(k == Kind.SUSTAIN.value for k in after), after
    assert agent.state.footprint, "the footprint is still published"
    last = agent.log.records[-1]
    assert "nothing confirmed, nothing cleared" in last.reason


def test_blind_passes_teach_the_baseline_nothing():
    grid = build("quiet").world.grid
    state = State()
    policy = Policy()
    snapshot = {c.id: type("R", (), {"reach": Reach.UNKNOWN, "congestion": Level.UNKNOWN})() for c in grid.monitored()}
    corr = correlate(snapshot, grid, 0.0)
    assert blind(corr, policy)
    verdict = declare(corr, exclude(corr, grid, (), 0.0), state, grid, policy, 0.0)
    apply(verdict, corr, state, policy, 0.0)
    assert state.passes_observed == 0
    assert None not in state.explained


def test_the_six_scenes_never_see_a_blind_pass():
    """The offline simulator always answers for a sentinel, so nothing above
    can have moved the evidence the film and the deck were made from."""
    for name in ("quiet", "quake", "noise", "degraded", "maras", "atlas"):
        scene = build(name)
        from nabd.loop import sense
        from nabd.scene import build_gateway

        gw = build_gateway("offline", world=scene.world)
        gw.tick(0.0)
        snapshot = sense(gw, scene.world.grid, 0.0)
        corr = correlate(snapshot, scene.world.grid, 0.0)
        assert corr.unknown == (), name
        assert not blind(corr, DEFAULT_POLICY)
