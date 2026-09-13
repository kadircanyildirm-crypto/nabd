"""The real event: what the agent does when the ground motion is measured, not drawn.

    python -m tests.test_nabd_real

Every other Nabd suite checks the agent against a world we authored. These
check it against two earthquakes that happened — the M7.8 Pazarcık earthquake
of 6 February 2023 and the M6.8 Al Haouz earthquake of 8 September 2023 — and
check the data itself has not silently changed underneath the claims made
about it.

The claim worth testing is not "it declares something". It is that **every cell
Nabd names is one the measured shaking condemns** — the map does not invent
damage — and that what it misses is small, known, and arrives as the footprint
grows.

The second event is here for one reason: the rule that turns shaking into
silence was calibrated against what was reported from Türkiye, and it is
carried to Morocco untouched. `test_nothing_was_retuned_for_the_second_event`
is the assertion that keeps that honest, and the rest of the Al Haouz tests
describe what falls out of it — a later declaration, at lower confidence, for
reasons that are in the evidence.
"""

from __future__ import annotations

from nabd import shakemap
from nabd.detector import clusters
from nabd.model import Kind
from nabd.scene import build, run
from nabd.world import Rupture


def test_the_extract_is_the_event_it_claims_to_be():
    """Provenance, asserted — so the numbers cannot drift from their source."""
    sm = shakemap.load()
    assert sm.event["id"] == "us6000jllz", sm.event
    assert sm.event["magnitude"] == 7.8
    assert sm.event["origin_utc"].startswith("2023-02-06T01:17:34")
    assert sm.event["epicentre"] == [37.2256, 37.0143]
    assert sm.event["seismic_stations"] >= 200 and sm.event["intensity_observations"] >= 1000
    assert "earthquake.usgs.gov" in sm.source["product"]
    assert sm.source["shakemap_version"] >= 1
    # It is an estimated field, and the file has to keep saying so.
    assert "model" in sm.source["note"].lower()


def test_the_second_extract_is_the_event_it_claims_to_be():
    """Al Haouz, from the same USGS pipeline and asserted the same way."""
    sm = shakemap.load(shakemap.AL_HAOUZ)
    assert sm.event["id"] == "us7000kufc", sm.event
    assert sm.event["magnitude"] == 6.8
    assert sm.event["origin_utc"].startswith("2023-09-08T22:11:01")
    assert sm.event["epicentre"] == [31.058, -8.3847]
    # Three seismic stations, against 262 for Kahramanmaraş. That gap is the
    # argument for reading the network instead of waiting for the ground.
    assert sm.event["seismic_stations"] <= 10
    assert sm.event["intensity_observations"] >= 500
    assert "earthquake.usgs.gov" in sm.source["product"]
    assert "us7000kufc" in sm.source["product"]
    assert sm.source["shakemap_version"] >= 1
    assert "model" in sm.source["note"].lower()


def test_nothing_was_retuned_for_the_second_event():
    """The whole point of Al Haouz: it is a held-out test, not a calibration.

    The two scenes must be driven by the same rule with the same numbers, and
    those numbers must be the ones the class ships with — so nobody can quietly
    tune the second event into agreement and call it a validation.
    """
    import dataclasses

    a = next(e for e in build("maras").world.events if isinstance(e, Rupture))
    b = next(e for e in build("atlas").world.events if isinstance(e, Rupture))
    tuned = ("collapse_mmi", "power_mmi", "battery_s", "surge_s", "covered_rate")
    defaults = {f.name: f.default for f in dataclasses.fields(Rupture) if f.name in tuned}
    for field in tuned:
        assert getattr(a, field) == getattr(b, field) == defaults[field], field
    # And the windows really are different places, not the same one relabelled.
    assert build("maras").world.grid.cells[0].lon > 0 > build("atlas").world.grid.cells[0].lon


