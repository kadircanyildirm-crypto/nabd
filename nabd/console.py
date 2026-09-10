"""Build the command-centre console: one self-contained HTML file, no server, no network.

    python -m nabd.console            # reads nac/evidence/nabd-scene-*.jsonl, writes nabd/replay.html

The console is what the room watches, so its failure modes matter more than its
features. It is generated as a single file with the evidence inlined, because
every alternative can fail in a room you do not control: `fetch()` on a `file://`
page is blocked, a local server is one more process, a CDN is a network you will
not have. Open the file. That is the whole runbook.

It is a view over the records `nabd/log.py` writes — the map is redrawn from the
per-pass grid string, the lists from the triage summary, the log from the
verdicts. Nothing on screen exists that the evidence file does not contain,
which is what makes it defensible when a judge asks whether the screen is theatre.
"""

from __future__ import annotations

import json
from pathlib import Path

from nabd.log import EVIDENCE_DIR
from nabd.scene import BUILDERS, build, run

OUT = Path(__file__).resolve().parent / "replay.html"
# The same file is published as the live demo (GitHub Pages serves docs/), so it is
# written twice; nothing else differs between the two copies.
PAGES = Path(__file__).resolve().parent.parent / "docs" / "index.html"

TITLES = {
    "quiet": ("Quiet morning", "the baseline — a monitored city on an ordinary day"),
    "quake": ("Earthquake", "the reference case — nine cells fall silent at once, the ring goes hot"),
    "noise": ("Look-alikes", "the false-alarm defence — a cell fault, a maintenance window, a stadium crowd"),
    "degraded": ("Chronic degradation", "the hardest look-alike — a block where silence is normal, and a real impact in the same run"),
    "maras": ("Kahramanmaraş", "6 February 2023 — the real event, where measured ground motion decides which cells go silent"),
    "atlas": ("Al Haouz", "8 September 2023 — a second real event on the same thresholds; nothing was retuned for it"),
}

#: Which set of base maps a scene is drawn on. Four scenes and the first real
#: one watch Türkiye; the second real one watches Morocco.
REGION_OF = {"quiet": "tr", "quake": "tr", "noise": "tr", "degraded": "tr", "maras": "tr", "atlas": "ma"}

#: The measured event behind a scene, for the ones that have one.
EVENT_OF = {"maras": "us6000jllz", "atlas": "us7000kufc"}


def load(name: str) -> list[dict]:
    path = EVIDENCE_DIR / f"nabd-scene-{name}.jsonl"
    if not path.exists():
        log, _ = run(build(name))
        path = log.write()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def basemap() -> dict | None:
    """Towns, water, roads and provincial lines for the monitored region.

    One extract serves every scene: the regional window contains the city one, so
    the console projects the same lines onto whichever grid it is drawing.
    """
    path = Path(__file__).resolve().parent / "data" / "basemap.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Roads, water and places come from OpenStreetMap at both scales now; the one
    # thing Natural Earth still supplies is the provincial boundary.
    return {"borders": raw["borders"], "source": raw["source"]}


def json_data(filename: str) -> dict | None:
    path = Path(__file__).resolve().parent / "data" / filename
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def region_basemap() -> dict | None:
    """The same street data as the city scenes, thinned for a 150 km view.

    Drawing the real-event scene from Natural Earth while the others came from
    OpenStreetMap made it the odd one out — a sparser map for the one scene that
    matters most. Both windows come from the same source now.
    """
    return json_data("basemap-region.json")


def mid_basemap() -> dict | None:
    """The road network between the towns, for when the region is zoomed in.

    At the full 150 km view only the trunk roads are worth drawing. Zooming in
    should reveal something, not just magnify what was already there, so this is
    the tier underneath: the tertiary and unclassified network across the
    monitored window.
    """
    return json_data("basemap-mid.json")


def city_basemap() -> dict | None:
    """The street network, for the scenes that watch a single city.

    The regional extract carries two roads and one dot across a 6.7 km square,
    which is not a map. This is OpenStreetMap, delta-encoded, and it is what makes
    the four city-scale scenes legible as a place.
    """
    return json_data("basemap-city.json")


def geometry_for(name: str) -> dict | None:
    """The measured event's own geometry, for the scenes that have one.

    Four scenes are worlds we drew, and there is nothing real to lay under them.
    Two are earthquakes that happened, and for those the published isoseismals
    and the finite-fault rupture go on the map — so the footprint Nabd declares
    can be checked against the shaking that caused it, by eye, in a second.
    """
    event = EVENT_OF.get(name)
    raw = json_data(f"shakemap-{event}-geo.json") if event else None
    if not raw:
        return None
    return {"contours": raw["contours"], "rupture": raw["rupture"], "source": raw["source"]}


def counted_calls(records: list[dict]) -> list[dict]:
    """Replace each pass's list of CAMARA calls with a tally of it.

    A 10x10 grid makes two hundred calls a pass, and the console shows one
    number: how many. Carrying the two hundred names into the page cost more
    than every base map in it put together. The ordered list stays where it
    belongs — in `nac/evidence/nabd-scene-*.jsonl`, which is the audit trail;
    this is the same information at the resolution the screen uses.
    """
    out = []
    for record in records:
        tally: dict[str, int] = {}
        for call in record.get("api_calls", ()):
            tally[call] = tally.get(call, 0) + 1
        out.append({**record, "api_calls": tally})
    return out


def scene_payload(name: str) -> dict:
    scenario = build(name)
    grid = scenario.world.grid
    title, subtitle = TITLES[name]
    return {
        "geo": geometry_for(name),
        "city": grid.spacing_m <= 2000,
        "maps": REGION_OF.get(name, "tr"),
        "name": name,
        "title": title,
        "subtitle": subtitle,
        "grid": {
            "rows": grid.rows,
            "cols": grid.cols,
            "spacing_m": grid.spacing_m,
            "cells": [{"id": c.id, "row": c.row, "col": c.col, "lat": c.lat, "lon": c.lon} for c in grid.cells],
        },
        "beats": [{"t": b.t, "note": b.note} for b in scenario.beats],
        "onset": scenario.onset_t,
        "core": list(scenario.core),
        "registry": len(scenario.world.registry),
        "maintenance": [{"ticket": m.ticket, "cells": list(m.cells), "start": m.start, "end": m.end} for m in scenario.calendar],
        "records": counted_calls(load(name)),
        # For the cell inspector: how many registered people live in each cell
        # (an aggregate, never a name), and the measured shaking per cell for
        # the real events.
        "registry_by_cell": registry_by_cell(scenario),
        "mmi": cell_intensity(name),
    }


def registry_by_cell(scenario) -> dict[str, int]:
    counts: dict[str, int] = {}
    for person in scenario.world.registry:
        counts[person.home_cell] = counts.get(person.home_cell, 0) + 1
    return counts


def cell_intensity(name: str) -> dict[str, float] | None:
    event = EVENT_OF.get(name)
    if not event:
        return None
    from nabd import shakemap

    return dict(shakemap.load(event).mmi)


