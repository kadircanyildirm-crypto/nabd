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
    "maras": ("6 February 2023", "the real event — measured ground motion decides which cells go silent"),
}


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


def region_basemap() -> dict | None:
    """The same street data as the city scenes, thinned for a 150 km view.

    Drawing the real-event scene from Natural Earth while the others came from
    OpenStreetMap made it the odd one out — a sparser map for the one scene that
    matters most. Both windows come from the same source now.
    """
    path = Path(__file__).resolve().parent / "data" / "basemap-region.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def mid_basemap() -> dict | None:
    """The road network between the towns, for when the region is zoomed in.

    At the full 150 km view only the trunk roads are worth drawing. Zooming in
    should reveal something, not just magnify what was already there, so this is
    the tier underneath: the tertiary and unclassified network across the
    monitored window.
    """
    path = Path(__file__).resolve().parent / "data" / "basemap-mid.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def city_basemap() -> dict | None:
    """The street network, for the scenes that watch a single city.

    The regional extract carries two roads and one dot across a 6.7 km square,
    which is not a map. This is OpenStreetMap, delta-encoded, and it is what makes
    the four city-scale scenes legible as a place.
    """
    path = Path(__file__).resolve().parent / "data" / "basemap-city.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def geometry_for(name: str) -> dict | None:
    """The measured event's own geometry, for the one scene that has one.

    Four scenes are worlds we drew, and there is nothing real to lay under them.
    The fifth is 6 February 2023, and for that one the published isoseismals and
    the finite-fault rupture go on the map — so the footprint Nabd declares can
    be checked against the shaking that caused it, by eye, in a second.
    """
    if name != "maras":
        return None
    path = Path(__file__).resolve().parent / "data" / "shakemap-us6000jllz-geo.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"contours": raw["contours"], "rupture": raw["rupture"], "source": raw["source"]}


def scene_payload(name: str) -> dict:
    scenario = build(name)
    grid = scenario.world.grid
    title, subtitle = TITLES[name]
    return {
        "geo": geometry_for(name),
        "city": grid.spacing_m <= 2000,
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
        "records": load(name),
    }


