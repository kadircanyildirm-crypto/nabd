"""The demonstration: three scenes, one agent, no account needed.

    python -m nabd.scene                     # all three scenes, offline
    python -m nabd.scene --scene quake -v    # every pass, including routine ones
    python -m nabd.scene --runner loop       # the same scenes without LangGraph
    python -m nabd.scene --backend live      # the contract run against real NaC
    python -m nabd.scene --console           # ...and rebuild the command-centre console

The story follows the mentor's five beats. A disaster strikes; the command
centre has nothing but scattered calls; Nabd declares the footprint inside the
first minute; responders get ranked zones and a list of who is unreachable and
where they were last seen; and the noise scene shows the same agent staying
silent through a cell fault, a maintenance window and a stadium crowd — each of
which reproduces one signal of a disaster without the others.

**Quiet** is the baseline: a monitored city on an ordinary morning.
**Quake** is the reference case, shaped on Kahramanmaraş: a block of nine cells
in the centre falls silent at once while the ring around it goes to High.
**Noise** is the false-alarm defence, three look-alikes in one run.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from nabd.gateway import EPOCH, OfflineGateway, write_calls
from nabd.log import clock
from nabd.model import Maintenance, Reach
from nabd.world import KAHRAMANMARAS, CellFault, Peak, Quake, World, assign_sentinels, make_grid, make_registry

STEP_S = 30.0


@dataclass
class Beat:
    t: float
    note: str


@dataclass
class Scenario:
    name: str
    world: World
    calendar: tuple[Maintenance, ...]
    beats: list[Beat]
    duration_s: float
    core: tuple[str, ...] = ()
    onset_t: float | None = None
    extra: dict = field(default_factory=dict)


def _quiet(seed: int) -> Scenario:
    grid = make_grid()
    registry = make_registry(grid, seed=seed)
    world = World(grid, registry, events=(), seed=seed)
    return Scenario(
        "quiet",
        world,
        (),
        [Beat(0, f"{clock(0)} — an ordinary morning. {len(grid.monitored())} cells monitored, {len(registry)} people on the opt-in registry.")],
        duration_s=300,
    )


def _quake(seed: int) -> Scenario:
    grid = make_grid()
    registry = make_registry(grid, seed=seed)
    onset = 125.0
    core = grid.block("F5", 1)
    ring = grid.ring(core)
    # First build without recoveries to learn who the model marks as hit, then
    # bring two of them back at 09:07 — one dug out, one who reached a live cell.
    probe = World(grid, registry, events=(Quake(onset, core, ring),), seed=seed)
    hit = [p.id for p in registry if p.home_cell in core and probe.person_state(p, onset + 1)[0] is Reach.UNREACHABLE]
    recoveries = {pid: 420.0 for pid in hit[:2]}
    world = World(grid, registry, events=(Quake(onset, core, ring, recoveries=recoveries),), seed=seed)
    inside = [p for p in registry if p.home_cell in core]
    beats = [
        Beat(0, f"{clock(0)} — an ordinary morning. {len(grid.monitored())} cells monitored, {len(registry)} people on the opt-in registry, {len(inside)} of them living in what is about to become the footprint."),
        Beat(onset, f"{clock(onset)} — earthquake. The seismometers have already said 'it happened'. Nobody yet knows which neighbourhoods have lost their people; the command centre has scattered calls and an overloaded network."),
        Beat(420, f"{clock(420)} — two registered people answer again: one reached, one moved to a working cell. The list must update without anyone touching it."),
    ]
    return Scenario("quake", world, (), beats, duration_s=600, core=core, onset_t=onset, extra={"recoveries": recoveries})


def _noise(seed: int) -> Scenario:
    grid = make_grid()
    registry = make_registry(grid, seed=seed)
    maintenance = Maintenance("MNT-2214", ("I2", "I3", "J2", "J3"), start=180, end=480)
    stadium = grid.block("D8", 1)
    world = World(
        grid,
        registry,
        events=(CellFault(60, 360, "C3"), Peak(300, 540, stadium)),
        maintenance=(maintenance,),
        seed=seed,
    )
    beats = [
        Beat(0, f"{clock(0)} — the same city, a different morning. Three things will happen that look like a disaster to a single sensor."),
        Beat(60, f"{clock(60)} — the base station serving C3 drops on a firmware fault. One cell silent, neighbours untouched."),
        Beat(180, f"{clock(180)} — a planned maintenance window opens on four cells in the south-west (ticket MNT-2214, on the calendar the operator shared)."),
        Beat(300, f"{clock(300)} — kick-off at the stadium: nine cells around D8 go to High congestion at once. Every sentinel still answers."),
    ]
    return Scenario("noise", world, (maintenance,), beats, duration_s=600, extra={"stadium": stadium})


BUILDERS = {"quiet": _quiet, "quake": _quake, "noise": _noise}


def build(name: str, seed: int = 7) -> Scenario:
    return BUILDERS[name](seed)


def make_runner(runner: str, gateway, scenario: Scenario, name: str | None = None):
    kwargs = dict(
        gateway=gateway,
        grid=scenario.world.grid,
        registry=scenario.world.registry,
        calendar=scenario.calendar,
        name=name or f"nabd-scene-{scenario.name}",
    )
    if runner == "loop":
        from nabd.loop import NabdLoop

        return NabdLoop(**kwargs)
    from nabd.graph import NabdGraph

    return NabdGraph(**kwargs)


def run(scenario: Scenario, runner: str = "graph", verbose: bool = False, out=None):
    """Run one scenario to the end. Returns (log, gateway)."""
    gateway = OfflineGateway(scenario.world)
    agent = make_runner(runner, gateway, scenario)
    pending = sorted(scenario.beats, key=lambda b: b.t)
    t = 0.0
    while t <= scenario.duration_s:
        while pending and pending[0].t <= t:
            beat = pending.pop(0)
            if out:
                print(f"\n  ▸ {beat.note}\n", file=out)
        record = agent.step(t)
        if out:
            line = agent.log.render(record, verbose=verbose)
            if line:
                print(line, file=out)
        t += STEP_S
    return agent.log, gateway


def run_live(passes: int = 3, out=None):
    """The contract run: the same code path against Nokia Network-as-Code.

    The sandbox cannot stage a disaster, so this proves the calls — request
    shapes, response vocabulary, error behaviour — on the handful of devices the
    account allocates, and writes the raw exchanges next to the offline ones.
    """
    from nabd.gateway import LiveGateway
    from nabd.model import Grid
    from nac import client as nac_client

    numbers = nac_client.msisdns()
    if not numbers:
        raise SystemExit("NAC_MSISDNS is empty — nothing to monitor. See nac/.env.example.")
    grid = assign_sentinels(make_grid(), numbers)
    gateway = LiveGateway()
    from nabd.loop import NabdLoop

    agent = NabdLoop(gateway, grid, registry=(), calendar=(), name="nabd-live-log")
    if out:
        print(f"\n  live contract run: {len(numbers)} sentinel(s) on {gateway.backend}, {passes} passes\n", file=out)
    for i in range(passes):
        record = agent.step(i * STEP_S)
        if out:
            print(agent.log.render(record, verbose=True), file=out)
    log_path = agent.log.write()
    calls_path = write_calls(gateway.calls, "nabd-live-contract")
    ok = sum(1 for c in gateway.calls if c.ok)
    if out:
        print(f"\n  {ok}/{len(gateway.calls)} calls answered → {calls_path.name}, decisions → {log_path.name}\n", file=out)
    return agent.log, gateway


def _print_summary(log, gateway, scenario: Scenario, out) -> None:
    s = log.summary()
    print("\n  " + "─" * 62, file=out)
    if s["declared_at"] is not None:
        lag = "" if scenario.onset_t is None else f" — {s['declared_at'] - scenario.onset_t:.0f}s after onset"
        print(f"  declared      {clock(s['declared_at'])}{lag}, {s['footprint_cells']} cells, confidence {s['confidence']}", file=out)
        print(f"  unreachable   peak {s['unreachable_peak']} registered people inside the footprint", file=out)
    else:
        print("  declared      nothing", file=out)
    print(f"  abstentions   {len(s['abstains'])}", file=out)
    for reason in s["abstains"]:
        print(f"                — {reason}", file=out)
    print(f"  CAMARA calls  {s['api_calls']} over {s['passes']} passes ({gateway.backend})", file=out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", choices=[*BUILDERS, "all"], default="all")
    parser.add_argument("--runner", choices=["graph", "loop"], default="graph")
    parser.add_argument("--backend", choices=["offline", "live"], default="offline")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--calls", action="store_true", help="also write every raw CAMARA call to nac/evidence/")
    parser.add_argument("--console", action="store_true", help="rebuild nabd/replay.html from the evidence afterwards")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.backend == "live":
        run_live(out=sys.stdout)
        return 0

    names = list(BUILDERS) if args.scene == "all" else [args.scene]
    for name in names:
        scenario = build(name, seed=args.seed)
        print("\n" + "═" * 66)
        print(f"  NABD · scene: {name}  ·  runner: {args.runner}  ·  {clock(0)} at {KAHRAMANMARAS[0]:.3f}N {KAHRAMANMARAS[1]:.3f}E")
        print("═" * 66)
        log, gateway = run(scenario, runner=args.runner, verbose=args.verbose, out=sys.stdout)
        _print_summary(log, gateway, scenario, sys.stdout)
        path = log.write()
        print(f"  evidence      {path.name}", end="")
        if args.calls:
            calls = write_calls(gateway.calls, f"nabd-calls-{name}")
            print(f", {calls.name} ({len(gateway.calls)} raw calls)", end="")
        print()
    if args.console:
        from nabd.console import build_console

        path = build_console()
        print(f"  console       {path.name} ({path.stat().st_size // 1024} KB) — open it in a browser")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