def test_the_intensity_window_is_sane_and_varied():
    for event in (shakemap.KAHRAMANMARAS, shakemap.AL_HAOUZ):
        sm = shakemap.load(event)
        assert len(sm.mmi) == sm.window["rows"] * sm.window["cols"] == 100, event
        values = list(sm.mmi.values())
        assert all(1.0 <= v <= 10.0 for v in values), (event, min(values), max(values))
        # A window where the shaking is uniform would prove nothing about a map.
        assert max(values) - min(values) >= 2.0, (event, min(values), max(values))
        grid = sm.grid()
        assert len(grid.monitored()) == 100
        assert grid.spacing_m == sm.window["spacing_km"] * 1000


def test_the_outage_model_is_calibrated_to_the_reported_figure():
    """Turkcell reported half of its 3,300 base stations in the region out of service."""
    sm = shakemap.load()
    r = Rupture(0.0, sm.mmi)
    eventually_dark = [c for c in sm.mmi if r.dark_from(c) is not None]
    fraction = len(eventually_dark) / len(sm.mmi)
    assert 0.5 < fraction < 0.8, f"{fraction:.0%} of the window goes dark — off the reported figure"
    # And the two mechanisms have to stay distinguishable in time.
    instant = [c for c in eventually_dark if r.dark_from(c) == r.t0]
    later = [c for c in eventually_dark if r.dark_from(c) > r.t0]
    assert instant and later, (len(instant), len(later))
    assert max(r.dark_from(c) for c in later) > r.t0 + 300
    print(f"        {fraction:.0%} of the window eventually dark: {len(instant)} on impact, {len(later)} as batteries fail")


def test_the_first_map_names_only_cells_the_shaking_condemns():
    """No invented damage: the declared footprint is inside the collapse band."""
    scenario, log, _ = _real()
    sm = shakemap.load()
    r = Rupture(scenario.onset_t, sm.mmi)
    collapse = set(sm.band(r.collapse_mmi))

    declared = next(r_ for r_ in log.records if r_.kind == Kind.DECLARE.value)
    named = set(declared.cells)
    assert named <= collapse, f"declared cells outside the collapse band: {sorted(named - collapse)}"
    assert len(clusters(tuple(named), scenario.world.grid)) == 1, "the footprint must be one block"

    lag = declared.t - scenario.onset_t
    assert 0 < lag <= 60, f"declared {lag:.0f}s after onset"
    missed = collapse - named
    assert len(missed) <= 4, f"too much of the collapse band missed at declaration: {sorted(missed)}"
    print(
        f"        declared {lag:.0f}s after onset: {len(named)} of {len(collapse)} collapse-band cells, "
        f"{len(missed)} held back as a separate pocket below the size floor"
    )


def test_the_footprint_grows_as_the_network_dies_without_losing_confidence():
    """A real event spreads for hours; a published map must follow it, not degrade."""
    scenario, log, _ = _real()
    declared = next(r for r in log.records if r.kind == Kind.DECLARE.value)
    updates = [r for r in log.records if r.kind == Kind.UPDATE.value]
    assert len(updates) >= 3, f"only {len(updates)} updates"
    sizes = [len(declared.cells)] + [len(u.cells) for u in updates]
    assert sizes == sorted(sizes), sizes
    assert sizes[-1] > sizes[0] * 2, sizes
    # A staggered onset is what a spreading outage looks like; it must not be
    # read as the disaster becoming less real.
    assert all(u.confidence == declared.confidence for u in updates), [u.confidence for u in updates]
    assert declared.confidence == "HIGH"
    print(f"        footprint {sizes[0]} → {sizes[-1]} cells over {len(updates)} updates, confidence held at HIGH")


