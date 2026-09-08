"""The real event: what the agent does when the ground motion is measured, not drawn.

    python -m tests.test_nabd_real

Every other Nabd suite checks the agent against a world we authored. This one
checks it against the USGS ShakeMap for the M7.8 Pazarcık earthquake of
6 February 2023, and checks the data itself has not silently changed underneath
the claims made about it.

The claim worth testing is not "it declares something". It is that **every cell
Nabd names in the first minute is a cell the measured shaking says was above the
collapse threshold** — the map does not invent damage — and that what it misses
at that moment is small, known, and arrives as the footprint grows.
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


def test_the_intensity_window_is_sane_and_varied():
    sm = shakemap.load()
    assert len(sm.mmi) == sm.window["rows"] * sm.window["cols"] == 100
    values = list(sm.mmi.values())
    assert all(1.0 <= v <= 10.0 for v in values), (min(values), max(values))
    # A window where the shaking is uniform would prove nothing about a map.
    assert max(values) - min(values) >= 2.0, (min(values), max(values))
    grid = sm.grid()
    assert len(grid.monitored()) == 100
    assert grid.spacing_m == sm.window["spacing_km"] * 1000


def test_the_outage_model_is_calibrated_to_the_reported_figure():
    """Turkcell reported more than half of local base stations inoperative."""
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


def _real():
    scenario = build("maras")
    log, gateway = run(scenario, runner="loop")
    return scenario, log, gateway


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_real"]))
