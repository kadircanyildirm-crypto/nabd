"""The false-alarm rate, as a number: ordinary mornings with sentinels that fail on their own.

    python -m tests.test_nabd_false_alarm

Real fixed devices drop out. A SIM loses registration for a pass, a modem
reboots, a meter's battery dips — and none of it is an impact. The look-alike
scenes show the detector refusing four *shaped* non-events; this suite asks the
plainer question a jury asks first: with nothing happening at all, and each
sentinel failing at random on each pass, how often does the agent declare?

The answer is measured rather than asserted, and it has an edge. Up to a three
percent per-pass dropout the floor holds — no morning is declared. Around five
percent it becomes marginal: random three-cell blocks that persist through the
confirmation pass start to appear on a hundred-cell grid, candidates are held
on most mornings, and in a wider sample some are declared (6 of 60 in one run,
0 of 20 in another). That edge is an operating requirement for a deployment,
written down: keep sentinel dropout under three percent per pass, or raise the
size floor.
"""

from __future__ import annotations

from nabd.model import Kind
from nabd.scene import Scenario, build, run
from nabd.world import Dropout, World

MORNINGS = 30  # per rate; each is 31 passes over 100 cells


def _mornings(rate: float, n: int = MORNINGS) -> tuple[int, int, int]:
    """(mornings declared, candidate passes, abstentions) at one dropout rate."""
    base = build("quiet")
    grid, registry = base.world.grid, base.world.registry
    declared = candidates = abstentions = 0
    for seed in range(n):
        world = World(grid, registry, events=(Dropout(rate),), seed=1000 + seed)
        log, _ = run(Scenario("false-alarm", world, (), [], duration_s=900), runner="loop")
        kinds = [r.kind for r in log.records]
        declared += any(k in (Kind.DECLARE.value, Kind.UPDATE.value) for k in kinds)
        candidates += sum(k == Kind.CANDIDATE.value for k in kinds)
        abstentions += sum(k == Kind.ABSTAIN.value for k in kinds)
    return declared, candidates, abstentions


def test_random_dropout_up_to_three_percent_never_declares():
    """Zero declared mornings at 1%, 2% and 3% per-pass sentinel dropout."""
    for rate in (0.01, 0.02, 0.03):
        declared, candidates, abstentions = _mornings(rate)
        assert declared == 0, f"{declared} of {MORNINGS} ordinary mornings declared at {rate:.0%} dropout"
        print(f"        {rate:.0%} dropout: 0 / {MORNINGS} mornings declared — "
              f"{candidates} candidates held and dropped, {abstentions} single-cell abstentions")


def test_the_floor_has_an_edge_and_it_is_written_down():
    """Around 5% the floor is marginal. That is the requirement, not a surprise."""
    declared, candidates, _ = _mornings(0.05, n=20)
    # Random three-cell blocks now reach the confirmation pass often enough to
    # be held as candidates most mornings; the test records the envelope rather
    # than hiding it, and the requirement it implies is in the docstring.
    print(f"        5% dropout: {declared} / 20 mornings declared, {candidates} candidates held — "
          f"the deployment requirement is under 3% per pass, or a higher size floor")
    assert candidates > 0, "at 5% the detector should at least be seeing candidates"


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_false_alarm"]))
