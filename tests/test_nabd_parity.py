"""Backend parity: the checks behind "one agent, both networks", as tests.

    python -m tests.test_nabd_parity

`nabd/parity.py` produces the report a judge reads. This suite is the same
checks run as assertions, so a change that quietly reintroduces a second code
path — an SDK import in the detector, a scene constructing its own gateway —
fails the build rather than degrading a paragraph in a report.
"""

from __future__ import annotations

from nabd import parity
from nabd.gateway import build as build_gateway, parse_congestion, parse_location, parse_reachability
from nabd.model import Level, Reach
from nabd.scene import BUILDERS, build, make_runner, run


def test_agent_stack_is_backend_blind():
    check = parity.check_agent_is_backend_blind()
    assert check.status == "PASS", f"{check.detail}\n          " + "\n          ".join(check.lines)


def test_gateway_build_is_the_only_selection_point():
    check = parity.check_single_selection_point()
    assert check.status == "PASS", f"{check.detail}\n          " + "\n          ".join(check.lines)


def test_every_scene_replays_through_the_live_parsers():
    """Each scene, recorded and replayed, must produce identical evidence.

    The replay backend reads every recorded response with the same three
    functions the live gateway uses. If the simulator answered in a shape the
    live code could not read, the evidence would diverge here.
    """
    for name in BUILDERS:
        scenario = build(name)
        log_a, gateway_a = run(scenario, runner="loop")
        replay = build_gateway("replay", calls=list(gateway_a.calls))
        agent = make_runner("loop", replay, scenario, name=f"parity-{name}")
        t = 0.0
        while t <= scenario.duration_s:
            agent.step(t)
            t += 30.0
        assert replay.missing == 0, (name, replay.missing)
        a = [r.to_json() for r in log_a.records]
        b = [r.to_json() for r in agent.log.records]
        assert a == b, f"{name}: evidence diverged on replay"
    print(f"        {len(BUILDERS)} scenes recorded and replayed, evidence identical every time")


def test_the_live_parsers_read_the_simulators_responses():
    """The unit-level version: simulator bytes in, the live gateway's readings out."""
    _, gateway = run(build("quake"), runner="loop")
    checked = 0
    for call in gateway.calls:
        if not call.ok:
            continue
        if call.name == "congestion.query":
            level, _ = parse_congestion(call.response)
            assert isinstance(level, Level)
        elif call.name == "device_status.connectivity":
            assert parse_reachability(call.response) in (Reach.REACHABLE, Reach.UNREACHABLE)
        elif call.name == "location.retrieve":
            from datetime import timedelta

            from nabd.gateway import EPOCH

            loc = parse_location(call.response, EPOCH + timedelta(seconds=call.t))
            assert loc is not None and loc.radius_m > 0, call
        checked += 1
    print(f"        {checked:,} simulated responses parsed by the live code path")


def test_the_live_check_is_honest_about_a_missing_transcript():
    """It must say PENDING, never PASS, when there is no live run on file."""
    check = parity.check_live_transcript()
    assert check.status in ("PASS", "PENDING"), check
    if not parity.LIVE_TRANSCRIPT.exists():
        assert check.status == "PENDING", "a missing live transcript must not read as a pass"


def test_the_report_renders():
    checks = parity.run_checks()
    assert len(checks) == 4
    text = parity.render(checks)
    assert "backend parity" in text
    markdown = parity.markdown(checks)
    assert markdown.startswith("# Backend parity") and "| # | Check |" in markdown


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_parity"]))