def build_console(names: tuple[str, ...] = tuple(BUILDERS), out: Path = OUT) -> Path:
    # The base maps are the same for every scene, and the city one is the largest
    # thing in the file. Inlining it per scene made the console five times heavier
    # than it needed to be, so it is carried once and referenced by a flag.
    payload = {
        "scenes": [scene_payload(n) for n in names],
        "base": basemap(),
        "cityBase": city_basemap(),
        "regionBase": region_basemap(),
        "midBase": mid_basemap(),
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
  nav { display: flex; gap: 6px; }
  nav button { background: transparent; color: var(--muted); border: 1px solid var(--line); border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; }
  nav button.on { color: var(--text); border-color: var(--high); background: #1a2330; }
  .clock { font-family: var(--mono); font-size: 22px; font-variant-numeric: tabular-nums; text-align: right; line-height: 1.1; }
  .clock small { display: block; font-size: 11px; color: var(--muted); font-family: inherit; }
  .controls { display: flex; align-items: center; gap: 8px; }
  .controls button { background: #1a2330; color: var(--text); border: 1px solid var(--line); border-radius: 6px; width: 34px; height: 32px; cursor: pointer; font-size: 14px; }
  .controls input[type=range] { width: 220px; accent-color: var(--high); }
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
  .beat { min-height: 44px; padding: 10px 12px; border-left: 3px solid var(--high); background: var(--panel-2); border-radius: 6px; color: var(--text); }
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
  /* The readings are a field, not tiles: each cell eases into its new colour and
     the layer is softened, so a pass reads as the network changing rather than a
     chessboard being repainted. */
  .cell { stroke: none; transition: fill .55s cubic-bezier(.4,0,.2,1); }
  .c-low { fill: #2f6d9e33; } .c-medium { fill: #b8892242; } .c-high { fill: #e08a2e5c; }
  .c-unmon { fill: #141a2226; }
  .c-dark { fill: #01030699; }
  .c-clear { fill: #00000000; }
  .fpfill { fill: var(--alert); fill-opacity: 0; transition: fill-opacity .55s cubic-bezier(.4,0,.2,1); }
  .fpfill.on { fill-opacity: .10; }
  .fpfill.cand { fill: var(--cand); fill-opacity: .12; }
  .fpfill.held { fill: var(--held); fill-opacity: .09; }
  .dot, .halo { transition: opacity .45s ease; }
  .scale { stroke: #7f8f9f; stroke-width: 1.4; fill: none; }
  .scaletxt, .compass { font-family: var(--mono); font-size: 10px; fill: #9fb3c6; }
  .compass { font-size: 13px; font-weight: 700; }
  .fp { fill: none; stroke: var(--alert); stroke-width: 3; pointer-events: none; }
  .cand { fill: none; stroke: var(--cand); stroke-width: 2.5; stroke-dasharray: 5 4; pointer-events: none; }
  .held { fill: none; stroke: var(--held); stroke-width: 2; stroke-dasharray: 3 4; pointer-events: none; }
  .mnt { fill: none; stroke: var(--held); stroke-width: 1; stroke-dasharray: 2 3; pointer-events: none; }
  .lbl { fill: var(--dim); font-family: var(--mono); font-size: 10px; }
  .fplabel { fill: var(--alert); font-family: var(--mono); font-size: 11px; font-weight: 700; }
  .dot { fill: #fff; stroke: var(--alert); stroke-width: 1.5; }
  .halo { fill: var(--alert); fill-opacity: .07; stroke: var(--alert); stroke-opacity: .3; stroke-width: 1; }
  .legend { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; color: var(--muted); font-size: 12px; }
  /* The measured event is a second reading of the same map, not the map itself. */
  /* Map controls belong on the map, not in the key underneath it. */
  .mapctl { position: absolute; top: 8px; right: 8px; z-index: 2; display: flex; align-items: center;
            gap: 8px; background: #0b1017cc; border-radius: 8px; padding: 4px; }
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
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -2px; margin-right: 6px; }
  /* The column is exactly as tall as the screen. The verdict and the brief are
     always visible; everything else lives behind a tab, so a reader is told what
     is there rather than left to guess that scrolling would reveal it. */
  /* Two things, not four. The verdict is what the room is looking at; everything
     else — the zones, the registry, the brief, the log — is one tab away. The
     brief used to sit in its own panel repeating the signals word for word,
     which is most of why this column looked busy. */
  aside { display: grid; grid-template-rows: minmax(0, auto) minmax(0, 1fr); gap: 10px; min-height: 0; }
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
  .signals { margin: 10px 0 0; padding: 0; list-style: none; border-top: 1px solid var(--line); }
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
  footer { display: flex; flex-wrap: wrap; gap: 18px; padding: 10px 20px 18px; color: var(--muted); font-family: var(--mono); font-size: 12px; }
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
  </div>
</header>
<main>
  <section class="map">
    <div id="beat" class="beat empty"></div>
    <div class="mapview">
      <svg id="grid" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="mapctl">
        <button id="detail" class="hidden" title="measured intensity contours and the fault rupture">Measured intensity</button>
        <span class="zoomer"><button id="zout" title="zoom out">−</button><button id="zlvl" title="back to the whole picture">1×</button><button id="zin" title="zoom in — drag the map to move, or roll the wheel over the spot you want">+</button></span>
      </div>
    </div>
    <div class="legend">
      <span><i style="background:var(--low)"></i>Low</span>
      <span><i style="background:var(--medium)"></i>Medium</span>
      <span><i style="background:var(--high)"></i>High congestion</span>
      <span><i style="background:var(--dark);border:1px solid #3a1a1a"></i>Sentinel unreachable</span>
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
      </div>
      <div class="panes">
        <div id="zones" class="pane on"></div>
        <div id="registry" class="pane"></div>
        <div id="brief" class="pane brief empty"></div>
        <div id="log" class="pane log"></div>
      </div>
    </div>
  </aside>
</main>
<footer>
  <span>CAMARA this pass <b id="calls-pass">0</b></span>
  <span>to date <b id="calls-total">0</b></span>
  <span>backend <b>offline simulator</b></span>
  <span>evidence <b id="evidence"></b></span>
  <span><kbd>space</kbd> play · <kbd>←</kbd><kbd>→</kbd> step · <kbd>1</kbd>–<kbd>5</kbd> scene</span>
  <span class="credit">map © OpenStreetMap contributors (ODbL) · Natural Earth · GeoNames (CC BY) · intensity USGS ShakeMap us6000jllz</span>
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
  DATA.scenes.forEach((sc, i) => {
    const b = document.createElement('button');
    b.textContent = `${i + 1} · ${sc.title}`;
    b.title = sc.subtitle;
    b.onclick = () => setScene(i);
    nav.appendChild(b);
  });

  function setScene(i) {
    stop();
    scene = i; pass = 0; MAP = null;
    [...nav.children].forEach((b, k) => b.classList.toggle('on', k === i));
    $('scrub').max = cur().records.length - 1;
    $('evidence').textContent = `nabd-scene-${cur().name}.jsonl`;
    $('detail').classList.toggle('hidden', !cur().geo);
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
  const zx = x => x * ZOOM + TX;
  const zy = y => y * ZOOM + TY;

  function project(lat, lon, g) {
    const a = g.cells[0], b = g.cells[1], c = g.cells[g.cols];
    const dlon = b.lon - a.lon, dlat = c.lat - a.lat; // dlat is negative (south)
    return [zx(ORIGIN_X + ((lon - a.lon) / dlon + 0.5) * S),
            zy(M + ((lat - a.lat) / dlat + 0.5) * S)];
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
    const SZ = S * ZOOM;
    const line = pts => pts.map((p, i) => {
      const [x, y] = project(p[1], p[0], g);
      return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }).join('');
    const out = [];

    out.push(`<defs>`
      + `<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">`
      + `<stop offset="0" stop-color="#0c1420"/><stop offset="1" stop-color="#080d14"/></linearGradient>`
      + `<clipPath id="viewclip"><rect x="0" y="0" width="${W.toFixed(1)}" height="${H}"/></clipPath>`
      + `<clipPath id="winclip"><rect x="${zx(x0).toFixed(1)}" y="${zy(y0).toFixed(1)}" width="${(w * ZOOM).toFixed(1)}" height="${(h * ZOOM).toFixed(1)}"/></clipPath>`
      + `<filter id="soften" x="-10%" y="-10%" width="120%" height="120%">`
      + `<feGaussianBlur stdDeviation="${(SZ * 0.045).toFixed(2)}"/></filter>`
      + `<filter id="glow" x="-30%" y="-30%" width="160%" height="160%">`
      + `<feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/>`
      + `<feMergeNode in="SourceGraphic"/></feMerge></filter>`
      + `</defs>`);
    out.push(`<rect class="ground" x="0" y="0" width="${W.toFixed(1)}" height="${H}"/>`);

    // -- the region, or the city ---------------------------------------------
    const geo = detail ? cur().geo : null;
    const isCity = !!cur().city;          // the scene watches one city, not a region
    const base = DATA.base;
    out.push('<g clip-path="url(#viewclip)">');
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
    if (isCity) {
      const city = DATA.cityBase;
      if (city) city.water.forEach(l => out.push(`<path class="water" d="${line(decode(l, city.scale))}Z"/>`));
    } else {
      const region = DATA.regionBase;
      if (region) region.water.forEach(l => out.push(`<path class="water" d="${line(decode(l, region.scale))}Z"/>`));
    }
    out.push('</g>');

    const field = (id, cls) => {
      out.push(`<g clip-path="url(#winclip)" filter="url(#soften)"><g id="${id}">`);
      g.cells.forEach(c => out.push(
        `<rect class="cell ${cls}" data-k="${c.row * g.cols + c.col}" x="${zx(OX + c.col * S).toFixed(1)}" y="${zy(M + c.row * S).toFixed(1)}" width="${SZ.toFixed(1)}" height="${SZ.toFixed(1)}"><title>${c.id} · ${c.lat.toFixed(4)}N ${c.lon.toFixed(4)}E</title></rect>`));
      out.push('</g></g>');
    };

    // -- how loaded the network is: a wash under the streets it describes ----
    field('cells', 'c-unmon');

    // -- the streets, over the wash -----------------------------------------
    out.push('<g clip-path="url(#viewclip)">');
    if (isCity) {
      const city = DATA.cityBase;
      layer(city, 'roads.local', 'rd-local');
      layer(city, 'roads.minor', 'rd-minor');
      layer(city, 'roads.major', 'rd-major');
      layer(city, 'streams', 'river');
      layer(city, 'rail', 'rail');
    } else {
      const region = DATA.regionBase, mid = DATA.midBase;
      // The city scenes look the way they do because the ground under them is
      // dense. The region gets the same treatment from the start: the whole
      // between-towns network, not just the trunk roads, so the map has texture
      // to read the footprint against. Zooming in then adds the streets.
      layer(DATA.cityBase, 'roads.local', 'rd-local');
      layer(DATA.cityBase, 'roads.minor', 'rd-minor');
      layer(mid, 'roads.minor', 'rd-local');
      layer(region, 'roads.major', 'rd-major');
      layer(region, 'streams', 'river');
    }
    out.push('</g>');

    // -- what has gone dark, over everything: it is an absence, not a tint ---
    field('dark', 'c-clear');

    out.push('<g clip-path="url(#winclip)" filter="url(#soften)"><g id="fpfills">');
    g.cells.forEach(c => out.push(
      `<rect class="fpfill" data-id="${c.id}" x="${zx(OX + c.col * S).toFixed(1)}" y="${zy(M + c.row * S).toFixed(1)}" width="${SZ.toFixed(1)}" height="${SZ.toFixed(1)}"/>`));
    out.push('</g></g>');
    out.push('<g id="mnt" clip-path="url(#winclip)"></g>');

    // -- the measured event --------------------------------------------------
    if (geo) {
      out.push('<g clip-path="url(#viewclip)">');
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
    out.push('<g id="dots"></g>');

    // -- place names, on top so they stay readable ---------------------------
    const places = (isCity ? DATA.cityBase : DATA.regionBase);
    if (places) {
      out.push('<g clip-path="url(#viewclip)">');
      // Places are ranked, so when two labels want the same spot the more
      // important one keeps it and the other loses its text but keeps its dot.
      const placed = [];
      places.places.forEach(t => {
        const [x, y] = project(t.lat, t.lon, g);
        if (x < 4 || x > W - 4 || y < 4 || y > H - 4) return;
        const big = t.rank <= 2;
        out.push(`<circle class="town${big ? ' major' : ''}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${big ? 3.4 : 1.8}"/>`);
        const wide = t.name.length * (big ? 6.6 : 4.6) + 10, tall = big ? 13 : 10;
        if (placed.some(p => Math.abs(p.x - x) < (p.w + wide) / 2 && Math.abs(p.y - y) < (p.h + tall) / 2)) return;
        placed.push({ x, y, w: wide, h: tall });
        out.push(`<text class="placelbl${big ? ' big' : ''}" x="${(x + (big ? 7 : 4)).toFixed(1)}" y="${(y + 3).toFixed(1)}">${t.name}</text>`);
      });
      out.push('</g>');
    }

    // -- the monitored window, its labels, and the furniture of a map --------
    out.push(`<rect x="${zx(x0).toFixed(1)}" y="${zy(y0).toFixed(1)}" width="${(w * ZOOM).toFixed(1)}" height="${(h * ZOOM).toFixed(1)}" fill="none" stroke="#54708a" stroke-width="1.2" stroke-dasharray="5 4" opacity=".75"/>`);
    // Row and column letters ride the edge of the view, not the edge of the
    // window: zoomed in, the window's own edge is off-screen, and a reader still
    // needs to know that this is F6.
    const ly = Math.min(Math.max(zy(M) - 8, 11), H - 8);
    // Pinned to the left edge, the letters have to read outwards instead of in.
    const pinned = zx(OX) - 8 < 18;
    const lx = pinned ? 6 : Math.min(zx(OX) - 8, W - 6);
    for (let c = 0; c < g.cols; c++) {
      const x = zx(OX + c * S + S / 2);
      if (x > 10 && x < W - 10) out.push(`<text class="lbl" x="${x.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle">${c + 1}</text>`);
    }
    for (let r = 0; r < g.rows; r++) {
      const y = zy(M + r * S + S / 2);
      if (y > 14 && y < H - 6) out.push(`<text class="lbl" x="${lx.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${pinned ? 'start' : 'end'}">${'ABCDEFGHIJKLMNOPQRST'[r]}</text>`);
    }

    // A scale bar keeps its length and changes its number, the way a paper map
    // does. Pick the roundest distance near the bar we already draw at 1×.
    const km = g.spacing_m / 1000;
    const LADDER = [.1, .2, .25, .5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 500];
    const want = (km >= 5 ? 50 : 2) / ZOOM;
    const span = LADDER.reduce((a, b) => Math.abs(b - want) < Math.abs(a - want) ? b : a);
    const bar = (span / km) * SZ, bx = 14, by = H - 14;
    out.push(`<path class="scale" d="M${bx} ${by - 5}V${by}H${(bx + bar).toFixed(1)}V${by - 5}"/>`);
    out.push(`<text class="scaletxt" x="${bx}" y="${by - 9}">${span < 1 ? Math.round(span * 1000) + ' m' : span + ' km'}</text>`);
    out.push(`<text class="compass" x="${(W - 18).toFixed(1)}" y="${M + 4}" text-anchor="middle">N</text>`);
    out.push(`<path class="scale" d="M${(W - 18).toFixed(1)} ${M + 8}V${M + 24}M${(W - 22).toFixed(1)} ${M + 13}L${(W - 18).toFixed(1)} ${M + 8}L${(W - 14).toFixed(1)} ${M + 13}"/>`);

    out.push(`<g id="fplabel"></g>`);
    svg.innerHTML = out.join('');
    MAP = { scene: cur().name, w: Math.round(svg.getBoundingClientRect().width), OX, W, H,
            cells: [...svg.querySelectorAll('#cells rect')],
            dark: [...svg.querySelectorAll('#dark rect')],
            fills: new Map([...svg.querySelectorAll('#fpfills rect')].map(r => [r.dataset.id, r])) };
  }

  function drawMap(rec) {
    const svg = $('grid'), g = cur().grid;
    const width = Math.round(svg.getBoundingClientRect().width);
    if (!MAP || MAP.scene !== cur().name || Math.abs(MAP.w - width) > 8) buildMap();
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
        const x = zx(OX + cell.col * S), y = zy(M + cell.row * S);
        const sz = S * ZOOM;
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
        mnt.push(`<rect class="mnt" x="${(zx(OX + cell.col * S) + 3).toFixed(1)}" y="${(zy(M + cell.row * S) + 3).toFixed(1)}" width="${(S * ZOOM - 6).toFixed(1)}" height="${(S * ZOOM - 6).toFixed(1)}" rx="2"/>`);
      });
    });
    $('mnt').innerHTML = mnt.join('');

    const dots = [];
    if (rec.triage) rec.triage.top.forEach(p => {
      if (!p.last_seen) return;
      const [x, y] = project(p.last_seen.lat, p.last_seen.lon, g);
      const r = (p.last_seen.radius_m / g.spacing_m) * S * ZOOM;   // a real distance, so it scales
      dots.push(`<circle class="halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"/>`);
      dots.push(`<circle class="dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"><title>${p.person} · ${p.class} · ${p.cell}</title></circle>`);
    });
    $('dots').innerHTML = dots.join('');

    let label = '';
    if (cls === 'on' && rec.cells.length) {
      const cells = rec.cells.map(id => g.cells.find(c => c.id === id));
      const bottom = Math.max(...cells.map(c => c.row)), left = Math.min(...cells.map(c => c.col));
      const text = `FOOTPRINT · ${rec.confidence || ''} · ${(rec.cells.length * (g.spacing_m / 1000) ** 2).toFixed(1)} km²`;
      const bw = text.length * 6.8 + 12;
      const bx = Math.max(4, Math.min(zx(OX + left * S), W - bw - 4));
      const by = Math.min(zy(M + (bottom + 1) * S) + 6, H - 20);
      label = `<rect x="${bx.toFixed(1)}" y="${by}" width="${bw.toFixed(1)}" height="18" rx="4" fill="#0b1017" stroke="var(--alert)" stroke-width="1"/>`
            + `<text class="fplabel" x="${(bx + 6).toFixed(1)}" y="${by + 13}">${text}</text>`;
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
      html += `<ul class="signals">${rec.signals.map(sig => {
        const at = sig.indexOf(':');
        const body = at > 0 && at < 34
          ? `<b>${esc(sig.slice(0, at))}</b>${esc(sig.slice(at))}`
          : esc(sig);
        return `<li class="${signalFired(sig) ? 'yes' : 'no'}">${body}</li>`;
      }).join('')}</ul>`;
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
      rows.map(([cell, n]) => `<tr><td class="mono">${cell}</td><td><span class="bar" style="width:${Math.round(n / max * 120)}px"></span>${n}</td></tr>`).join('') + '</table>';
  }

  function drawRegistry(rec) {
    const el = $('registry');
    if (!rec.triage) { el.innerHTML = '<div class="empty">Not queried. No personal device is touched outside a declared footprint.</div>'; return; }
    if (!rec.triage.top.length) { el.innerHTML = '<div class="empty">Everyone registered inside the footprint is reachable.</div>'; return; }
    el.innerHTML = `<table><tr><th class="mono">id</th><th>class</th><th class="mono">cell</th><th>last seen</th></tr>` +
      rec.triage.top.map(p => `<tr><td class="mono">${p.person}</td><td>${p.class}</td><td class="mono">${p.cell}</td><td>${p.last_seen ? `${age(p.last_seen.age_s)} ago · ±${p.last_seen.radius_m} m` : '–'}</td></tr>`).join('') + '</table>';
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
    $('calls-pass').textContent = rec.api_calls.length;
    $('calls-total').textContent = cur().records.slice(0, pass + 1).reduce((n, r) => n + r.api_calls.length, 0);
  }

  function show(i) {
    const recs = cur().records;
    pass = Math.max(0, Math.min(recs.length - 1, i));
    const rec = recs[pass];
    $('scrub').value = pass;
    $('clock').textContent = clock(rec.t);
    const sc = cur();
    $('since').textContent = sc.onset != null && rec.t >= sc.onset ? `+${Math.round(rec.t - sc.onset)}s since onset` : `pass ${pass + 1} / ${recs.length}`;
    drawBeat(rec); drawMap(rec); drawStatus(rec); drawBrief(rec); drawZones(rec); drawRegistry(rec); drawLog(); drawFooter(rec);
    // Say how much is behind each tab, so the count is visible without opening it.
    const counts = { zones: (rec.triage ? rec.triage.top.length : 0), registry: (rec.triage ? rec.triage.unreachable : 0), brief: null, log: null };
    const names = { zones: 'Priority zones', registry: 'Registry', brief: 'Brief', log: 'Log' };
    [...$('tabs').children].forEach(b => {
      const n = counts[b.dataset.pane];
      b.textContent = n ? `${names[b.dataset.pane]} · ${n}` : names[b.dataset.pane];
    });
  }

  // -- playback ---------------------------------------------------------------
  function play() {
    if (timer) return stop();
    if (pass >= cur().records.length - 1) pass = -1;
    $('play').textContent = '❚❚';
    timer = setInterval(() => { if (pass >= cur().records.length - 1) return stop(); show(pass + 1); }, 900);
  }
  function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶'; }

  $('play').onclick = play;
  $('prev').onclick = () => { stop(); show(pass - 1); };
  $('next').onclick = () => { stop(); show(pass + 1); };
  $('scrub').oninput = e => { stop(); show(+e.target.value); };
  // Tabs: one panel at a time, so the column never runs off the bottom.
  $('tabs').addEventListener('click', e => {
    const button = e.target.closest('button[data-pane]');
    if (!button) return;
    [...$('tabs').children].forEach(b => b.classList.toggle('on', b === button));
    ['zones', 'registry', 'brief', 'log'].forEach(id => $(id).classList.toggle('on', id === button.dataset.pane));
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
    MAP = null;
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

  // Dragging moves the element with a CSS transform, which costs nothing, and
  // the map is rebuilt once at the end — a rebuild per frame would drop the
  // playback to a slideshow on a map with eight thousand paths in it.
  (() => {
    const svg = $('grid');
    let from = null;
    svg.addEventListener('pointerdown', e => {
      if (!MAP || e.button !== 0) return;
      from = { x: e.clientX, y: e.clientY };
      svg.classList.add('dragging');
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener('pointermove', e => {
      if (!from) return;
      svg.style.transform = `translate(${e.clientX - from.x}px, ${e.clientY - from.y}px)`;
    });
    const end = e => {
      if (!from) return;
      const r = svg.getBoundingClientRect();
      const k = r.width ? MAP.W / r.width : 1;
      const dx = e.clientX - from.x, dy = e.clientY - from.y;
      from = null;
      svg.classList.remove('dragging');
      svg.style.transform = '';
      if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;   // a click, not a drag
      TX += dx * k; TY += dy * k;
      clampPan();
      MAP = null;
      drawMap(cur().records[pass]);
    };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
  })();

  $('detail').onclick = () => {
    detail = !detail;
    $('detail').classList.toggle('on', detail);
    MAP = null;
    drawMap(cur().records[pass]);
  };

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
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