def build_console(names: tuple[str, ...] = tuple(BUILDERS), out: Path = OUT) -> Path:
    # The base maps are the same for every scene, and the city one is the largest
    # thing in the file. Inlining it per scene made the console five times heavier
    # than it needed to be, so it is carried once and referenced by a flag.
    payload = {
        "scenes": [scene_payload(n) for n in names],
        # One set of base maps per region watched, carried once at the top and
        # named by each scene. Morocco has no city-scale scene and no Natural
        # Earth extract, and the map layer simply skips what is not there.
        "maps": {
            "tr": {"base": basemap(), "city": city_basemap(),
                   "mid": mid_basemap(), "region": region_basemap()},
            "ma": {"region": json_data("basemap-region-ma.json"),
                   "mid": json_data("basemap-mid-ma.json")},
        },
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    out.write_text(html, encoding="utf-8")
    if out == OUT and PAGES.parent.is_dir():
        PAGES.write_text(html, encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nabd · command centre</title>
<style>
  :root {
    --bg: #0b1017; --panel: #111a24; --panel-2: #0e151d; --line: #1e2a37;
    --text: #d7e1ea; --muted: #7f8f9f; --dim: #55667a;
    --low: #16324b; --medium: #5b4a1a; --high: #d9822b; --dark: #07090c; --unmon: #161c24;
    --alert: #ff5a4e; --cand: #ffd166; --held: #8a9bab; --ok: #4cc38a;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  header { display: grid; grid-template-columns: auto 1fr auto auto; gap: 18px; align-items: center; padding: 12px 20px; border-bottom: 1px solid var(--line); background: var(--panel); }
  .brand { font-weight: 700; letter-spacing: .02em; font-size: 16px; white-space: nowrap; }
  .brand span { color: var(--muted); font-weight: 400; margin-left: 8px; }
  nav { display: flex; gap: 5px; min-width: 0; overflow-x: auto; scrollbar-width: none; }
  nav::-webkit-scrollbar { display: none; }
  nav button { background: transparent; color: var(--muted); border: 1px solid var(--line); border-radius: 6px;
               padding: 6px 10px; cursor: pointer; font: inherit; font-size: 13px; white-space: nowrap; }
  nav button.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  .clock { font-family: var(--mono); font-size: 22px; font-variant-numeric: tabular-nums; text-align: right; line-height: 1.1; }
  .clock small { display: block; font-size: 11px; color: var(--muted); font-family: inherit; }
  .controls { display: flex; align-items: center; gap: 8px; }
  .controls button { background: #1a2330; color: var(--text); border: 1px solid var(--line); border-radius: 6px; width: 34px; height: 32px; cursor: pointer; font-size: 14px; }
  .controls input[type=range] { width: 220px; accent-color: var(--high); }
  /* Run the six scenes as one, at a pace the room has time for. */
  .controls #all { width: auto; padding: 0 11px; font-size: 12px; }
  .controls #all.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  .speeds { display: flex; margin-left: 2px; }
  .speeds button { width: auto; padding: 0 9px; font-size: 12px; font-family: var(--mono); border-radius: 0; }
  .speeds button:first-child { border-radius: 6px 0 0 6px; }
  .speeds button:last-child { border-radius: 0 6px 6px 0; border-left: 0; }
  .speeds button + button { border-left: 0; }
  .speeds button.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  /* The whole console is one screen. Nothing that matters may sit below a fold
     nobody knows is there, so main fills the viewport and the only thing that
     ever scrolls is a panel that visibly can. */
  html, body { height: 100%; }
  body { overflow: hidden; display: flex; flex-direction: column; }
  header, footer { flex: 0 0 auto; }
  main { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 440px;
         grid-template-rows: minmax(0, 1fr); gap: 14px; padding: 14px 18px; overflow: hidden; }
  @media (max-width: 1100px) { main { grid-template-columns: minmax(0, 1fr) 380px; } }
  .map { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px;
         display: grid; grid-template-rows: auto minmax(0, 1fr) auto; gap: 10px; min-height: 0; overflow: hidden; }
  .mapview { position: relative; min-height: 0; display: grid; }
  .map svg { width: 100%; height: 100%; min-height: 0; }
  .beat { min-height: 40px; padding: 8px 12px; border-left: 3px solid var(--high); background: var(--panel-2); border-radius: 6px;
          color: #c9d6e2; font-size: 13px; line-height: 1.4; }
  .beat.empty { border-left-color: var(--line); color: var(--dim); }
  svg { width: 100%; height: auto; display: block; }
  /* --- the base map ------------------------------------------------------ */
  .ground { fill: url(#sky); }
  .border { fill: none; stroke: #2b3d4e; stroke-width: 1.1; stroke-dasharray: 7 5; }
  .river  { fill: none; stroke: #1d4a63; stroke-width: 1.4; stroke-linecap: round; }
  .lake   { fill: #14384b; stroke: #1d4a63; stroke-width: 1; }
  .road   { fill: none; stroke: #2f3b48; stroke-width: 1.2; stroke-linecap: round; }
  /* A city reads by its street hierarchy: the trunk roads first, then the grid
     of everything else underneath them. */
  .rd-local { fill: none; stroke: #3b5065; stroke-width: .8; stroke-linecap: round; }
  .rd-minor { fill: none; stroke: #55697e; stroke-width: 1.1; stroke-linecap: round; }
  .rd-major { fill: none; stroke: #7f96ac; stroke-width: 1.9; stroke-linecap: round; }
  .rail     { fill: none; stroke: #3a4452; stroke-width: 1.1; stroke-dasharray: 5 4; }
  .water    { fill: #14384b; stroke: #1d4a63; stroke-width: .8; }
  .placelbl { font-family: var(--mono); font-size: 9px; fill: #7f93a6; paint-order: stroke;
              stroke: #0a1119; stroke-width: 2.5px; stroke-linejoin: round; }
  .placelbl.big { font-size: 12.5px; fill: #eaf2f9; font-weight: 600; }
  .town   { fill: #cfe0ee; }
  .town.major { fill: #ffffff; }
  .townlbl { font-family: var(--mono); font-size: 10px; fill: #9fb3c6; paint-order: stroke;
             stroke: #0a1119; stroke-width: 3px; stroke-linejoin: round; }
  .townlbl.major { font-size: 12px; fill: #eaf2f9; font-weight: 600; }
  .hair { stroke: #223141; stroke-width: .6; opacity: .55; }
  /* Cells are a wash over the map, not tiles on top of it: the ground, the roads
     and the town names stay legible through them, which is the difference between
     a data overlay and a chessboard. */
  .iso { fill: none; stroke-width: 1.1; opacity: .5; stroke-linejoin: round; stroke-linecap: round; }
  .iso.major { stroke-width: 1.9; opacity: .72; }
  .rupture { fill: none; stroke: #eaf2f9; stroke-width: 2.2; stroke-dasharray: 7 5; opacity: .75; }
  .isokey { font-family: var(--mono); font-size: 9.5px; fill: #0b1017; font-weight: 700; }
  /* Every state is drawn so that it cannot blend with another: load is a hatch
     (it never occludes the map and never turns brown over it), dark is solid,
     and normal is nothing at all — the map itself is the sign that all is well. */
  .cell { stroke: none; }
  /* The scene is scaled as a group; its strokes are not. */
  #scene path, #scene rect, #scene circle, #scene line { vector-effect: non-scaling-stroke; }
  .c-low { fill: none; }
  .c-medium { fill: url(#hatch-medium); }
  .c-high { fill: url(#hatch-high); }
  .c-unmon { fill: #141a2226; }
  .c-dark { fill: #04070de6; }
  .c-clear { fill: none; }
  /* With the measured event on, the shaking is the subject and the load steps back. */
  #grid.detail #cells { opacity: .3; }
  .fpfill { fill: var(--alert); fill-opacity: 0; transition: fill-opacity .55s cubic-bezier(.4,0,.2,1); }
  .fpfill.on { fill-opacity: .10; }
  .fpfill.cand { fill: var(--cand); fill-opacity: .12; }
  .fpfill.held { fill: var(--held); fill-opacity: .03; }
  .dot, .halo { transition: opacity .45s ease; }
  .scale { stroke: #7f8f9f; stroke-width: 1.4; fill: none; }
  .scaletxt, .compass { font-family: var(--mono); font-size: 10px; fill: #9fb3c6; }
  .compass { font-size: 13px; font-weight: 700; }
  #edge .fp { fill: none; stroke: var(--alert); stroke-width: 3; pointer-events: none; }
  #edge .cand { fill: none; stroke: var(--cand); stroke-width: 2.5; stroke-dasharray: 6 4; stroke-linecap: round; pointer-events: none; }
  #edge .held { fill: none; stroke: var(--held); stroke-width: 2; stroke-dasharray: 4 4; stroke-linecap: round; pointer-events: none; }
  .mnt { fill: none; stroke: var(--held); stroke-width: 1; stroke-dasharray: 2 3; pointer-events: none; }
  /* The grid reference lives in a ruled margin, the way a map sheet's does. */
  .ruler { fill: #0b1017; fill-opacity: .86; }
  .ruler-edge { stroke: #3a4d61; stroke-width: 1; }
  .tick { stroke: #6b8299; stroke-width: 1; }
  .lbl { fill: #a9bccd; font-family: var(--mono); font-size: 10px; font-weight: 600; letter-spacing: .04em; }
  .win { fill: none; stroke: #6b8299; stroke-width: 1; opacity: .9; }
  .pick { fill: #7dd3fc1a; stroke: #7dd3fc; stroke-width: 2; }
  /* The cell inspector: one card, bottom left of the map, following the playback. */
  #inspect { position: absolute; left: 26px; top: 26px; z-index: 3; width: 330px; background: #0b1017f2;
             border: 1px solid #2b3c4e; border-left: 3px solid #7dd3fc; border-radius: 8px; padding: 10px 12px 9px;
             font-size: 12px; line-height: 1.4; box-shadow: 0 10px 30px #00000088; }
  #inspect.hidden { display: none; }
  #inspect h5 { margin: 0 0 6px; font-size: 13px; font-weight: 600; display: flex; align-items: baseline; gap: 8px; }
  #inspect h5 .id { font-family: var(--mono); color: #7dd3fc; font-size: 15px; }
  #inspect h5 .ll { font-family: var(--mono); color: var(--muted); font-size: 10.5px; font-weight: 400; margin-left: auto; }
  #inspect .r { display: grid; grid-template-columns: 74px 1fr; gap: 8px; padding: 3px 0; border-top: 1px solid #1a2430; }
  #inspect .r:first-of-type { border-top: 0; }
  #inspect .k { color: var(--muted); font-size: 11px; padding-top: 1px; }
  #inspect .v { color: var(--text); }
  #inspect .v.muted { color: var(--muted); }
  #inspect .v b { font-weight: 600; }
  #inspect .v .mono { font-family: var(--mono); font-size: 11px; }
  #inspect .close { position: absolute; top: 4px; right: 8px; background: none; border: 0; color: var(--muted); font-size: 15px; cursor: pointer; }
  #inspect .close:hover { color: var(--text); }
  #inspect .hint { color: var(--dim); font-size: 10.5px; margin-top: 6px; }
  .focus { fill: #05080d; opacity: .3; }
  .fplabel { fill: var(--alert); font-family: var(--mono); font-size: 11px; font-weight: 700; }
  .dot { fill: #fff; stroke: var(--alert); stroke-width: 1.5; }
  .halo { fill: none; stroke: var(--alert); stroke-opacity: .28; stroke-width: .8; stroke-dasharray: 3 3; }
  .legend { display: flex; flex-wrap: wrap; align-items: center; gap: 13px; color: var(--muted); font-size: 11.5px; }
  /* The key: a panel over the map, every symbol drawn as the map draws it. */
  #keybtn { background: transparent; color: var(--muted); font: inherit; font-size: 11.5px;
            border: 1px solid var(--line); border-radius: 6px; padding: 4px 11px; cursor: pointer; white-space: nowrap; }
  #keybtn:hover, #keybtn.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  #mapkey { position: absolute; top: 58px; right: 8px; z-index: 3; width: min(1180px, calc(100% - 16px)); max-height: calc(100% - 66px);
            columns: 3; column-gap: 22px; column-fill: balance;
            overflow: auto; background: #0b1017f2; border: 1px solid var(--line); border-radius: 10px;
            padding: 14px 16px 10px; box-shadow: 0 12px 40px #00000088; font-size: 12.5px; line-height: 1.45; }
  #mapkey.hidden { display: none; }
  #mapkey h4 { margin: 10px 0 5px; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase;
               color: var(--high); font-weight: 600; break-after: avoid; }
  #mapkey .row, #mapkey .iso-scale, #mapkey .iso-lbls { break-inside: avoid; }
  #mapkey .close { column-span: all; }
  #mapkey h4:first-child { margin-top: 0; }
  #mapkey h4 small { color: var(--muted); letter-spacing: 0; text-transform: none; font-weight: 400; margin-left: 8px; }
  #mapkey .row { display: grid; grid-template-columns: 58px 1fr; gap: 10px; align-items: start; padding: 4px 0;
                 border-bottom: 1px solid #1a2430; font-size: 12px; line-height: 1.4; }
  #mapkey .row:last-child { border-bottom: 0; }
  #mapkey .sym { width: 58px; height: 34px; }
  #mapkey .sym svg { width: 58px; height: 34px; display: block; }
  #mapkey b { color: var(--text); font-weight: 600; }
  #mapkey .row span { color: var(--muted); display: block; }
  #mapkey .close { float: right; background: none; border: 0; color: var(--muted); font-size: 16px; cursor: pointer;
                   line-height: 1; padding: 0 2px; }
  #mapkey .close:hover { color: var(--text); }
  #mapkey .iso-scale { display: flex; gap: 0; margin: 6px 0 2px; border-radius: 4px; overflow: hidden; }
  #mapkey .iso-scale i { flex: 1; height: 10px; display: block; }
  #mapkey .iso-lbls { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10px; color: var(--muted); }
  /* The measured event is a second reading of the same map, not the map itself. */
  /* Map controls belong on the map, not in the key underneath it. */
  .mapctl { position: absolute; top: 22px; right: 8px; z-index: 2; display: flex; align-items: center;
            gap: 8px; background: #0b1017; border: 1px solid #16202b; border-radius: 8px; padding: 4px; }
  #detail { background: transparent; color: var(--muted); font: inherit;
            font-size: 11.5px; border: 1px solid var(--line); border-radius: 6px;
            padding: 4px 11px; cursor: pointer; white-space: nowrap; }
  #detail:hover { color: var(--text); }
  #detail.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  #detail.hidden { display: none; }
  .zoomer { display: flex; align-items: center; gap: 0; }
  .zoomer button { background: transparent; color: var(--muted); font: inherit; font-size: 13px;
                   border: 1px solid var(--line); width: 26px; height: 24px; cursor: pointer; }
  .zoomer button:first-child { border-radius: 6px 0 0 6px; }
  .zoomer button:last-child { border-radius: 0 6px 6px 0; border-left: 0; }
  .zoomer button:hover:not(:disabled) { color: var(--text); }
  .zoomer button:disabled { opacity: .35; cursor: default; }
  .zoomer #zlvl { font-family: var(--mono); font-size: 11px; width: 42px;
                  border-radius: 0; border-left: 0; border-right: 0; }
  /* The map is a thing you handle, so it says so: grab it, drag it, and the
     wheel brings the point under the pointer closer rather than the middle. */
  #grid { cursor: grab; touch-action: none; }
  #grid.dragging { cursor: grabbing; }
  .mapview { overflow: hidden; }
  /* The cost panel: rows of number-then-explanation, so it reads as arithmetic
     rather than as a claim. */
  .scale h4 { margin: 14px 0 6px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
              color: var(--muted); font-weight: 600; }
  .scale h4:first-child { margin-top: 2px; }
  .scale table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  .scale td { padding: 3px 0; vertical-align: baseline; }
  .scale td.n { font-family: var(--mono); color: var(--text); text-align: right;
                white-space: nowrap; padding-right: 10px; width: 1%; }
  .scale td.k { color: var(--text); white-space: nowrap; padding-right: 10px; }
  .scale td.w { color: var(--muted); }
  .scale p { margin: 8px 0 0; color: var(--muted); font-size: 12.5px; line-height: 1.5; }
  .scale b { color: var(--text); font-weight: 600; }
  .legend i { display: inline-block; width: 13px; height: 13px; border-radius: 2px; vertical-align: -2px; margin-right: 6px;
              box-sizing: border-box; }
  .legend i.sw-low { border: 1px solid #2b3c4e; }
  .legend i.sw-medium { background: repeating-linear-gradient(-45deg, #d9b24d 0 1px, transparent 1px 5px); border: 1px solid #2b3c4e; }
  .legend i.sw-high { background: repeating-linear-gradient(-45deg, #f07a2a 0 1.2px, transparent 1.2px 4px),
                                  repeating-linear-gradient(45deg, #f07a2a 0 1.2px, transparent 1.2px 4px); border: 1px solid #2b3c4e; }
  .legend i.sw-dark { background: #04070d; border: 1px solid #3a1a1a; }
  /* The column is exactly as tall as the screen. The verdict and the brief are
     always visible; everything else lives behind a tab, so a reader is told what
     is there rather than left to guess that scrolling would reveal it. */
  /* Two things, not four. The verdict is what the room is looking at; everything
     else — the zones, the registry, the brief, the log — is one tab away. The
     brief used to sit in its own panel repeating the signals word for word,
     which is most of why this column looked busy. */
  aside { display: grid; grid-template-rows: minmax(0, auto) minmax(0, 1fr) auto; gap: 10px; min-height: 0; }
  /* The three numbers the commercial question turns on, on every frame. */
  .card.strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 10px 14px; }
  .strip div { min-width: 0; }
  .strip b { display: block; font-family: var(--mono); font-size: 17px; color: var(--text); letter-spacing: -.01em; }
  .strip span { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
  .card.status { max-height: 46vh; overflow: auto; }
  .tabbed { min-height: 220px; }
  .tabbed { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; padding: 0; overflow: hidden; }
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line); padding: 8px 10px 0; }
  .tabs button { background: transparent; border: 1px solid transparent; border-bottom: none;
                 color: var(--muted); font: inherit; font-size: 12.5px; padding: 6px 12px;
                 border-radius: 6px 6px 0 0; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); background: var(--panel-2); border-color: var(--line); }
  .panes { position: relative; min-height: 0; overflow: hidden; }
  .pane { display: none; height: 100%; overflow: auto; padding: 12px 14px 14px;
          scrollbar-width: thin; scrollbar-color: var(--line) transparent; }
  .pane.on { display: block; }
  .pane::-webkit-scrollbar { width: 8px; }
  .pane::-webkit-scrollbar-thumb { background: var(--line); border-radius: 4px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
  .card h3 { margin: 0 0 8px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  .status { border-left: 4px solid var(--line); }
  .status.k-DECLARE, .status.k-UPDATE, .status.k-SUSTAIN { border-left-color: var(--alert); }
  .status.k-CANDIDATE { border-left-color: var(--cand); }
  .status.k-ABSTAIN { border-left-color: var(--held); }
  .status.k-CLEAR { border-left-color: var(--ok); }
  /* A verdict reads top down: what it is, then how big, then why. */
  .vrow { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; flex-wrap: wrap; }
  .headline { font-size: 16px; font-weight: 600; margin: 0 0 10px; line-height: 1.32; }
  .headline .kind { font-family: var(--mono); font-size: 12px; padding: 2px 7px; border-radius: 4px; background: #1a2330; color: var(--muted); margin-right: 8px; vertical-align: 2px; }
  .chip { display: inline-block; font-family: var(--mono); font-size: 11px; padding: 2px 7px; border-radius: 4px; margin-right: 6px; background: #1a2330; color: var(--text); }
  .chip.HIGH { background: #3a1613; color: #ffb4ad; } .chip.MEDIUM { background: #3a2f10; color: #ffd98a; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; }
  .stat { background: var(--panel-2); border-radius: 6px; padding: 8px 10px; }
  .stat b { display: block; font-family: var(--mono); font-size: 21px; font-variant-numeric: tabular-nums; line-height: 1.15; }
  .stat span { font-size: 10.5px; color: var(--muted); line-height: 1.25; display: block; margin-top: 3px; }
  /* The reasons fold away until asked for; the verdict itself is enough to read first. */
  details.why { margin: 8px 0 0; border-top: 1px solid var(--line); }
  details.why summary { cursor: pointer; list-style: none; padding: 7px 0 2px; font-size: 11.5px; color: var(--muted);
                        display: flex; align-items: center; gap: 8px; user-select: none; }
  details.why summary::-webkit-details-marker { display: none; }
  details.why summary::before { content: "\25B8"; font-size: 10px; color: var(--dim); transition: transform .15s; }
  details.why[open] summary::before { transform: rotate(90deg); }
  details.why summary:hover { color: var(--text); }
  details.why summary .n { font-family: var(--mono); color: var(--text); }
  .signals { margin: 2px 0 0; padding: 0; list-style: none; }
  .signals li { margin: 0; padding: 5px 0 5px 15px; color: var(--muted); font-size: 12px;
                line-height: 1.4; border-bottom: 1px solid #16202b; position: relative; }
  .signals li:last-child { border-bottom: 0; }
  .signals li::before { content: ""; position: absolute; left: 3px; top: 11px; width: 4px; height: 4px;
                        border-radius: 50%; background: var(--dim); }
  .signals li.yes::before { background: var(--ok); }
  .signals li.no::before { background: var(--dim); }
  .signals b { color: var(--text); font-weight: 600; }
  /* The privacy boundary, stated on every pass rather than argued once. */
  /* One line, not a paragraph: the number is the claim. */
  .privacy { margin-top: 10px; padding: 6px 9px; border-radius: 6px; font-size: 11.5px; line-height: 1.35;
             border: 1px solid var(--line); display: flex; gap: 8px; align-items: center; }
  .privacy b { font-family: var(--mono); font-size: 10.5px; letter-spacing: .04em; white-space: nowrap; }
  .privacy span { color: var(--muted); }
  .privacy.shut { background: #10231a; border-color: #1d3d2c; color: #8fe0b0; }
  .privacy.open { background: #2a2413; border-color: #4a3f1c; color: #ffd98a; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-weight: 500; font-size: 11px; padding: 2px 6px 6px 0; }
  td { padding: 4px 6px 4px 0; border-top: 1px solid var(--line); vertical-align: top; }
  td.mono, th.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
  /* Rows that name a cell point at the map. */
  tr[data-cell] { cursor: pointer; }
  tr[data-cell]:hover td { background: #141d29; }
  tr[data-cell].picked td { background: #12283a; }
  tr[data-cell].picked td.mono:first-child { color: #7dd3fc; font-weight: 700; }
  .bar { height: 6px; background: var(--alert); border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 6px; }
  .empty { color: var(--dim); font-size: 13px; }
  .log { max-height: none; }
  .entry { padding: 8px 0; border-top: 1px solid var(--line); }
  .entry:first-child { border-top: 0; }
  .entry .when { font-family: var(--mono); color: var(--muted); font-size: 12px; margin-right: 8px; }
  .entry .g { font-family: var(--mono); margin-right: 6px; }
  .entry.k-DECLARE .g, .entry.k-UPDATE .g { color: var(--alert); } .entry.k-CANDIDATE .g { color: var(--cand); } .entry.k-ABSTAIN .g { color: var(--held); } .entry.k-CLEAR .g { color: var(--ok); }
  .entry ul { margin: 4px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; }
  .brief { font-size: 13px; line-height: 1.55; color: #c2d1de; }
  .brief.empty { color: var(--dim); }
  footer { display: flex; flex-wrap: wrap; gap: 18px; padding: 8px 20px 14px; color: var(--dim); font-family: var(--mono); font-size: 11px; }
  footer b { color: var(--text); font-weight: 600; }
  /* ODbL asks for credit, and a map that shows its sources is a better map. */
  footer .credit { color: var(--dim); margin-left: auto; }
  kbd { font-family: var(--mono); border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; color: var(--muted); }
</style>
</head>
<body>
<header>
  <div class="brand">Nabd <span>نبض · command centre</span></div>
  <nav id="scenes"></nav>
  <div class="clock"><span id="clock">09:00:00</span><small id="since">&nbsp;</small></div>
  <div class="controls">
    <button id="prev" title="previous pass (←)">‹</button>
    <button id="play" title="play / pause (space)">▶</button>
    <button id="next" title="next pass (→)">›</button>
    <input type="range" id="scrub" min="0" max="0" value="0">
    <button id="all" title="play every scene in order, without stopping">All</button>
    <span class="speeds" id="speeds"></span>
  </div>
</header>
<main>
  <section class="map">
    <div id="beat" class="beat empty"></div>
    <div class="mapview">
      <svg id="grid" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="mapctl">
        <button id="keybtn" title="what every colour and line on the map means">Map key</button>
        <button id="detail" class="hidden" title="measured intensity contours and the fault rupture">Measured intensity</button>
        <span class="zoomer"><button id="zout" title="zoom out">−</button><button id="zlvl" title="back to the whole picture">1×</button><button id="zin" title="zoom in — drag the map to move, or roll the wheel over the spot you want">+</button></span>
      </div>
      <div id="mapkey" class="hidden"></div>
      <div id="inspect" class="hidden"></div>
    </div>
    <div class="legend">
      <span><i class="sw-low"></i>Normal</span>
      <span><i class="sw-medium"></i>Medium load</span>
      <span><i class="sw-high"></i>High congestion</span>
      <span><i class="sw-dark"></i>Sentinel unreachable</span>
      <span><i style="border:2px solid var(--alert)"></i>Declared footprint</span>
      <span><i style="border:2px dashed var(--cand)"></i>Candidate</span>
      <span><i style="border:2px dashed var(--held)"></i>Explained, held</span>
      <span><i style="background:#fff;border-radius:50%"></i>Last-seen position</span>

    </div>
  </section>
  <aside>
    <div class="card status" id="status"></div>
    <div class="card tabbed">
      <div class="tabs" id="tabs">
        <button data-pane="zones" class="on">Priority zones</button>
        <button data-pane="registry">Registry</button>
        <button data-pane="brief">Brief</button>
        <button data-pane="log">Log</button>
        <button data-pane="scale">Scale</button>
      </div>
      <div class="panes">
        <div id="zones" class="pane on"></div>
        <div id="registry" class="pane"></div>
        <div id="brief" class="pane brief empty"></div>
        <div id="log" class="pane log"></div>
        <div id="scale" class="pane scale"></div>
      </div>
    </div>
    <div class="card strip" id="strip">
      <div><b id="s-pass">–</b><span>CAMARA calls, this pass</span></div>
      <div><b id="s-hour">–</b><span>calls / hour, this window</span></div>
      <div><b id="s-sims">–</b><span>SIMs to watch Türkiye</span></div>
    </div>
  </aside>
</main>
<footer>
  <span>CAMARA this pass <b id="calls-pass">0</b></span>
  <span>to date <b id="calls-total">0</b></span>
  <span>backend <b>offline simulator</b></span>
  <span>evidence <b id="evidence"></b></span>
  <span><kbd>space</kbd> play · <kbd>←</kbd><kbd>→</kbd> step · <kbd>1</kbd>–<kbd id="lastscene">5</kbd> scene</span>
  <span class="credit">map © OpenStreetMap contributors (ODbL) · Natural Earth · GeoNames (CC BY)<span id="intensity"></span></span>
</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('data').textContent);
  const S = 44, M = 26;
  const EPOCH = Date.UTC(2026, 8, 10, 9, 0, 0);
  const GLYPH = { QUIET: '·', CANDIDATE: '?', DECLARE: '!', UPDATE: '▲', SUSTAIN: '·', ABSTAIN: '—', CLEAR: '✓' };
  const CLASS = { '.': 'c-low', 'm': 'c-medium', 'H': 'c-high', 'D': 'c-dark', 'x': 'c-unmon' };
  const ACTIVE = new Set(['DECLARE', 'UPDATE', 'SUSTAIN']);
  const $ = id => document.getElementById(id);
  let scene = 0, pass = 0, timer = null;

  const clock = t => new Date(EPOCH + t * 1000).toISOString().slice(11, 19);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const age = s => s < 90 ? `${Math.round(s)}s` : `${Math.round(s / 60)} min`;

  function cur() { return DATA.scenes[scene]; }

  // -- header -------------------------------------------------------------
  const nav = $('scenes');
  $('lastscene').textContent = DATA.scenes.length;
  DATA.scenes.forEach((sc, i) => {
    const b = document.createElement('button');
    b.textContent = `${i + 1} · ${sc.title}`;
    b.title = sc.subtitle;
    b.onclick = () => setScene(i);
    nav.appendChild(b);
  });

  function setScene(i) {
    if (!timer) stop();           // a run through the scenes keeps its own timer
    scene = i; pass = 0; MAP = null; PICK = null;
    [...nav.children].forEach((b, k) => b.classList.toggle('on', k === i));
    $('scrub').max = cur().records.length - 1;
    $('evidence').textContent = `nabd-scene-${cur().name}.jsonl`;
    $('intensity').textContent = cur().geo ? ` · intensity USGS ShakeMap ${cur().geo.source.event}` : '';
    $('detail').classList.toggle('hidden', !cur().geo);
    if (!$('mapkey').classList.contains('hidden')) drawKey();
    setZoom(0);
    show(0);
  }

  // -- map ------------------------------------------------------------------
  let ORIGIN_X = M;  // the grid's left edge, once the view is widened to the panel

  // Zoom scales the geometry, not the viewBox, so line weights and place names
  // keep their size while the map spreads out under them — which is what makes a
  // zoomed map more readable rather than just bigger.
  //
  // A scale and an offset, and every single thing drawn on the map goes through
  // this pair. That is the whole contract: anything that skips it drifts out of
  // register the moment the reader zooms, which is exactly what used to happen
  // to the maintenance boxes and the uncertainty haloes.
  const zx = x => x * ZOOM + TX;   // unzoomed map units -> screen
  const zy = y => y * ZOOM + TY;

  // Geometry inside the scene is kept in unzoomed units and the scene's own
  // transform does the rest, so project() answers in those units.
  function project(lat, lon, g) {
    const a = g.cells[0], b = g.cells[1], c = g.cells[g.cols];
    const dlon = b.lon - a.lon, dlat = c.lat - a.lat; // dlat is negative (south)
    return [ORIGIN_X + ((lon - a.lon) / dlon + 0.5) * S,
            M + ((lat - a.lat) / dlat + 0.5) * S];
  }

  const viewTransform = () => `translate(${TX.toFixed(2)},${TY.toFixed(2)}) scale(${ZOOM})`;

  // One attribute write per layer moves the whole map; the hatch is
  // counter-scaled so its texture keeps the same weight at every zoom.
  function applyView() {
    if (!MAP) return;
    MAP.scene.setAttribute('transform', viewTransform());
    MAP.labels.setAttribute('transform', `translate(${TX.toFixed(2)},${TY.toFixed(2)})`);
    MAP.patterns.forEach(p => p.setAttribute('patternTransform', `rotate(45) scale(${(1 / ZOOM).toFixed(4)})`));
  }

  // The map is built once per scene and then only updated, because a redraw
  // cannot animate: replacing the DOM every pass is what made the playback snap
  // from one still to the next. Now the cells own a CSS transition and the pass
  // is something you watch happen.
  let MAP = null;
  let detail = false;   // the measured-event overlay, off unless asked for
  const ZOOMS = [1, 2, 4, 8];
  let zi = 0;           // index into ZOOMS
  let ZOOM = 1, TX = 0, TY = 0;   // scale, and where the scaled map sits

  function mapGeometry(g, svg) {
    const rect = svg.getBoundingClientRect();
    const H = M + g.rows * S + 6;
    const natural = M + g.cols * S + 6;
    const ratio = rect.height > 0 ? rect.width / rect.height : 1;
    const W = Math.max(natural, H * ratio);
    return { W, H, OX: M + (W - natural) / 2 };
  }

  function buildMap() {
    const g = cur().grid, svg = $('grid');
    const { W, H, OX } = mapGeometry(g, svg);
    ORIGIN_X = OX;
    svg.setAttribute('viewBox', `0 0 ${W.toFixed(1)} ${H}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    const x0 = OX, y0 = M, w = g.cols * S, h = g.rows * S;
    // Two decimals: the scene is built once at 1x and shown at up to 8x, and a
    // tenth of a unit would show as a wobble in the streets by then.
    const line = pts => pts.map((p, i) => {
      const [x, y] = project(p[1], p[0], g);
      return (i ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2);
    }).join('');
    const out = [];

    out.push(`<defs>`
      + `<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">`
      + `<stop offset="0" stop-color="#0c1420"/><stop offset="1" stop-color="#080d14"/></linearGradient>`
      + `<clipPath id="viewclip"><rect x="0" y="0" width="${W.toFixed(1)}" height="${H}"/></clipPath>`
      + `<clipPath id="winclip"><rect x="${x0.toFixed(1)}" y="${y0}" width="${w}" height="${h}"/></clipPath>`
      // Hatches in user units, so the texture stays the same weight at every zoom
      // while the cells under it grow.
      + `<pattern id="hatch-medium" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(45)">`
      + `<line x1="0" y1="0" x2="0" y2="9" stroke="#d9b24d" stroke-width="1" stroke-opacity=".5"/></pattern>`
      + `<pattern id="hatch-high" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">`
      + `<line x1="0" y1="0" x2="0" y2="6" stroke="#f07a2a" stroke-width="1" stroke-opacity=".62"/>`
      + `<line x1="0" y1="3" x2="6" y2="3" stroke="#f07a2a" stroke-width="1" stroke-opacity=".62"/></pattern>`
      + `<filter id="glow" x="-30%" y="-30%" width="160%" height="160%">`
      + `<feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/>`
      + `<feMergeNode in="SourceGraphic"/></feMerge></filter>`
      + `</defs>`);
    out.push(`<rect class="ground" x="0" y="0" width="${W.toFixed(1)}" height="${H}"/>`);

    // Everything that is *the map* lives in one scaled group; the clip that
    // keeps it inside the view sits on the parent, in screen units, so it does
    // not travel with the scene.
    out.push(`<g clip-path="url(#viewclip)"><g id="scene" transform="${viewTransform()}">`);

    // -- the region, or the city ---------------------------------------------
    const geo = detail ? cur().geo : null;
    const isCity = !!cur().city;          // the scene watches one city, not a region
    const MS = DATA.maps[cur().maps] || {};
    const base = MS.base;
    out.push('<g>');
    if (base) base.borders.forEach(l => out.push(`<path class="border" d="${line(l)}"/>`));
    const decode = (a, k) => {
      const pts = []; let x = a[0], y = a[1];
      pts.push([x / k, y / k]);
      for (let i = 2; i < a.length; i += 2) { x += a[i]; y += a[i + 1]; pts.push([x / k, y / k]); }
      return pts;
    };
    const layer = (src, key, cls) => {
      if (!src) return;
      const bucket = key.split('.').reduce((o, p) => (o || {})[p], src) || [];
      bucket.forEach(l => out.push(`<path class="${cls}" d="${line(decode(l, src.scale))}"/>`));
    };
    // Water is ground, so it goes down before the readings; the roads come back
    // over the top of them.
    const ground = isCity ? MS.city : MS.region;
    if (ground) ground.water.forEach(l => out.push(`<path class="water" d="${line(decode(l, ground.scale))}Z"/>`));
    out.push('</g>');

    const field = (id, cls) => {
      out.push(`<g clip-path="url(#winclip)"><g id="${id}">`);
      g.cells.forEach(c => out.push(
        `<rect class="cell ${cls}" data-k="${c.row * g.cols + c.col}" x="${(OX + c.col * S).toFixed(1)}" y="${M + c.row * S}" width="${S}" height="${S}"><title>${c.id} · ${c.lat.toFixed(4)}N ${c.lon.toFixed(4)}E</title></rect>`));
      out.push('</g></g>');
    };

    // -- the streets ---------------------------------------------------------
    out.push('<g>');
    if (isCity) {
      layer(MS.city, 'roads.local', 'rd-local');
      layer(MS.city, 'roads.minor', 'rd-minor');
      layer(MS.city, 'roads.major', 'rd-major');
      layer(MS.city, 'streams', 'river');
      layer(MS.city, 'rail', 'rail');
    } else {
      // The city scenes look the way they do because the ground under them is
      // dense. The region gets the same treatment from the start: the whole
      // between-towns network, not just the trunk roads, so the map has texture
      // to read the footprint against. Zooming in then adds the streets.
      layer(MS.city, 'roads.local', 'rd-local');
      layer(MS.city, 'roads.minor', 'rd-minor');
      layer(MS.mid, 'roads.minor', 'rd-local');
      layer(MS.region, 'roads.major', 'rd-major');
      layer(MS.region, 'streams', 'river');
    }
    out.push('</g>');

    // -- how loaded the network is: a hatch over the streets, never a wash ---
    field('cells', 'c-unmon');

    // -- what has gone dark, over everything: it is an absence, not a tint ---
    field('dark', 'c-clear');

    out.push('<g clip-path="url(#winclip)"><g id="fpfills">');
    g.cells.forEach(c => out.push(
      `<rect class="fpfill" data-id="${c.id}" x="${(OX + c.col * S).toFixed(1)}" y="${M + c.row * S}" width="${S}" height="${S}"/>`));
    out.push('</g></g>');
    out.push('<g id="mnt" clip-path="url(#winclip)"></g>');

    // -- the measured event --------------------------------------------------
    if (geo) {
      out.push('<g>');
      geo.contours.forEach(lv => {
        const major = Math.abs(lv.mmi - Math.round(lv.mmi)) < 0.01;
        lv.lines.forEach(l => out.push(
          `<path class="iso${major ? ' major' : ''}" d="${line(l)}" stroke="${lv.color}"><title>Measured intensity MMI ${lv.mmi}</title></path>`));
      });
      geo.rupture.forEach(r => out.push(
        `<path class="rupture" d="${line(r)}Z"><title>Finite-fault rupture, USGS ShakeMap</title></path>`));
      out.push('</g>');
    }

    out.push('<g id="edge" filter="url(#glow)"></g>');
    out.push('<g id="pick"></g>');
    out.push('<g id="dots"></g>');

    out.push('</g></g>');                        // #scene, and its clip
    out.push('<g id="labels"></g>');            // names and dots: translated, never scaled
    out.push('</g>');                            // the view clip
    out.push('<g id="chrome"></g><g id="fplabel"></g>');
    svg.innerHTML = out.join('');
    MAP = { name: cur().name, w: Math.round(svg.getBoundingClientRect().width), OX, W, H,
            cells: [...svg.querySelectorAll('#cells rect')],
            dark: [...svg.querySelectorAll('#dark rect')],
            fills: new Map([...svg.querySelectorAll('#fpfills rect')].map(r => [r.dataset.id, r])),
            scene: svg.querySelector('#scene'), labels: svg.querySelector('#labels'),
            patterns: [...svg.querySelectorAll('pattern')] };
    applyView();
    drawLabels();
    drawChrome();
  }

  // -- place names: laid out in screen units so they never scale -----------
  // The ruled margin covers a strip along the top and the left of the window;
  // a name that would sit under it is left out rather than half-covered.
  const BAND = 16;
  function drawLabels() {
    if (!MAP) return;
    const g = cur().grid, { W, H, OX } = MAP;
    const isCity = !!cur().city;
    const MS = DATA.maps[cur().maps] || {};
    const places = (isCity ? MS.city : MS.region);
    const x0 = OX, y0 = M, w = g.cols * S, h = g.rows * S;
    const underBand = (x, y) => y < BAND + 6 || x < BAND + 6;
    const out = [];
    if (places) {
      // Places are ranked, so when two labels want the same spot the more
      // important one keeps it and the other loses its text but keeps its dot.
      const placed = [];
      // Cities and towns are always named. Villages and neighbourhoods wait for
      // the zoom: at 1x they were most of what made the map hard to look at.
      const rankCap = ZOOM >= 4 ? 9 : ZOOM >= 2 ? 3 : 2;
      places.places.forEach(t => {
        if (t.rank > rankCap) return;
        const [bx, by] = project(t.lat, t.lon, g);
        const x = bx * ZOOM, y = by * ZOOM;               // in the translated layer
        const px = x + TX, py = y + TY;                    // on screen
        if (px < 4 || px > W - 4 || py < 4 || py > H - 4 || underBand(px, py)) return;
        const big = t.rank <= 2;
        out.push(`<circle class="town${big ? ' major' : ''}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${big ? 3.4 : 1.8}"/>`);
        const wide = t.name.length * (big ? 6.6 : 4.6) + 10, tall = big ? 13 : 10;
        if (px + wide > W - 6) return;                    // a name that would run off the sheet keeps its dot only
        if (placed.some(p => Math.abs(p.x - x) < (p.w + wide) / 2 && Math.abs(p.y - y) < (p.h + tall) / 2)) return;
        placed.push({ x, y, w: wide, h: tall });
        out.push(`<text class="placelbl${big ? ' big' : ''}" x="${(x + (big ? 7 : 4)).toFixed(1)}" y="${(y + 3).toFixed(1)}">${t.name}</text>`);
      });
    }
    MAP.labels.innerHTML = out.join('');
  }

  // -- the window, its margin and the furniture of a map: screen units -----
  function drawChrome() {
    if (!MAP) return;
    const g = cur().grid, { W, H, OX } = MAP;
    const x0 = OX, y0 = M, w = g.cols * S, h = g.rows * S;
    const SZ = S * ZOOM;
    const out = [];
    const X0 = zx(x0), Y0 = zy(y0), X1 = X0 + w * ZOOM, Y1 = Y0 + h * ZOOM;
    const f = n => n.toFixed(1);

    // No rectangle around the window and no dimming outside it: the margin's
    // ticks are long and lettered where there are cells and short where there
    // are none, which is how a map sheet says where its grid runs.

    // The grid reference, in a ruled margin along the top and the left. The
    // margin runs along the sheet's own top and left edges, the way a map
    // sheet's does: ticks the whole way along at the cell pitch, and letters
    // and numbers only where there are cells to name. It does not move with
    // the window, so it never floats in the middle of the map.
    const TICK = 4;
    out.push(`<rect class="ruler" x="0" y="0" width="${f(W)}" height="${BAND}"/>`);
    out.push(`<rect class="ruler" x="0" y="${BAND}" width="${BAND}" height="${f(H - BAND)}"/>`);
    out.push(`<path class="ruler-edge" d="M0 ${BAND}H${f(W)}M${BAND} ${BAND}V${f(H)}"/>`);
    const letters = 'ABCDEFGHIJKLMNOPQRST';
    const c0 = Math.floor((BAND - zx(OX)) / SZ), c1 = Math.ceil((W - zx(OX)) / SZ);
    for (let c = c0; c <= c1; c++) {
      const x = zx(OX + c * S);
      if (x < BAND || x > W) continue;
      const named = c >= 0 && c <= g.cols;
      out.push(`<path class="tick" d="M${f(x)} ${f(BAND - (named ? TICK : 2))}V${BAND}"/>`);
      if (c >= 0 && c < g.cols) {
        const mid = x + SZ / 2;
        if (mid > BAND + 5 && mid < W - 5) out.push(`<text class="lbl" x="${f(mid)}" y="11.5" text-anchor="middle">${c + 1}</text>`);
      }
    }
    const r0 = Math.floor((BAND - zy(M)) / SZ), r1 = Math.ceil((H - zy(M)) / SZ);
    for (let r = r0; r <= r1; r++) {
      const y = zy(M + r * S);
      if (y < BAND || y > H) continue;
      const named = r >= 0 && r <= g.rows;
      out.push(`<path class="tick" d="M${f(BAND - (named ? TICK : 2))} ${f(y)}H${BAND}"/>`);
      if (r >= 0 && r < g.rows) {
        const mid = y + SZ / 2;
        if (mid > BAND + 5 && mid < H - 5) out.push(`<text class="lbl" x="${BAND / 2}" y="${f(mid + 3.5)}" text-anchor="middle">${letters[r]}</text>`);
      }
    }

    // A scale bar keeps its length and changes its number, the way a paper map
    // does. Pick the roundest distance near the bar we already draw at 1×.
    const km = g.spacing_m / 1000;
    const LADDER = [.1, .2, .25, .5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 500];
    const want = (km >= 5 ? 50 : 2) / ZOOM;
    const span = LADDER.reduce((a, b) => Math.abs(b - want) < Math.abs(a - want) ? b : a);
    const bar = (span / km) * SZ, bx = BAND + 14, by = H - 14;
    out.push(`<path class="scale" d="M${bx} ${by - 5}V${by}H${(bx + bar).toFixed(1)}V${by - 5}"/>`);
    out.push(`<text class="scaletxt" x="${bx}" y="${by - 9}">${span < 1 ? Math.round(span * 1000) + ' m' : span + ' km'}</text>`);
    const cx = W - 20, cy = H - 40;
    out.push(`<text class="compass" x="${cx.toFixed(1)}" y="${cy}" text-anchor="middle">N</text>`);
    out.push(`<path class="scale" d="M${cx.toFixed(1)} ${cy + 4}V${cy + 22}M${(cx - 4).toFixed(1)} ${cy + 9}L${cx.toFixed(1)} ${cy + 4}L${(cx + 4).toFixed(1)} ${cy + 9}"/>`);

    $('chrome').innerHTML = out.join('');
  }

  function drawMap(rec) {
    const svg = $('grid'), g = cur().grid;
    const width = Math.round(svg.getBoundingClientRect().width);
    if (!MAP || MAP.name !== cur().name || Math.abs(MAP.w - width) > 8) buildMap();
    const { OX, W, H } = MAP;
    ORIGIN_X = OX;

    // -- the field ----------------------------------------------------------
    MAP.cells.forEach((rect, k) => {
      const ch = (rec.grid || '')[k] || 'x';
      // Under the streets: how loaded the cell is. A dark cell has no reading at
      // all, so it shows as unmonitored here and as black in the layer above.
      rect.setAttribute('class', 'cell ' + (ch === 'D' ? 'c-unmon' : CLASS[ch]));
    });
    MAP.dark.forEach((rect, k) => {
      rect.setAttribute('class', 'cell ' + ((rec.grid || '')[k] === 'D' ? 'c-dark' : 'c-clear'));
    });

    // -- what the verdict claims, as a tint that grows ----------------------
    let cls = null;
    if (ACTIVE.has(rec.kind)) cls = 'on';
    else if (rec.kind === 'CANDIDATE') cls = 'cand';
    else if (rec.kind === 'ABSTAIN' || (rec.reason || '').startsWith('holding')) cls = 'held';
    const claimed = new Set(cls ? rec.cells : []);
    MAP.fills.forEach((rect, id) => {
      rect.setAttribute('class', 'fpfill' + (claimed.has(id) ? ' ' + cls : ''));
    });

    // -- and its edge --------------------------------------------------------
    const edge = [];
    if (cls && rec.cells.length) {
      const set = new Set(rec.cells);
      rec.cells.forEach(id => {
        const cell = g.cells.find(c => c.id === id);
        const x = OX + cell.col * S, y = M + cell.row * S;
        const sz = S;
        const n = (dr, dc) => set.has((g.cells.find(c => c.row === cell.row + dr && c.col === cell.col + dc) || {}).id);
        if (!n(-1, 0)) edge.push(`M${x.toFixed(1)} ${y.toFixed(1)}h${sz.toFixed(1)}`);
        if (!n(1, 0)) edge.push(`M${x.toFixed(1)} ${(y + sz).toFixed(1)}h${sz.toFixed(1)}`);
        if (!n(0, -1)) edge.push(`M${x.toFixed(1)} ${y.toFixed(1)}v${sz.toFixed(1)}`);
        if (!n(0, 1)) edge.push(`M${(x + sz).toFixed(1)} ${y.toFixed(1)}v${sz.toFixed(1)}`);
      });
    }
    const style = cls === 'on' ? 'fp' : (cls === 'cand' ? 'cand' : 'held');
    $('edge').innerHTML = edge.length ? `<path class="${style}" d="${edge.join('')}" fill="none"/>` : '';

    // -- maintenance, people, and the footprint's own label ------------------
    const mnt = [];
    (cur().maintenance || []).forEach(m => {
      if (rec.t >= m.start && rec.t < m.end) m.cells.forEach(id => {
        const cell = g.cells.find(c => c.id === id);
        // Through zx/zy like everything else: these used to be pinned to the
        // unzoomed grid, so the yellow boxes stayed put while the map moved.
        mnt.push(`<rect class="mnt" x="${(OX + cell.col * S + 3).toFixed(1)}" y="${(M + cell.row * S + 3).toFixed(1)}" width="${S - 6}" height="${S - 6}" rx="2"/>`);
      });
    });
    $('mnt').innerHTML = mnt.join('');

    const dots = [];
    if (rec.triage) rec.triage.top.forEach(p => {
      if (!p.last_seen) return;
      const [x, y] = project(p.last_seen.lat, p.last_seen.lon, g);
      const r = (p.last_seen.radius_m / g.spacing_m) * S;   // a real distance: the scene's scale applies
      dots.push(`<circle class="halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"/>`);
      // The dot is a marker, not a distance, so it is sized against the scale.
      dots.push(`<circle class="dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(4 / ZOOM).toFixed(2)}"><title>${p.person} · ${p.class} · ${p.cell}</title></circle>`);
    });
    $('dots').innerHTML = dots.join('');

    drawFootprintLabel(rec);
    drawInspect(rec);
  }

  // -- the cell inspector -------------------------------------------------
  // A click on a cell asks the map about that place. The card is rebuilt on
  // every pass so it follows the playback, and the picked cell is outlined.
  let PICK = null;   // cell id, or null

  function pickCell(id) {
    PICK = PICK === id ? null : id;
    const rec = cur().records[pass];
    drawInspect(rec);
    drawZones(rec);
    drawRegistry(rec);
  }
  ['zones', 'registry'].forEach(id => $(id).addEventListener('click', e => {
    const row = e.target.closest('tr[data-cell]');
    if (row) pickCell(row.dataset.cell);
  }));

  function pickAt(sx, sy) {
    if (!MAP) return;
    const g = cur().grid, { OX } = MAP;
    const mx = (sx - TX) / ZOOM, my = (sy - TY) / ZOOM;
    const col = Math.floor((mx - OX) / S), row = Math.floor((my - M) / S);
    const cell = g.cells.find(c => c.col === col && c.row === row);
    PICK = cell && PICK !== cell.id ? cell.id : null;
    const rec = cur().records[pass];
    drawInspect(rec);
    drawZones(rec);
    drawRegistry(rec);
  }

  function drawInspect(rec) {
    const box = $('inspect'), g = cur().grid, sc = cur();
    const cell = PICK && g.cells.find(c => c.id === PICK);
    if (!cell) { box.classList.add('hidden'); $('pick').innerHTML = ''; return; }
    const { OX } = MAP;
    $('pick').innerHTML = `<rect class="pick" x="${(OX + cell.col * S).toFixed(1)}" y="${M + cell.row * S}" width="${S}" height="${S}"/>`;

    const k = cell.row * g.cols + cell.col;
    const ch = (rec.grid || '')[k] || 'x';
    const STATE = { '.': ['Sentinel answers · load normal', ''], 'm': ['Sentinel answers · medium load', ''],
                    'H': ['Sentinel answers · <b>high congestion</b>', ''], 'D': ['<b>Sentinel unreachable</b>', ''], 'x': ['Not monitored', 'muted'] };
    // How long the current state has held, and how often the cell has been dark.
    const upto = sc.records.slice(0, pass + 1);
    let run = 0;
    for (let i = upto.length - 1; i >= 0 && (upto[i].grid || '')[k] === ch; i--) run++;
    const darkPasses = upto.filter(r => (r.grid || '')[k] === 'D').length;
    const since = run > 1 ? ` — for ${run} passes (${Math.round((run - 1) * 30 / 60) || '<1'} min)` : '';
    const history = darkPasses ? `dark in ${darkPasses} of ${upto.length} passes so far` : `never dark so far`;

    // What the agent has said about this cell on this pass.
    let agent = 'Not claimed.', agentCls = 'muted';
    const inFp = rec.cells.includes(cell.id);
    if (inFp && ACTIVE.has(rec.kind)) { agent = `Inside the <b>declared footprint</b> · ${rec.confidence || ''}`; agentCls = ''; }
    else if (inFp && rec.kind === 'CANDIDATE') { agent = 'In the <b>candidate</b> block — held one more pass'; agentCls = ''; }
    else if (inFp && rec.kind === 'ABSTAIN') { agent = `Held: ${esc(rec.reason)}`; agentCls = ''; }
    const ticket = (sc.maintenance || []).find(m => m.cells.includes(cell.id) && rec.t >= m.start && rec.t < m.end);

    // People: an aggregate count, and the unreachable already in the evidence.
    const registered = (sc.registry_by_cell || {})[cell.id] || 0;
    const unreachable = rec.triage ? rec.triage.top.filter(p => p.cell === cell.id) : [];
    let people = registered ? `${registered} registered` : 'nobody on the registry';
    if (unreachable.length) people += ` · <b>${unreachable.length} unreachable</b>: ` + unreachable.map(p =>
      `<span class="mono">${p.person}</span> (${p.class}${p.last_seen ? `, ±${p.last_seen.radius_m} m` : ''})`).join(', ');
    else if (registered && rec.triage && ACTIVE.has(rec.kind) && inFp) people += ' · all reachable';
    else if (registered && !rec.triage) people += ' · not queried (no footprint)';

    // Places inside the cell, and the measured shaking for the real events.
    const MS = DATA.maps[sc.maps] || {};
    const src = sc.city ? MS.city : MS.region;
    const a = g.cells[0], b = g.cells[1], c2 = g.cells[g.cols];
    const dlon = Math.abs(b.lon - a.lon), dlat = Math.abs(c2.lat - a.lat);
    const places = src ? src.places.filter(p => Math.abs(p.lon - cell.lon) <= dlon / 2 && Math.abs(p.lat - cell.lat) <= dlat / 2)
      .sort((p, q) => p.rank - q.rank).slice(0, 5).map(p => p.name) : [];
    const mmi = sc.mmi && sc.mmi[cell.id];

    const row = (kk, v, cls = '') => `<div class="r"><div class="k">${kk}</div><div class="v ${cls}">${v}</div></div>`;
    let html = `<button class="close" title="close">×</button>`;
    html += `<h5><span class="id">${cell.id}</span>${places[0] ? esc(places[0]) : 'cell'}<span class="ll">${cell.lat.toFixed(4)}N ${cell.lon.toFixed(4)}E</span></h5>`;
    html += row('Network', STATE[ch][0] + since, STATE[ch][1]);
    html += row('History', history, 'muted');
    html += row('Agent', agent, agentCls);
    if (ticket) html += row('Maintenance', `ticket <span class="mono">${esc(ticket.ticket)}</span> covers this cell`);
    html += row('Registry', people, registered ? '' : 'muted');
    if (mmi != null) html += row('Shaking', `MMI <b>${mmi.toFixed(1)}</b> · ${mmiWord(mmi)} — USGS ShakeMap ${cur().geo && cur().geo.source ? cur().geo.source.event : ''}`);
    if (places.length) html += row('Places', places.map(esc).join(', '), 'muted');
    html += `<div class="hint">click the cell again, or Esc, to close</div>`;
    box.innerHTML = html;
    box.classList.remove('hidden');
    box.querySelector('.close').onclick = () => { PICK = null; drawInspect(rec); drawZones(rec); drawRegistry(rec); };
  }

  // The footprint's own label is chrome: placed in screen units against the
  // view, so it stays readable however far the map has been dragged.
  function drawFootprintLabel(rec) {
    if (!MAP) return;
    const g = cur().grid, { OX, W, H } = MAP;
    let label = '';
    if (ACTIVE.has(rec.kind) && rec.cells.length) {
      const cells = rec.cells.map(id => g.cells.find(c => c.id === id));
      const bottom = Math.max(...cells.map(c => c.row)), left = Math.min(...cells.map(c => c.col));
      const text = `FOOTPRINT · ${rec.confidence || ''} · ${(rec.cells.length * (g.spacing_m / 1000) ** 2).toFixed(1)} km²`;
      const bw = text.length * 6.8 + 12;
      const bx = Math.max(4, Math.min(zx(OX + left * S), W - bw - 4));
      const by = Math.min(Math.max(zy(M + (bottom + 1) * S) + 6, 4), H - 20);
      label = `<rect x="${bx.toFixed(1)}" y="${by.toFixed(1)}" width="${bw.toFixed(1)}" height="18" rx="4" fill="#0b1017" stroke="var(--alert)" stroke-width="1"/>`
            + `<text class="fplabel" x="${(bx + 6).toFixed(1)}" y="${(by + 13).toFixed(1)}">${text}</text>`;
    }
    $('fplabel').innerHTML = label;
  }

  addEventListener('resize', () => { MAP = null; if (cur()) drawMap(cur().records[pass]); });

  // -- panels -----------------------------------------------------------------
  // Each signal says whether the thing it names was found. Colouring the dot by
  // that turns a wall of sentences into something scannable: green fired, grey
  // did not, and a reader sees the shape of the evidence before reading a word.
  function signalFired(text) {
    return !/^no |staggered|not enough history|no local baseline/i.test(text);
  }

  let WHY_OPEN = false;   // the reasons stay open once opened, across passes
  document.addEventListener('toggle', e => { if (e.target.matches('details.why')) WHY_OPEN = e.target.open; }, true);

  function drawStatus(rec) {
    const sc = cur(), el = $('status');
    el.className = `card status k-${rec.kind}`;
    const declared = sc.records.slice(0, pass + 1).find(r => r.kind === 'DECLARE');
    let head = rec.reason || (rec.kind === 'QUIET' ? 'Monitoring. Nothing anomalous.' : '');
    if (rec.kind === 'SUSTAIN' && !rec.signals.length) head = rec.reason || 'Footprint held.';
    const change = registryChange(rec);

    // Row one: what this is, at a glance.
    let html = `<div class="vrow"><span class="kind">${GLYPH[rec.kind]} ${rec.kind}</span>`;
    if (rec.confidence) html += `<span class="chip ${rec.confidence}">${rec.confidence}</span>`;
    if (declared) html += `<span class="chip">declared ${clock(declared.t)}${sc.onset != null ? ` · +${Math.round(declared.t - sc.onset)}s` : ''}</span>`;
    if (change) html += `<span class="chip">registry ${change[0]} → ${change[1]}</span>`;
    html += `</div>`;

    html += `<div class="headline">${esc(head)}</div>`;

    const km2 = rec.cells.length ? (rec.cells.length * (sc.grid.spacing_m / 1000) ** 2).toFixed(1) : '–';
    html += `<div class="stats">
      <div class="stat"><b>${ACTIVE.has(rec.kind) ? rec.cells.length : '–'}</b><span>cells</span></div>
      <div class="stat"><b>${ACTIVE.has(rec.kind) ? km2 : '–'}</b><span>km²</span></div>
      <div class="stat"><b>${rec.triage ? rec.triage.unreachable : '–'}</b><span>unreachable of ${rec.triage ? rec.triage.inside : sc.registry}</span></div>
    </div>`;

    if (rec.privacy) {
      const open = !!rec.privacy.open;
      html += `<div class="privacy ${open ? 'open' : 'shut'}">`
            + `<b>${open ? '◉ PERSONAL DATA' : '○ PERSONAL DATA'}</b>`
            + `<span>${open
                ? `${rec.privacy.personal} call${rec.privacy.personal === 1 ? '' : 's'} this pass, all inside the footprint`
                : 'closed — the registry was not queried'}</span></div>`;
    }
    if (rec.signals.length && rec.kind !== 'SUSTAIN') {
      const fired = rec.signals.filter(signalFired).length;
      html += `<details class="why"${WHY_OPEN ? ' open' : ''}><summary>Why \u00b7 <span class="n">${fired} of ${rec.signals.length}</span> signals present</summary>`
        + `<ul class="signals">${rec.signals.map(sig => {
        const at = sig.indexOf(':');
        const body = at > 0 && at < 34
          ? `<b>${esc(sig.slice(0, at))}</b>${esc(sig.slice(at))}`
          : esc(sig);
        return `<li class="${signalFired(sig) ? 'yes' : 'no'}">${body}</li>`;
      }).join('')}</ul></details>`;
    }

    el.innerHTML = html;
  }

  function registryChange(rec) {
    if (!rec.triage) return null;
    const recs = cur().records;
    for (let i = recs.indexOf(rec) - 1; i >= 0; i--) {
      if (recs[i].triage) return recs[i].triage.unreachable === rec.triage.unreachable ? null : [recs[i].triage.unreachable, rec.triage.unreachable];
    }
    return null;
  }

  function drawBrief(rec) {
    const recs = cur().records;
    let text = '';
    for (let i = pass; i >= 0; i--) { if (recs[i].brief && recs[i].kind !== 'QUIET') { text = recs[i].brief; break; } }
    if (rec.kind === 'QUIET' && rec.brief === '' && !recs.slice(0, pass + 1).some(r => ACTIVE.has(r.kind))) text = '';
    const el = $('brief');
    el.classList.toggle('empty', !text);
    el.textContent = text || 'No brief. The agent has nothing to tell the duty officer.';
  }

  function drawZones(rec) {
    const el = $('zones');
    if (!rec.triage || !ACTIVE.has(rec.kind)) { el.innerHTML = '<div class="empty">No declared footprint.</div>'; return; }
    const counts = {};
    rec.cells.forEach(c => counts[c] = 0);
    rec.triage.top.forEach(p => counts[p.cell] = (counts[p.cell] || 0) + 1);
    const rows = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const max = Math.max(1, ...rows.map(r => r[1]));
    el.innerHTML = `<table><tr><th class="mono">zone</th><th>unreachable registered</th></tr>` +
      rows.map(([cell, n]) => `<tr data-cell="${cell}"${cell === PICK ? ' class="picked"' : ''} title="show ${cell} on the map"><td class="mono">${cell}</td><td><span class="bar" style="width:${Math.round(n / max * 120)}px"></span>${n}</td></tr>`).join('') + '</table>';
  }

  function drawRegistry(rec) {
    const el = $('registry');
    if (!rec.triage) { el.innerHTML = '<div class="empty">Not queried. No personal device is touched outside a declared footprint.</div>'; return; }
    if (!rec.triage.top.length) { el.innerHTML = '<div class="empty">Everyone registered inside the footprint is reachable.</div>'; return; }
    el.innerHTML = `<table><tr><th class="mono">id</th><th>class</th><th class="mono">cell</th><th>last seen</th></tr>` +
      rec.triage.top.map(p => `<tr data-cell="${p.cell}"${p.cell === PICK ? ' class="picked"' : ''} title="show ${p.cell} on the map"><td class="mono">${p.person}</td><td>${p.class}</td><td class="mono">${p.cell}</td><td>${p.last_seen ? `${age(p.last_seen.age_s)} ago · ±${p.last_seen.radius_m} m` : '–'}</td></tr>`).join('') + '</table>';
  }

  function drawLog() {
    const recs = cur().records.slice(0, pass + 1);
    const items = [];
    recs.forEach(r => {
      const change = registryChange(r);
      if (r.kind === 'QUIET' || (r.kind === 'SUSTAIN' && !change)) return;
      let text = r.reason;
      if (change) text += ` — registry ${change[0]} → ${change[1]} unreachable`;
      const sig = (r.kind === 'SUSTAIN' ? [] : r.signals).map(s => `<li>${esc(s)}</li>`).join('');
      items.push(`<div class="entry k-${r.kind}"><span class="when">${clock(r.t)}</span><span class="g">${GLYPH[r.kind]} ${r.kind}</span>${esc(text)}${sig ? `<ul>${sig}</ul>` : ''}</div>`);
    });
    $('log').innerHTML = items.length ? items.reverse().join('') : '<div class="empty">Nothing to report.</div>';
  }

  function drawBeat(rec) {
    const beats = cur().beats.filter(b => b.t <= rec.t);
    const el = $('beat');
    if (!beats.length) { el.className = 'beat empty'; el.textContent = ''; return; }
    el.className = 'beat';
    el.textContent = beats[beats.length - 1].note;
  }

  function drawFooter(rec) {
    // The calls arrive as a tally per pass — {endpoint: count} — so the number
    // on screen is the sum of it.
    const calls = r => Object.values(r.api_calls || {}).reduce((n, c) => n + c, 0);
    $('calls-pass').textContent = calls(rec);
    $('calls-total').textContent = cur().records.slice(0, pass + 1).reduce((n, r) => n + calls(r), 0);
  }

  function show(i) {
    const recs = cur().records;
    pass = Math.max(0, Math.min(recs.length - 1, i));
    const rec = recs[pass];
    $('scrub').value = pass;
    $('clock').textContent = clock(rec.t);
    const sc = cur();
    $('since').textContent = sc.onset != null && rec.t >= sc.onset ? `+${Math.round(rec.t - sc.onset)}s since onset` : `pass ${pass + 1} / ${recs.length}`;
    drawBeat(rec); drawMap(rec); drawStatus(rec); drawBrief(rec); drawZones(rec); drawRegistry(rec); drawLog(); drawScale(rec); drawFooter(rec);
    // Say how much is behind each tab, so the count is visible without opening it.
    const counts = { zones: (rec.triage ? rec.triage.top.length : 0), registry: (rec.triage ? rec.triage.unreachable : 0), brief: null, log: null, scale: null };
    const names = { zones: 'Priority zones', registry: 'Registry', brief: 'Brief', log: 'Log', scale: 'Scale' };
    [...$('tabs').children].forEach(b => {
      const n = counts[b.dataset.pane];
      b.textContent = n ? `${names[b.dataset.pane]} · ${n}` : names[b.dataset.pane];
    });
  }

  // -- playback ---------------------------------------------------------------
  // A pass every 900 ms at 1×; the divisor is what the speed buttons change.
  const STEP_MS = 900;
  const SPEEDS = [1, 1.5, 2];
  let speed = 1;
  let playAll = false;   // run through every scene rather than stopping at the end

  function tick() {
    if (pass < cur().records.length - 1) return show(pass + 1);
    // End of a scene. Either that is the end, or the next scene starts.
    if (!playAll || scene >= DATA.scenes.length - 1) return stop();
    const running = true;
    setScene(scene + 1);
    if (running) resume();
  }

  function resume() {
    clearInterval(timer);
    $('play').textContent = '❚❚';
    timer = setInterval(tick, STEP_MS / speed);
  }

  function play() {
    if (timer) return stop();
    const last = cur().records.length - 1;
    // Starting from the end replays: from the top of this scene, or of the film.
    if (pass >= last) {
      if (playAll && scene >= DATA.scenes.length - 1) setScene(0);
      pass = -1;
    }
    resume();
  }
  function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶'; }

  $('play').onclick = play;
  $('all').onclick = () => {
    playAll = !playAll;
    $('all').classList.toggle('on', playAll);
    $('all').title = playAll ? 'stop at the end of each scene' : 'play every scene in order, without stopping';
  };
  $('speeds').innerHTML = SPEEDS.map(x =>
    `<button data-speed="${x}"${x === speed ? ' class="on"' : ''}>${x}×</button>`).join('');
  $('speeds').addEventListener('click', e => {
    const button = e.target.closest('button[data-speed]');
    if (!button) return;
    speed = +button.dataset.speed;
    [...$('speeds').children].forEach(b => b.classList.toggle('on', b === button));
    if (timer) resume();          // change pace without restarting the run
  });
  $('prev').onclick = () => { stop(); show(pass - 1); };
  $('next').onclick = () => { stop(); show(pass + 1); };
  $('scrub').oninput = e => { stop(); show(+e.target.value); };
  // Tabs: one panel at a time, so the column never runs off the bottom.
  // -- what it costs to run ------------------------------------------------
  // Everything below is arithmetic over two numbers the console already has:
  // how many cells are being watched, and how many calls a pass made. Land
  // areas are the published figures for the two countries the real scenes are
  // set in; nothing here is priced, because the tariff is the operator's to set
  // and inventing one would be the least credible number on the page.
  const COUNTRIES = [
    { name: 'Morocco', km2: 446550 },
    { name: 'Türkiye', km2: 783562 },
  ];
  const WATCH_S = 300;   // a national baseline does not need a 30-second pass
  const DEPLOY_KM = 10;  // the deployment cell; the city scenes are a 670 m zoom of one district

  function human(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + ' M';
    if (n >= 1e4) return Math.round(n / 1e3) + ' k';
    return n.toLocaleString('en-GB');
  }

  function drawScale(rec) {
    const sc = cur(), g = sc.grid;
    const cells = g.cells.length;
    const cellKm2 = (g.spacing_m / 1000) ** 2;
    const windowKm2 = cells * cellKm2;
    // The personal count comes from the evidence's own privacy line rather than
    // from guessing at endpoint names: it is the number the agent recorded, and
    // it is the number the card above the panel shows.
    const total = Object.values(rec.api_calls || {}).reduce((n, c) => n + c, 0);
    const personal = rec.privacy ? rec.privacy.personal : 0;
    const aggregate = total - personal;
    const cadence = 30;                                  // the scenes run every 30 s
    const perHour = aggregate * 3600 / cadence;

    const row = (n, k, w) => `<tr><td class="n">${n}</td><td class="k">${k}</td><td class="w">${w}</td></tr>`;
    let html = `<h4>This pass</h4><table>`
      + row(aggregate, 'aggregate', `2 per cell × ${cells} cells — sentinel SIMs, never a member of the public`)
      + row(personal, 'personal', personal
          ? 'only inside the declared footprint, only opt-in registry members'
          : 'the registry was not queried on this pass')
      + `</table>`;

    html += `<h4>This window, every ${cadence} s</h4><table>`
      + row(human(perHour), 'calls / hour', `${cells} cells of ${(g.spacing_m / 1000).toFixed(g.spacing_m < 2000 ? 2 : 0)} km over ${human(windowKm2)} km²`)
      + `</table>`;

    // Always quoted at the deployment cell, whatever this scene is drawn at: a
    // country is watched at 10 km, and extrapolating the city scenes' 670 m grid
    // to a national footprint would be arithmetic nobody would ever deploy.
    const deployKm2 = DEPLOY_KM * DEPLOY_KM;
    html += `<h4>A national watch, ${DEPLOY_KM} km cells</h4><table>`;
    COUNTRIES.forEach(c => {
      const n = Math.round(c.km2 / deployKm2);
      html += row(human(n), c.name, `cells over ${human(c.km2)} km² · ${human(n * 2 * 3600 / WATCH_S)} calls/h at a ${WATCH_S / 60}-minute watch`);
    });
    html += `</table>`;

    html += `<p>One sentinel SIM per cell: <b>${human(Math.round(COUNTRIES[1].km2 / deployKm2))} SIMs to watch Türkiye</b>, `
          + `not eighty-five million people. The bill scales with land area and cadence, and the buyer `
          + `chooses both — a national watch runs slow and tightens to ${cadence} s over one province the moment `
          + `a seismic alert or a first block of silence arrives.</p>`;
    html += `<p>The operator sells the impact feed as an Open Gateway product; the buyer is the civil-defence `
          + `agency or the municipality that already carries the duty of care. Detection touches no member of `
          + `the public, so there is no consent to buy — the personal line above is the only one that ever does, `
          + `and it is <b>zero on an ordinary morning</b>, on every pass, in the evidence file.</p>`;
    $('scale').innerHTML = html;
    $('s-pass').textContent = total.toLocaleString('en-GB');
    $('s-hour').textContent = human(perHour);
    $('s-sims').textContent = Math.round(COUNTRIES[1].km2 / deployKm2).toLocaleString('en-GB');
  }

  $('tabs').addEventListener('click', e => {
    const button = e.target.closest('button[data-pane]');
    if (!button) return;
    [...$('tabs').children].forEach(b => b.classList.toggle('on', b === button));
    ['zones', 'registry', 'brief', 'log', 'scale'].forEach(id => $(id).classList.toggle('on', id === button.dataset.pane));
  });

  // Keep the watched window overlapping the middle of the view, so the map can
  // be dragged freely but never thrown away off the edge.
  function clampPan() {
    if (!MAP) return;
    const g = cur().grid, { W, H, OX } = MAP;
    const w = g.cols * S * ZOOM, h = g.rows * S * ZOOM;
    TX = Math.min(W * 0.75 - OX * ZOOM, Math.max(W * 0.25 - (OX * ZOOM + w), TX));
    TY = Math.min(H * 0.75 - M * ZOOM, Math.max(H * 0.25 - (M * ZOOM + h), TY));
  }

  // Zoom about a point instead of about the middle: whatever is under (ax, ay)
  // stays under it, which is the difference between choosing what to look at and
  // being handed whatever the middle happened to be.
  function setZoom(next, ax, ay) {
    next = Math.max(0, Math.min(ZOOMS.length - 1, next));
    const z0 = ZOOM, z1 = ZOOMS[next];
    if (ax == null) { ax = (MAP ? MAP.W : 0) / 2; ay = (MAP ? MAP.H : 0) / 2; }
    TX = ax - (ax - TX) * (z1 / z0);
    TY = ay - (ay - TY) * (z1 / z0);
    zi = next; ZOOM = z1;
    if (zi === 0) { TX = 0; TY = 0; }        // 1× is always the whole picture
    clampPan();
    $('zlvl').textContent = ZOOMS[zi] + '×';
    $('zin').disabled = zi === ZOOMS.length - 1;
    $('zout').disabled = zi === 0;
    // No rebuild: the scene is transformed, the unscaled layers are re-laid
    // out, and the per-pass marks are refreshed at the new scale.
    applyView();
    drawLabels();
    drawChrome();
    drawMap(cur().records[pass]);
  }
  $('zin').onclick = () => setZoom(zi + 1);
  $('zout').onclick = () => setZoom(zi - 1);
  $('zlvl').onclick = () => setZoom(0);

  // Pointer position in the map's own units, whatever the element is scaled to.
  function atPointer(e) {
    const svg = $('grid'), r = svg.getBoundingClientRect();
    if (!MAP || !r.width) return [0, 0];
    return [(e.clientX - r.left) * MAP.W / r.width, (e.clientY - r.top) * MAP.H / r.height];
  }

  $('grid').addEventListener('wheel', e => {
    if (!MAP) return;
    e.preventDefault();
    const [ax, ay] = atPointer(e);
    setZoom(zi + (e.deltaY < 0 ? 1 : -1), ax, ay);
  }, { passive: false });

  $('grid').addEventListener('dblclick', e => {
    if (!MAP) return;
    const [ax, ay] = atPointer(e);
    setZoom(zi + 1, ax, ay);
  });

  // Dragging is a pan: the scene's transform follows the pointer and the chrome
  // is redrawn from a few dozen elements. Nothing is rebuilt, so there is
  // nothing to wait for when the reader lets go.
  (() => {
    const svg = $('grid');
    let from = null, pending = null;
    svg.addEventListener('pointerdown', e => {
      if (!MAP || e.button !== 0) return;
      // Measured once, here: reading layout after every transform write is
      // what makes a drag stutter, so the move handler never reads it at all.
      const r = svg.getBoundingClientRect();
      from = { x: e.clientX, y: e.clientY, tx: TX, ty: TY, k: r.width ? MAP.W / r.width : 1 };
      svg.classList.add('dragging');
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener('pointermove', e => {
      if (!from) return;
      pending = e;
      if (pending.raf) return;
      // One update per frame however fast the pointer reports.
      pending.raf = requestAnimationFrame(() => {
        const ev = pending; pending = null;
        if (!from) return;
        TX = from.tx + (ev.clientX - from.x) * from.k;
        TY = from.ty + (ev.clientY - from.y) * from.k;
        clampPan();
        applyView();
        drawChrome();
        drawFootprintLabel(cur().records[pass]);
      });
    });
    const end = e => {
      if (!from) return;
      const moved = Math.hypot(e.clientX - from.x, e.clientY - from.y);
      from = null;
      svg.classList.remove('dragging');
      drawLabels();                       // names may have slid under the margin
      if (moved < 3 && e.type === 'pointerup') { const [ax, ay] = atPointer(e); pickAt(ax, ay); }
    };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
  })();

  // -- the key to the map ----------------------------------------------------
  // Each swatch is an SVG using the map's own classes and patterns, so what is
  // shown here is exactly what is drawn there.
  function drawKey() {
    const sw = inner => `<div class="sym"><svg viewBox="0 0 58 34">${inner}</svg></div>`;
    const cell = cls => sw(`<rect x="6" y="3" width="46" height="28" fill="none" stroke="#2b3c4e"/><rect class="cell ${cls}" x="6" y="3" width="46" height="28"/>`);
    const row = (sym, name, text) => `<div class="row">${sym}<div><b>${name}</b><span>${text}</span></div></div>`;
    const streets = sw(`<path class="rd-local" d="M4 30 L22 10 L40 22 L56 6"/><path class="rd-major" d="M2 14 H56"/><path class="river" d="M6 4 C 20 18, 30 6, 54 30"/>`);
    const win = sw(`<rect class="ruler" x="0" y="4" width="58" height="12"/><path class="ruler-edge" d="M0 16 H58"/><path class="tick" d="M6 14 V16 M14 14 V16 M22 12 V16 M30 12 V16 M38 12 V16 M46 14 V16 M54 14 V16"/><text class="lbl" x="26" y="13" text-anchor="middle">1</text><text class="lbl" x="34" y="13" text-anchor="middle">2</text>`);
    const ruler = sw(`<rect class="ruler" x="4" y="4" width="50" height="12"/><path class="ruler-edge" d="M4 16 H54"/><path class="tick" d="M14 12 V16 M29 12 V16 M44 12 V16"/><text class="lbl" x="21.5" y="13" text-anchor="middle">6</text><text class="lbl" x="36.5" y="13" text-anchor="middle">7</text>`);
    const dot = sw(`<circle class="halo" cx="29" cy="17" r="13"/><circle class="dot" cx="29" cy="17" r="4"/>`);
    const fp = sw(`<path id="edge-key" class="fp" d="M8 6 H50 V28 H8 Z" style="stroke:var(--alert);stroke-width:3;fill:none"/>`);
    const cand = sw(`<path d="M8 6 H50 V28 H8 Z" style="stroke:var(--cand);stroke-width:2.5;stroke-dasharray:6 4;fill:none"/>`);
    const held = sw(`<path d="M8 6 H50 V28 H8 Z" style="stroke:var(--held);stroke-width:2;stroke-dasharray:4 4;fill:none"/>`);
    const mnt = sw(`<rect class="cell c-dark" x="6" y="3" width="46" height="28"/><rect class="mnt" x="12" y="7" width="34" height="20" rx="2"/>`);
    const iso = sw(`<path class="iso major" d="M2 28 C 16 4, 40 30, 56 8" stroke="#ffc600"/><path class="iso" d="M2 20 C 16 2, 38 24, 56 2" stroke="#ff9100"/>`);
    const rup = sw(`<path class="rupture" d="M6 26 L52 8"/>`);
    const geo = cur().geo;
    const levels = geo ? geo.contours.map(l => [l.mmi, l.color]) : [];

    let html = `<button class="close" title="close">×</button>`;
    html += `<h4>The network<small>one reading per cell, every 30 s</small></h4>`;
    html += row(cell('c-low'), 'Normal', 'The sentinel answers and the load is ordinary. Nothing is drawn \u2014 the street map showing through is the sign that all is well.');
    html += row(cell('c-medium'), 'Medium load', 'Sparse yellow hatch. Congestion Insights reports the cell at Medium.');
    html += row(cell('c-high'), 'High congestion', 'Dense orange crosshatch. The cell is saturated: everyone in reach is calling at once. Around a silent block this is the \u201chot ring\u201d.');
    html += row(cell('c-dark'), 'Sentinel unreachable', 'Solid black. Device Reachability says the cell\u2019s sentinel does not answer. The streets beneath are dimmed, not removed.');
    html += `<h4>The agent<small>what it claims, and what it refuses</small></h4>`;
    html += row(fp, 'Declared footprint', 'Solid red outline around a contiguous block of silent cells the agent has declared an impact. Its confidence and area are on the red label.');
    html += row(cand, 'Candidate', 'Yellow dashed outline. A block that looks like an impact, held for one more pass before anything is declared.');
    html += row(held, 'Explained, held', 'Grey dashed outline. Silence the agent can account for: a single-cell fault, a maintenance ticket, or a block where silence is the local normal. No alert.');
    html += row(mnt, 'Maintenance ticket', 'Dotted inset square. The operator\u2019s calendar says this cell is under planned work, so its silence is expected.');
    html += `<h4>People<small>only inside a declared footprint, only opt-in</small></h4>`;
    html += row(dot, 'Last-seen position', 'White dot: where the network last saw an unreachable opt-in registry member. The dashed red ring is that position\u2019s uncertainty radius in metres, from Location Retrieval.');
    html += `<h4>The measured event<small>real events, with \u201cMeasured intensity\u201d on</small></h4>`;
    html += row(iso, 'Isoseismals', 'USGS ShakeMap contours of estimated shaking intensity (MMI), in USGS\u2019s own colours; thicker lines are whole steps. A declared footprint should sit inside the VIII line \u2014 that is the check.');
    if (levels.length) {
      html += `<div class="iso-scale">${levels.map(([m, c]) => `<i style="background:${c}" title="MMI ${m}"></i>`).join('')}</div>`;
      html += `<div class="iso-lbls"><span>MMI ${levels[0][0]} \u00b7 ${mmiWord(levels[0][0])}</span><span>MMI ${levels[levels.length - 1][0]} \u00b7 ${mmiWord(levels[levels.length - 1][0])}</span></div>`;
    }
    html += row(rup, 'Fault rupture', 'White dashed line: the surface projection of the finite fault from the same ShakeMap. The reason a footprint is a band and not a circle.');
    html += `<h4>The map</h4>`;
    html += row(streets, 'Streets and water', 'Grey-blue lines are roads, thicker for the trunk network; blue lines are rivers and wadis; blue fills are lakes and reservoirs. OpenStreetMap.');
    html += row(win, 'Monitored window', 'The sentinel grid watches the span the margin letters and numbers cover; the short unlettered ticks beyond it are the same pitch, with no cells. The rest of the map is context.');
    html += row(ruler, 'Grid reference', 'The ruled margin along the top and the left names rows A\u2013J and columns 1\u201310, so a cell is F6. Click any cell for what the network, the agent and the survey say about it.');
    $('mapkey').innerHTML = html;
    $('mapkey').querySelector('.close').onclick = () => toggleKey(false);
  }

  function mmiWord(m) {
    const w = { 4: 'light', 5: 'moderate', 6: 'strong', 7: 'very strong', 8: 'severe', 9: 'violent', 10: 'extreme' };
    return w[Math.round(m)] || '';
  }

  function toggleKey(force) {
    const on = force == null ? $('mapkey').classList.contains('hidden') : force;
    if (on) drawKey();
    $('mapkey').classList.toggle('hidden', !on);
    $('keybtn').classList.toggle('on', on);
  }
  $('keybtn').onclick = () => toggleKey();

  $('detail').onclick = () => {
    detail = !detail;
    $('detail').classList.toggle('on', detail);
    $('grid').classList.toggle('detail', detail);
    MAP = null;
    drawMap(cur().records[pass]);
  };

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape' && PICK) { PICK = null; const r = cur().records[pass]; drawInspect(r); drawZones(r); drawRegistry(r); return; }
    if (e.code === 'Space') { e.preventDefault(); play(); }
    else if (e.key === 'ArrowRight') { stop(); show(pass + 1); }
    else if (e.key === 'ArrowLeft') { stop(); show(pass - 1); }
    else if (e.key >= '1' && e.key <= String(DATA.scenes.length)) setScene(+e.key - 1);
  });

  // Deep link: replay.html#quake/7 opens a scene at a pass — for screenshots and slides.
  function fromHash() {
    const m = location.hash.match(/^#([a-z]+)(?:\/(\d+))?$/);
    const idx = m ? DATA.scenes.findIndex(s => s.name === m[1]) : -1;
    setScene(idx >= 0 ? idx : Math.max(0, DATA.scenes.findIndex(s => s.name === 'quake')));
    if (m && m[2]) show(+m[2]);
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    path = build_console()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
