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
    payload = {"scenes": [scene_payload(n) for n in names]}
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
  main { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(380px, 520px); gap: 16px; padding: 16px 20px; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  .map { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  .beat { min-height: 44px; padding: 10px 12px; border-left: 3px solid var(--high); background: var(--panel-2); border-radius: 6px; color: var(--text); }
  .beat.empty { border-left-color: var(--line); color: var(--dim); }
  svg { width: 100%; height: auto; display: block; }
  /* The measured event, drawn over the cells rather than under them: the cells
     are opaque, and the point is to see both at once. */
  .iso { fill: none; stroke-width: 1.7; opacity: .8; stroke-linejoin: round; stroke-linecap: round; }
  .iso.major { stroke-width: 2.6; opacity: .95; }
  .rupture { fill: none; stroke: #ffffff; stroke-width: 2.4; stroke-dasharray: 6 4; opacity: .9; }
  .isokey { font-family: var(--mono); font-size: 9.5px; fill: #0b1017; font-weight: 700; }
  .cell { stroke: #0b1017; stroke-width: 1.5; }
  .c-low { fill: var(--low); } .c-medium { fill: var(--medium); } .c-high { fill: var(--high); } .c-unmon { fill: var(--unmon); }
  .c-dark { fill: var(--dark); stroke: #3a1a1a; }
  .fp { fill: none; stroke: var(--alert); stroke-width: 3; pointer-events: none; }
  .cand { fill: none; stroke: var(--cand); stroke-width: 2.5; stroke-dasharray: 5 4; pointer-events: none; }
  .held { fill: none; stroke: var(--held); stroke-width: 2; stroke-dasharray: 3 4; pointer-events: none; }
  .mnt { fill: none; stroke: var(--held); stroke-width: 1; stroke-dasharray: 2 3; pointer-events: none; }
  .lbl { fill: var(--dim); font-family: var(--mono); font-size: 10px; }
  .fplabel { fill: var(--alert); font-family: var(--mono); font-size: 11px; font-weight: 700; }
  .dot { fill: #fff; stroke: var(--alert); stroke-width: 1.5; }
  .halo { fill: var(--alert); fill-opacity: .07; stroke: var(--alert); stroke-opacity: .3; stroke-width: 1; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-size: 12px; }
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -2px; margin-right: 6px; }
  aside { display: flex; flex-direction: column; gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
  .card h3 { margin: 0 0 8px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  .status { border-left: 4px solid var(--line); }
  .status.k-DECLARE, .status.k-UPDATE, .status.k-SUSTAIN { border-left-color: var(--alert); }
  .status.k-CANDIDATE { border-left-color: var(--cand); }
  .status.k-ABSTAIN { border-left-color: var(--held); }
  .status.k-CLEAR { border-left-color: var(--ok); }
  .headline { font-size: 17px; font-weight: 600; margin: 0 0 6px; }
  .headline .kind { font-family: var(--mono); font-size: 12px; padding: 2px 7px; border-radius: 4px; background: #1a2330; color: var(--muted); margin-right: 8px; vertical-align: 2px; }
  .chip { display: inline-block; font-family: var(--mono); font-size: 11px; padding: 2px 7px; border-radius: 4px; margin-right: 6px; background: #1a2330; color: var(--text); }
  .chip.HIGH { background: #3a1613; color: #ffb4ad; } .chip.MEDIUM { background: #3a2f10; color: #ffd98a; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }
  .stat { background: var(--panel-2); border-radius: 6px; padding: 8px 10px; }
  .stat b { display: block; font-family: var(--mono); font-size: 20px; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 11px; color: var(--muted); }
  .signals { margin: 8px 0 0; padding-left: 16px; color: var(--muted); font-size: 12.5px; }
  .signals li { margin: 2px 0; }
  /* The privacy boundary, stated on every pass rather than argued once. */
  .privacy { margin-top: 8px; padding: 6px 9px; border-radius: 6px; font-size: 12px; line-height: 1.45;
             border: 1px solid var(--line); display: flex; gap: 7px; align-items: baseline; }
  .privacy b { font-family: var(--mono); font-size: 11px; letter-spacing: .03em; white-space: nowrap; }
  .privacy.shut { background: #10231a; border-color: #1d3d2c; color: #8fe0b0; }
  .privacy.open { background: #2a2413; border-color: #4a3f1c; color: #ffd98a; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-weight: 500; font-size: 11px; padding: 2px 6px 6px 0; }
  td { padding: 4px 6px 4px 0; border-top: 1px solid var(--line); vertical-align: top; }
  td.mono, th.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
  .bar { height: 6px; background: var(--alert); border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 6px; }
  .empty { color: var(--dim); font-size: 13px; }
  .log { max-height: 340px; overflow: auto; }
  .entry { padding: 8px 0; border-top: 1px solid var(--line); }
  .entry:first-child { border-top: 0; }
  .entry .when { font-family: var(--mono); color: var(--muted); font-size: 12px; margin-right: 8px; }
  .entry .g { font-family: var(--mono); margin-right: 6px; }
  .entry.k-DECLARE .g, .entry.k-UPDATE .g { color: var(--alert); } .entry.k-CANDIDATE .g { color: var(--cand); } .entry.k-ABSTAIN .g { color: var(--held); } .entry.k-CLEAR .g { color: var(--ok); }
  .entry ul { margin: 4px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; }
  .brief { font-size: 13.5px; line-height: 1.5; }
  .brief.empty { color: var(--dim); }
  footer { display: flex; flex-wrap: wrap; gap: 18px; padding: 10px 20px 18px; color: var(--muted); font-family: var(--mono); font-size: 12px; }
  footer b { color: var(--text); font-weight: 600; }
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
    <svg id="grid" xmlns="http://www.w3.org/2000/svg"></svg>
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
    <div class="card"><h3>Command-centre brief</h3><div id="brief" class="brief empty"></div></div>
    <div class="card"><h3>Priority zones</h3><div id="zones"></div></div>
    <div class="card"><h3>Opt-in registry · unreachable</h3><div id="registry"></div></div>
    <div class="card"><h3>Agent log</h3><div id="log" class="log"></div></div>
  </aside>
</main>
<footer>
  <span>CAMARA this pass <b id="calls-pass">0</b></span>
  <span>to date <b id="calls-total">0</b></span>
  <span>backend <b>offline simulator</b></span>
  <span>evidence <b id="evidence"></b></span>
  <span><kbd>space</kbd> play · <kbd>←</kbd><kbd>→</kbd> step · <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> scene</span>
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
    scene = i; pass = 0;
    [...nav.children].forEach((b, k) => b.classList.toggle('on', k === i));
    $('scrub').max = cur().records.length - 1;
    $('evidence').textContent = `nabd-scene-${cur().name}.jsonl`;
    show(0);
  }

  // -- map ------------------------------------------------------------------
  function project(lat, lon, g) {
    const a = g.cells[0], b = g.cells[1], c = g.cells[g.cols];
    const dlon = b.lon - a.lon, dlat = c.lat - a.lat; // dlat is negative (south)
    return [M + ((lon - a.lon) / dlon + 0.5) * S, M + ((lat - a.lat) / dlat + 0.5) * S];
  }

  function drawMap(rec) {
    const g = cur().grid, svg = $('grid');
    const W = M + g.cols * S + 6, H = M + g.rows * S + 6;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const out = [];
    for (let c = 0; c < g.cols; c++) out.push(`<text class="lbl" x="${M + c * S + S / 2}" y="${M - 8}" text-anchor="middle">${c + 1}</text>`);
    for (let r = 0; r < g.rows; r++) out.push(`<text class="lbl" x="${M - 8}" y="${M + r * S + S / 2 + 3}" text-anchor="end">${'ABCDEFGHIJKLMNOPQRST'[r]}</text>`);
    g.cells.forEach((cell, k) => {
      const ch = (rec.grid || '')[k] || 'x';
      out.push(`<rect class="cell ${CLASS[ch]}" x="${M + cell.col * S}" y="${M + cell.row * S}" width="${S}" height="${S}" rx="3"><title>${cell.id} · ${cell.lat.toFixed(4)}N ${cell.lon.toFixed(4)}E</title></rect>`);
    });
    // The real event, when there is one: isoseismals at their published colours,
    // then the rupture that produced them.
    const geo = cur().geo;
    if (geo) {
      const path = pts => pts.map(([lon, lat], i) => {
        const [x, y] = project(lat, lon, g);
        return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
      }).join('');
      geo.contours.forEach(lv => {
        const major = Math.abs(lv.mmi - Math.round(lv.mmi)) < 0.01;
        lv.lines.forEach(line => out.push(
          `<path class="iso${major ? ' major' : ''}" d="${path(line)}" stroke="${lv.color}"><title>Measured intensity MMI ${lv.mmi}</title></path>`));
        if (major) {
          const line = lv.lines.reduce((a, b) => b.length > a.length ? b : a);
          const mid = line[Math.floor(line.length / 2)];
          const [lx, ly] = project(mid[1], mid[0], g);
          out.push(`<rect x="${lx - 9}" y="${ly - 7}" width="18" height="13" rx="3" fill="${lv.color}" opacity=".95"/>`);
          out.push(`<text class="isokey" x="${lx}" y="${ly + 3}" text-anchor="middle">${Math.round(lv.mmi)}</text>`);
        }
      });
      geo.rupture.forEach(ring => out.push(
        `<path class="rupture" d="${path(ring)}Z"><title>Finite-fault rupture, USGS ShakeMap</title></path>`));
    }
    (cur().maintenance || []).forEach(m => {
      if (rec.t >= m.start && rec.t < m.end) m.cells.forEach(id => {
        const cell = g.cells.find(c => c.id === id);
        out.push(`<rect class="mnt" x="${M + cell.col * S + 3}" y="${M + cell.row * S + 3}" width="${S - 6}" height="${S - 6}" rx="2"/>`);
      });
    });
    let cls = null;
    if (ACTIVE.has(rec.kind)) cls = 'fp';
    else if (rec.kind === 'CANDIDATE') cls = 'cand';
    else if (rec.kind === 'ABSTAIN' || (rec.reason || '').startsWith('holding')) cls = 'held';
    if (cls && rec.cells.length) {
      const set = new Set(rec.cells);
      rec.cells.forEach(id => {
        const cell = g.cells.find(c => c.id === id);
        const x = M + cell.col * S, y = M + cell.row * S;
        const n = (dr, dc) => set.has((g.cells.find(c => c.row === cell.row + dr && c.col === cell.col + dc) || {}).id);
        if (!n(-1, 0)) out.push(`<line class="${cls}" x1="${x}" y1="${y}" x2="${x + S}" y2="${y}"/>`);
        if (!n(1, 0)) out.push(`<line class="${cls}" x1="${x}" y1="${y + S}" x2="${x + S}" y2="${y + S}"/>`);
        if (!n(0, -1)) out.push(`<line class="${cls}" x1="${x}" y1="${y}" x2="${x}" y2="${y + S}"/>`);
        if (!n(0, 1)) out.push(`<line class="${cls}" x1="${x + S}" y1="${y}" x2="${x + S}" y2="${y + S}"/>`);
      });
      if (cls === 'fp') {
        const cells = rec.cells.map(id => g.cells.find(c => c.id === id));
        const bottom = Math.max(...cells.map(c => c.row)), left = Math.min(...cells.map(c => c.col));
        const label = `FOOTPRINT · ${rec.confidence || ''} · ${(rec.cells.length * (g.spacing_m / 1000) ** 2).toFixed(1)} km²`;
        const x = M + left * S, y = M + (bottom + 1) * S + 6;
        out.push(`<rect x="${x}" y="${y}" width="${label.length * 6.8 + 12}" height="18" rx="4" fill="#0b1017" stroke="var(--alert)" stroke-width="1"/>`);
        out.push(`<text class="fplabel" x="${x + 6}" y="${y + 13}">${label}</text>`);
      }
    }
    if (rec.triage) rec.triage.top.forEach(p => {
      if (!p.last_seen) return;
      const [x, y] = project(p.last_seen.lat, p.last_seen.lon, g);
      const r = (p.last_seen.radius_m / g.spacing_m) * S;
      out.push(`<circle class="halo" cx="${x}" cy="${y}" r="${r}"/>`);
      out.push(`<circle class="dot" cx="${x}" cy="${y}" r="4"><title>${p.person} · ${p.class} · ${p.cell}</title></circle>`);
    });
    svg.innerHTML = out.join('');
  }

  // -- panels -----------------------------------------------------------------
  function drawStatus(rec) {
    const sc = cur(), el = $('status');
    el.className = `card status k-${rec.kind}`;
    const declared = sc.records.slice(0, pass + 1).find(r => r.kind === 'DECLARE');
    let head = rec.reason || (rec.kind === 'QUIET' ? 'Monitoring. Nothing anomalous.' : '');
    if (rec.kind === 'SUSTAIN' && !rec.signals.length) head = rec.reason || 'Footprint held.';
    const change = registryChange(rec);
    if (change) head += ` — registry ${change[0]} → ${change[1]} unreachable`;
    let html = `<div class="headline"><span class="kind">${GLYPH[rec.kind]} ${rec.kind}</span>${esc(head)}</div>`;
    if (rec.confidence) html += `<span class="chip ${rec.confidence}">confidence ${rec.confidence}</span>`;
    if (declared) html += `<span class="chip">declared ${clock(declared.t)}${sc.onset != null ? ` · ${Math.round(declared.t - sc.onset)}s after onset` : ''}</span>`;
    const km2 = rec.cells.length ? (rec.cells.length * (sc.grid.spacing_m / 1000) ** 2).toFixed(1) : '–';
    html += `<div class="stats">
      <div class="stat"><b>${ACTIVE.has(rec.kind) ? rec.cells.length : '–'}</b><span>footprint cells</span></div>
      <div class="stat"><b>${ACTIVE.has(rec.kind) ? km2 : '–'}</b><span>km²</span></div>
      <div class="stat"><b>${rec.triage ? rec.triage.unreachable : '–'}</b><span>unreachable of ${rec.triage ? rec.triage.inside : sc.registry} registered</span></div>
    </div>`;
    if (rec.signals.length && rec.kind !== 'SUSTAIN') html += `<ul class="signals">${rec.signals.map(s => `<li>${esc(s)}</li>`).join('')}</ul>`;
    if (rec.privacy) {
      const open = !!rec.privacy.open;
      html += `<div class="privacy ${open ? 'open' : 'shut'}">` +
              `<b>${open ? '◉ PERSONAL DATA · OPEN' : '○ PERSONAL DATA · CLOSED'}</b>` +
              `<span>${esc(rec.privacy.note || '')}` +
              (open ? ` <b>${rec.privacy.personal}</b> calls this pass.` : '') + `</span></div>`;
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
    el.className = 'brief' + (text ? '' : ' empty');
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
  }

  // -- playback ---------------------------------------------------------------
  function play() {
    if (timer) return stop();
    if (pass >= cur().records.length - 1) pass = -1;
    $('play').textContent = '❚❚';
    timer = setInterval(() => { if (pass >= cur().records.length - 1) return stop(); show(pass + 1); }, 700);
  }
  function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶'; }

  $('play').onclick = play;
  $('prev').onclick = () => { stop(); show(pass - 1); };
  $('next').onclick = () => { stop(); show(pass + 1); };
  $('scrub').oninput = e => { stop(); show(+e.target.value); };
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
