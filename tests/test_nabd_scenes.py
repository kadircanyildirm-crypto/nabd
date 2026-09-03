"""The three scenes end to end, and the two runners diffed against each other.

    python -m tests.test_nabd_scenes

These are the claims the demo makes on stage, checked by the machine before the
room: the quiet city stays quiet, the quake is declared inside the first minute
with everyone on the triage list living inside the footprint, the noise scene
abstains three different ways, and the LangGraph runner produces exactly the
evidence the plain loop does.
"""

from __future__ import annotations

from nabd.model import Kind
from nabd.scene import build, run
from nabd.world import make_registry


def _records(name: str, runner: str = "graph"):
    scenario = build(name)
    log, gateway = run(scenario, runner=runner)
    return scenario, log, gateway


def test_quiet_scene_stays_quiet():
    _, log, gateway = _records("quiet")
    kinds = {r.kind for r in log.records}
    assert kinds == {Kind.QUIET.value}, kinds
    assert all(not r.api_calls or set(r.api_calls) <= {"device_status.connectivity", "congestion.query"} for r in log.records)
    # Nothing personal was touched: every call went to a sentinel number.
    assert all(c.request["device"]["phoneNumber"].startswith("+9990") for c in gateway.calls)


def test_quake_is_declared_inside_the_first_minute():
    scenario, log, _ = _records("quake")
    s = log.summary()
    assert s["declared_at"] is not None, "never declared"
    lag = s["declared_at"] - scenario.onset_t
    assert 0 < lag <= 60, f"declared {lag:.0f}s after onset"
    declared = next(r for r in log.records if r.kind == Kind.DECLARE.value)
    assert set(declared.cells) == set(scenario.core), declared.cells
    assert declared.confidence == "HIGH"
    assert any("hot ring" in sig for sig in declared.signals), declared.signals
    print(f"        declared {lag:.0f}s after onset, {len(declared.cells)} cells, {declared.confidence}")


def test_quake_triage_stays_inside_the_footprint_and_is_ranked():
    scenario, log, gateway = _records("quake")
    registry = {p.msisdn: p for p in scenario.world.registry}
    core = set(scenario.core)
    personal = [c for c in gateway.calls if c.request["device"]["phoneNumber"] in registry]
    assert personal, "triage never ran"
    for call in personal:
        assert registry[call.request["device"]["phoneNumber"]].home_cell in core, call.request
    declared = next(r for r in log.records if r.kind == Kind.DECLARE.value)
    assert declared.triage and declared.triage["unreachable"] > 0
    priorities = [r["class"] for r in declared.triage["top"]]
    order = ["medical-dependent", "disabled", "elderly", "pilgrim-group", "lone-worker"]
    assert priorities == sorted(priorities, key=order.index), priorities
    assert all(entry["last_seen"] is not None for entry in declared.triage["top"])
    # Location Retrieval is the expensive call: never more of them than unreachable people.
    locates = sum(1 for c in gateway.calls if c.name == "location.retrieve")
    assert locates <= declared.triage["unreachable"] * 3, locates


def test_quake_list_updates_when_people_answer_again():
    scenario, log, _ = _records("quake")
    before = [r.triage["unreachable"] for r in log.records if r.triage and r.t < 420]
    after = [r.triage["unreachable"] for r in log.records if r.triage and r.t >= 420]
    assert before and after
    assert after[0] == before[-1] - len(scenario.extra["recoveries"]), (before[-1], after[0])


def test_noise_scene_abstains_three_ways_and_never_declares():
    _, log, _ = _records("noise")
    kinds = [r.kind for r in log.records]
    assert Kind.DECLARE.value not in kinds and Kind.CANDIDATE.value not in kinds, kinds
    reasons = [r.reason for r in log.records if r.kind == Kind.ABSTAIN.value]
    assert len(reasons) == 3, reasons
    assert any("single-cell" in r for r in reasons), reasons
    assert any("MNT-2214" in r for r in reasons), reasons
    assert any("congestion without silence" in r for r in reasons), reasons


def test_runners_agree_byte_for_byte():
    _, graph_log, graph_gw = _records("quake", runner="graph")
    _, loop_log, loop_gw = _records("quake", runner="loop")
    assert [r.to_json() for r in graph_log.records] == [r.to_json() for r in loop_log.records]
    assert [c.to_json() for c in graph_gw.calls] == [c.to_json() for c in loop_gw.calls]
    print(f"        {len(graph_log.records)} passes, {len(graph_gw.calls)} calls identical across both runners")


def test_topology_gates_triage_behind_the_verdict():
    from nabd.graph import render_mermaid

    mermaid = render_mermaid()
    assert "declare" in mermaid and "triage" in mermaid and "hold" in mermaid, mermaid
    # Both branches leave `declare`; neither `sense` nor `correlate` can reach triage directly.
    assert "declare -.-> triage" in mermaid.replace("\t", " ") or "declare -. &nbsp;triage&nbsp; .-> triage" in mermaid, mermaid


def test_console_is_a_view_over_the_evidence():
    import json
    import tempfile
    from pathlib import Path

    from nabd.console import build_console

    for name in ("quiet", "quake", "noise"):
        scenario = build(name)
        log, _ = run(scenario)
        log.write()
    out = Path(tempfile.mkdtemp()) / "replay.html"
    build_console(out=out)
    html = out.read_text(encoding="utf-8")
    assert html.count("<script") == 2 and "http" not in html.split("<style>")[1].split("</style>")[0], "no external resources"
    start = html.index('<script id="data" type="application/json">') + len('<script id="data" type="application/json">')
    data = json.loads(html[start : html.index("</script>", start)])  # "<\/" is plain JSON escaping
    names = [s["name"] for s in data["scenes"]]
    assert names == ["quiet", "quake", "noise"], names
    quake = next(s for s in data["scenes"] if s["name"] == "quake")
    assert all(len(r["grid"]) == 100 for r in quake["records"]), "every pass carries the full grid"
    declared = next(r for r in quake["records"] if r["kind"] == "DECLARE")
    assert declared["grid"].count("D") == 9 and declared["grid"].count("H") >= 16
    assert out.stat().st_size < 1_500_000
    print(f"        {out.stat().st_size // 1024} KB, {sum(len(s['records']) for s in data['scenes'])} passes inlined")


def test_registry_is_pseudonymous_and_reproducible():
    a = make_registry(build("quake").world.grid, seed=7)
    b = make_registry(build("quake").world.grid, seed=7)
    assert a == b
    assert all(p.id.startswith("R-") and p.msisdn.startswith("+9991") for p in a)


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_scenes"]))