def test_the_second_event_declares_later_and_says_why():
    """An M6.8 at 19 km does not flatten a block, so the agent waits for one.

    Almost nothing in this window is above the collapse threshold — a pocket at
    the epicentre, below the size floor — and the footprint arrives instead as
    the surviving sites drain their batteries. So the declaration is minutes
    late rather than seconds, and it is MEDIUM rather than HIGH because the
    onset genuinely was not synchronised. Both of those are in the evidence,
    which is the difference between a weaker answer and a dishonest one.
    """
    scenario, log, _ = _real("atlas")
    first = next(r for r in log.records if r.kind == Kind.ABSTAIN.value)
    assert "below the" in first.reason and "floor" in first.reason, first.reason

    declared = next(r for r in log.records if r.kind == Kind.DECLARE.value)
    lag = declared.t - scenario.onset_t
    assert 120 <= lag <= 400, f"declared {lag:.0f}s after onset"
    assert declared.confidence == "MEDIUM", declared.confidence
    assert any("staggered" in s for s in declared.signals), declared.signals
    assert any(s.startswith("hot ring") for s in declared.signals), declared.signals
    print(f"        Al Haouz declared {lag:.0f}s after onset at MEDIUM — the onset really was staggered")


def test_neither_map_names_a_cell_the_shaking_leaves_standing():
    """Across both events: nothing is ever declared outside the condemned band.

    For Kahramanmaraş the first map sits inside the collapse band; for Al Haouz
    it sits inside the band that loses power. The common claim, and the one that
    matters, is that no cell is ever named that the measured field says was fine.
    """
    for name in ("maras", "atlas"):
        scenario, log, _ = _real(name)
        sm = shakemap.load(shakemap.EVENT_OF[name])
        r = Rupture(scenario.onset_t, sm.mmi)
        condemned = {c for c, v in sm.mmi.items() if v >= r.power_mmi}
        claimed: set[str] = set()
        for record in log.records:
            if record.kind in (Kind.DECLARE.value, Kind.UPDATE.value, Kind.SUSTAIN.value):
                claimed |= set(record.cells)
        assert claimed <= condemned, f"{name}: named cells the shaking spared: {sorted(claimed - condemned)}"
        print(f"        {name}: {len(claimed)} cells ever named, all inside the {len(condemned)} the field condemns")


def test_marrakesh_is_shaken_and_is_not_cut_off():
    """The distinction the whole product exists to make.

    Marrakesh sits in the north of the Al Haouz window at about intensity 6. It
    was on every television in the world, and its cells answered the whole time.
    A map of what was shaken would have named it; a map of what went silent does
    not, and that is the difference between a seismograph and this.
    """
    sm = shakemap.load(shakemap.AL_HAOUZ)
    cell, centre = min(sm.centres.items(), key=lambda kv: (kv[1][0] - 31.63) ** 2 + (kv[1][1] + 8.008) ** 2)
    assert abs(centre[0] - 31.63) < 0.1 and abs(centre[1] + 8.008) < 0.1, (cell, centre)
    assert 5.5 <= sm.mmi[cell] <= 7.0, sm.mmi[cell]   # shaken, and well short of collapse

    _, log, _ = _real("atlas")
    for record in log.records:
        assert cell not in set(record.cells), f"Marrakesh ({cell}) was named at t={record.t}"
    print(f"        Marrakesh ({cell}) shaken at MMI {sm.mmi[cell]} and never named")


def test_triage_reaches_the_people_inside_the_real_footprint():
    scenario, log, gateway = _real()
    registry = {p.msisdn: p for p in scenario.world.registry}
    peak = max(r.triage["unreachable"] for r in log.records if r.triage)
    assert peak > 0, "nobody was ever unreachable"
    for call in gateway.calls:
        device = call.request["device"]["phoneNumber"]
        if device in registry:
            record = next(r for r in reversed(log.records) if r.t <= call.t and r.triage)
            assert registry[device].home_cell in set(record.cells), (device, record.t)
    # Ranked by need, not by discovery order.
    last = [r for r in log.records if r.triage and r.triage["top"]][-1]
    order = ["medical-dependent", "disabled", "elderly", "pilgrim-group", "lone-worker"]
    ranks = [order.index(e["class"]) for e in last.triage["top"]]
    assert ranks == sorted(ranks), ranks
    print(f"        {peak} registered people unreachable at peak, every query inside the footprint")


def _real(name: str = "maras"):
    scenario = build(name)
    log, gateway = run(scenario, runner="loop")
    return scenario, log, gateway


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_real"]))
