# -*- coding: utf-8 -*-
"""Generate docs/nabd-deck.html from the evidence files.

    python docs/build_deck.py
    chrome --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf=Nabd-Pitch-Deck.pdf docs/nabd-deck.html

Every grid on the slides is drawn from the per-pass grid strings in the evidence
logs, so the deck cannot drift from what the agent actually did.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "nabd-deck.html"

quake = [json.loads(l) for l in (ROOT / "nac/evidence/nabd-scene-quake.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
noise = [json.loads(l) for l in (ROOT / "nac/evidence/nabd-scene-noise.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
DECL = quake[6]
assert DECL["kind"] == "DECLARE"
GRID_DECL = DECL["grid"]
GRID_CROWD = noise[10]["grid"]
GRID_MAINT = noise[6]["grid"]
GRID_FAULT = noise[2]["grid"]

ROWS = "ABCDEFGHIJ"

# palette
INK = "#17211D"; SOFT = "#41504a"; MUTED = "#6d7a74"; ACC = "#0E6E52"; RULE = "#d7ded9"; SURF = "#f2f6f4"
ALERT = "#d1463a"; HIGH = "#e08a2e"; MED = "#f3d9a4"; LOW = "#e3ebe6"


def grid_svg(grid: str, size: int, *, labels: bool = True, dark: bool = False, ring: bool = False) -> str:
    """A 10x10 cell grid. '.' low, 'm' medium, 'H' high congestion, 'D' dark (silent)."""
    pad = 26 if labels else 0
    cell = (size - pad) / 10
    gap = max(2, cell * 0.08)
    bg_low = "#1e2a37" if dark else LOW
    col = {".": bg_low, "m": ("#5b4a1a" if dark else MED), "H": ("#d9822b" if dark else HIGH), "D": ("#ff5a4e" if dark else ALERT)}
    lbl = "#8a9bab" if dark else MUTED
    out = [f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg" font-family="Consolas, Segoe UI, monospace">']
    for i, ch in enumerate(grid):
        r, c = divmod(i, 10)
        x = pad + c * cell + gap / 2
        y = pad + r * cell + gap / 2
        w = cell - gap
        extra = ""
        if ch == "D":
            extra = f' stroke="{"#ffb4ad" if dark else "#7a1f17"}" stroke-width="{max(1.2, cell*0.05):.1f}"'
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{w:.1f}" rx="{cell*0.12:.1f}" fill="{col[ch]}"{extra}/>')
    if labels:
        fs = max(9, cell * 0.36)
        for c in range(10):
            out.append(f'<text x="{pad + c*cell + cell/2:.1f}" y="{pad*0.72:.1f}" text-anchor="middle" font-size="{fs:.0f}" fill="{lbl}">{c+1}</text>')
        for r in range(10):
            out.append(f'<text x="{pad*0.45:.1f}" y="{pad + r*cell + cell/2 + fs*0.35:.1f}" text-anchor="middle" font-size="{fs:.0f}" fill="{lbl}">{ROWS[r]}</text>')
    if ring:
        # outline of the declared footprint E4..G6 → rows 4..6, cols 3..5
        x0 = pad + 3 * cell; y0 = pad + 4 * cell
        out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{3*cell:.1f}" height="{3*cell:.1f}" fill="none" stroke="{"#ffb4ad" if dark else "#7a1f17"}" stroke-width="{max(2, cell*0.09):.1f}" stroke-dasharray="{cell*0.35:.0f} {cell*0.2:.0f}" rx="{cell*0.15:.0f}"/>')
    out.append("</svg>")
    return "\n".join(out)


def legend(dark=False):
    items = [(ALERT if not dark else "#ff5a4e", "silent — sentinel unreachable"),
             (HIGH if not dark else "#d9822b", "High congestion"),
             (MED if not dark else "#5b4a1a", "Medium"),
             (LOW if not dark else "#1e2a37", "Low")]
    return '<div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{t}</span>' for c, t in items) + "</div>"


top3 = DECL["triage"]["top"][:3]


def person_row(p):
    ls = p["last_seen"]
    return (f'<tr><td class="mono">{p["person"]}</td><td>{p["class"]}</td><td class="mono">{p["cell"]}</td>'
            f'<td>last seen {-(-ls["age_s"]//60)} min ago · within {ls["radius_m"]} m</td></tr>')


slides = []

# ---------- 1 cover
slides.append(f"""
<section class="slide cover" id="slide-1">
  <div class="kicker">GSMA MENA Ignite Open Gateway Hackathon 2026 &nbsp;·&nbsp; Prototype Phase</div>
  <h1>Nabd <span class="ar">· نبض</span></h1>
  <p class="tag">Read where the network goes silent.</p>
  <p class="cover-sub">An AI agent that turns coordinated network silence into a live disaster-impact map
  for command centres — the impact map in the first minute, triage across the first 72 hours.</p>
  <div class="chips">
    <span>Theme 6 — Climate Resilience &amp; Environmental Monitoring</span>
    <span>Nokia Network-as-Code</span>
    <span>Agent layer: LangGraph</span>
    <span>Kadir's Team</span>
  </div>
  <div class="cover-grid">{grid_svg(GRID_DECL, 300, labels=False, ring=True)}</div>
</section>""")

# ---------- 2 the wound
slides.append("""
<section class="slide" id="slide-2">
  <div class="kicker">The wound</div>
  <h2>The first hours decide who is found alive.</h2>
  <div class="stats3">
    <div><b>53,000+</b><span>Kahramanmaraş, Türkiye<br>earthquakes, February 2023</span></div>
    <div><b>~3,000</b><span>Al Haouz, Morocco<br>earthquake, September 2023</span></div>
    <div><b>11,000+</b><span>Derna, Libya<br>dam collapse and flood, September 2023</span></div>
  </div>
  <p class="lead" style="font-size:30px;max-width:1080px">In each of them, sensors confirmed <em>something</em> had happened within seconds.
  Which neighbourhoods had lost their people — that map arrived hours late.</p>
  <p class="note" style="font-size:20px;margin-top:22px">2024: Dubai and Oman floods. Same region, a different hazard, the same missing map.</p>
</section>""")

# ---------- 3 the gap
slides.append("""
<section class="slide" id="slide-3">
  <div class="kicker">The gap</div>
  <h2>Detection is solved. Impact is not.</h2>
  <div class="two">
    <div class="card">
      <div class="lbl">Seconds</div>
      <p>Seismometers, satellites and phone-based systems say <b>“it happened”</b> almost instantly.</p>
    </div>
    <div class="card">
      <div class="lbl">Hours</div>
      <p><b>“Which district first?”</b> is pieced together from fragmented calls, social media and field
      reports — on a network that is overloaded at exactly that moment.</p>
    </div>
  </div>
  <div class="two claims">
    <div class="no"><div class="lbl">Nabd is not</div><p>early warning. Seismometers and existing alert systems own quake detection; we do not compete with them.</p></div>
    <div class="yes"><div class="lbl">Nabd is</div><p>the <b>impact map in the first minute</b>, and <b>triage across the first 72 hours</b> — who is cut off, and where.</p></div>
  </div>
</section>""")

# ---------- 4 the insight
slides.append("""
<section class="slide" id="slide-4">
  <div class="kicker">The insight</div>
  <h2 class="huge">Silence is a sensor.</h2>
  <p class="lead wide">When a whole block of cells goes dark at the same moment, the network already knows
  where the disaster hit — before a single emergency call gets through.</p>
  <div class="steps">
    <div><i>1</i><p>An area goes <b>dark</b>: its cells stop answering.</p></div>
    <div><i>2</i><p>The ring around it goes <b>hot</b>: everyone calls at once.</p></div>
    <div><i>3</i><p>That pair, at the same instant, is a signature <b>no other event produces</b>.</p></div>
  </div>
  <p class="note">Disaster-agnostic: earthquake, flood, storm, mass power outage — to the network they are the same thing, an area going silent.</p>
</section>""")

# ---------- 5 two layers (diagram)
slides.append("""
<section class="slide" id="slide-5">
  <div class="kicker">Architecture</div>
  <h2>Two layers. Detection is aggregate; triage is consented.</h2>
  <svg class="diagram" viewBox="0 0 1152 470" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#41504a"/></marker>
    </defs>
    <!-- detection column -->
    <rect x="0" y="0" width="540" height="470" rx="14" fill="#f2f6f4"/>
    <text x="24" y="38" class="h">DETECTION — aggregate, no public devices</text>
    <rect x="24" y="60" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="40" y="90" class="t">Sentinel grid — one municipal or operator-owned SIM per cell</text>
    <text x="40" y="118" class="s">read every 30 s · 10×10 cells over Kahramanmaraş in the prototype</text>
    <rect x="24" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="142" y="200" class="api" text-anchor="middle">Congestion Insights</text>
    <text x="142" y="226" class="s" text-anchor="middle">load per cell</text>
    <rect x="280" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="398" y="200" class="api" text-anchor="middle">Device Reachability</text>
    <text x="398" y="226" class="s" text-anchor="middle">is the sentinel answering?</text>
    <rect x="24" y="268" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="40" y="298" class="t">Contiguous silent block + hot ring + persistence</text>
    <text x="40" y="326" class="s">maintenance calendar removed first · one signal never declares alone</text>
    <rect x="24" y="378" width="492" height="70" rx="10" fill="#17211D"/>
    <text x="270" y="408" class="w" text-anchor="middle">Footprint declared — HIGH / MEDIUM</text>
    <text x="270" y="434" class="ws" text-anchor="middle">or an abstention, with the reason written down</text>
    <line x1="270" y1="146" x2="270" y2="168" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="270" y1="244" x2="270" y2="266" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="270" y1="354" x2="270" y2="376" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <!-- triage column -->
    <rect x="612" y="0" width="540" height="470" rx="14" fill="#f2f6f4"/>
    <text x="636" y="38" class="h">TRIAGE — per person, opt-in only</text>
    <rect x="636" y="60" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="652" y="90" class="t">Registry of people who asked to be protected</text>
    <text x="652" y="118" class="s">elderly · disabled · pilgrimage groups · lone workers — pseudonymous IDs</text>
    <rect x="636" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="754" y="200" class="api" text-anchor="middle">Device Reachability</text>
    <text x="754" y="226" class="s" text-anchor="middle">who is unreachable</text>
    <rect x="892" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="1010" y="200" class="api" text-anchor="middle">Location Retrieval</text>
    <text x="1010" y="226" class="s" text-anchor="middle">where they were last seen</text>
    <rect x="636" y="268" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="652" y="298" class="t">Ranked list: priority zones and people to reach first</text>
    <text x="652" y="326" class="s">updated every pass as people answer again</text>
    <rect x="636" y="378" width="492" height="70" rx="10" fill="#0E6E52"/>
    <text x="882" y="408" class="w" text-anchor="middle">Command-centre brief</text>
    <text x="882" y="434" class="ws" text-anchor="middle">map · verdict · signals · list — replayable from the evidence log</text>
    <line x1="882" y1="146" x2="882" y2="168" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="882" y1="244" x2="882" y2="266" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="882" y1="354" x2="882" y2="376" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <!-- gate -->
    <line x1="516" y1="413" x2="634" y2="413" stroke="#0E6E52" stroke-width="3" marker-end="url(#arr)"/>
    <rect x="546" y="356" width="60" height="42" rx="8" fill="#fff" stroke="#0E6E52"/>
    <text x="576" y="383" class="gate" text-anchor="middle">gate</text>
    <text x="576" y="446" class="gs" text-anchor="middle">only inside a</text>
    <text x="576" y="464" class="gs" text-anchor="middle">declared footprint</text>
  </svg>
</section>""")

# ---------- 6 first-minute signature
slides.append(f"""
<section class="slide" id="slide-6">
  <div class="kicker">The first-minute signature</div>
  <h2>A block goes silent. The ring around it goes hot.</h2>
  <div class="sig">
    <div class="sig-grid">{grid_svg(GRID_DECL, 400, ring=True)}{legend()}</div>
    <div class="sig-text">
      <div class="sigrow"><b class="red">9 cells silent</b><p>E4 → G6, about 4.0 km². Their sentinels stop answering — <em>Device Reachability</em>.</p></div>
      <div class="sigrow"><b class="amber">16 / 16 ring cells at High</b><p>Everyone around the block is calling at once — <em>Congestion Insights</em>.</p></div>
      <div class="sigrow"><b>Onset synchronised</b><p>All nine went dark inside one 30-second window. A cell fault does not do that.</p></div>
      <div class="sigrow"><b>Persisted a second pass</b><p>Candidate at 09:02:30, declared at 09:03:00 — <b>55 seconds after onset</b>, confidence <b>HIGH</b>.</p></div>
    </div>
  </div>
  <p class="note" style="margin-top:8px">The grid is drawn from the evidence record of the declaring pass, not illustrated.</p>
</section>""")

# ---------- 7 the agent
slides.append("""
<section class="slide" id="slide-7">
  <div class="kicker">The agent — the mandatory component, on LangGraph</div>
  <h2>One signal never declares alone.</h2>
  <div class="agent">
    <svg class="topo" viewBox="0 0 600 440" xmlns="http://www.w3.org/2000/svg">
      <defs><marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#41504a"/></marker></defs>
      <g class="node"><rect x="200" y="10" width="160" height="46" rx="23"/><text x="280" y="39">sense</text></g>
      <g class="node"><rect x="200" y="86" width="160" height="46" rx="23"/><text x="280" y="115">correlate</text></g>
      <g class="node"><rect x="200" y="162" width="160" height="46" rx="23"/><text x="280" y="191">exclude</text></g>
      <g class="node key"><rect x="200" y="238" width="160" height="46" rx="23"/><text x="280" y="267">declare</text></g>
      <g class="node"><rect x="40" y="326" width="160" height="46" rx="23"/><text x="120" y="355">hold</text></g>
      <g class="node key2"><rect x="360" y="326" width="160" height="46" rx="23"/><text x="440" y="355">triage</text></g>
      <g class="node"><rect x="200" y="394" width="160" height="46" rx="23"/><text x="280" y="423">brief → log</text></g>
      <line x1="280" y1="56" x2="280" y2="84" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <line x1="280" y1="132" x2="280" y2="160" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <line x1="280" y1="208" x2="280" y2="236" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <path d="M230,284 C200,310 160,300 130,324" fill="none" stroke="#41504a" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#a2)"/>
      <path d="M330,284 C360,310 400,300 430,324" fill="none" stroke="#0E6E52" stroke-width="2.5" stroke-dasharray="6 5" marker-end="url(#a2)"/>
      <path d="M150,372 C180,392 210,392 245,393" fill="none" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <path d="M410,372 C380,392 350,392 315,393" fill="none" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <text x="96" y="306" class="edge">no footprint</text>
      <text x="392" y="306" class="edge green">footprint declared</text>
      <text x="478" y="258" class="side">conditional edge</text>
      <text x="478" y="276" class="side">gates triage</text>
    </svg>
    <div class="agent-text">
      <p><b>Corroborate before you speak.</b> Silence is only the hypothesis. It must be backed by a synchronised onset or a hot ring, persist for a second pass, and survive the operator's maintenance calendar.</p>
      <p><b>Grade the confidence.</b> Two corroborations → HIGH. One → MEDIUM. None → abstain, with the reason written into the log.</p>
      <p><b>Gate the personal layer.</b> The conditional edge means no registry device is ever queried outside a declared footprint — a fuzzed test invariant, not a promise.</p>
      <p><b>Keep the LLM off the control path.</b> Detection is deterministic and replayable; the language model only writes the command-centre sentence.</p>
    </div>
  </div>
</section>""")

# ---------- 8 what we built
slides.append("""
<section class="slide" id="slide-8">
  <div class="kicker">What we built — prototype status</div>
  <h2>A working agent, offline and live through one surface.</h2>
  <div class="built">
    <table class="mods">
      <tr><td class="mono">world · model</td><td>10×10 grid, 48-person opt-in registry, quake / cell-fault / peak events, maintenance calendar</td></tr>
      <tr><td class="mono">gateway</td><td>one CAMARA surface, two backends — simulator (NaC vocabulary and shapes) and live via the Nokia SDK</td></tr>
      <tr><td class="mono">detector</td><td>correlate → exclude → declare; pure functions, no framework import</td></tr>
      <tr><td class="mono">triage · brief</td><td>reachability and last-seen inside the footprint only; the command-centre sentence</td></tr>
      <tr><td class="mono">graph · loop</td><td>the LangGraph runner and the plain runner — same evidence, byte for byte</td></tr>
      <tr><td class="mono">scene · console</td><td>three scenes; a self-contained command-centre console generated from the evidence</td></tr>
    </table>
    <div class="status">
      <div><b>Runs on bare Python</b><span>no account, no server, no CDN — the demo cannot fail in the room</span></div>
      <div><b>Same agent, live</b><span><code>--backend live</code> makes the identical three calls through the Nokia SDK and records the raw exchanges</span></div>
      <div><b>Two runners, identical</b><span>plain loop and LangGraph diffed byte for byte — 4,405 CAMARA calls</span></div>
      <div><b>65 / 65 tests, 8 suites</b><span>incl. fuzzed invariants: no footprint without a contiguous block; no personal-device call outside a footprint</span></div>
    </div>
  </div>
</section>""")

# ---------- 9 evidence: quake console
sig = DECL["signals"]
slides.append(f"""
<section class="slide" id="slide-9">
  <div class="kicker">Evidence — the earthquake scene</div>
  <h2>Declared 55 seconds after onset. Six people to reach first.</h2>
  <div class="console">
    <div class="c-head"><span class="c-title">NABD · COMMAND CENTRE</span><span class="c-scene">scene: earthquake · pass 7 / 21 · 30 s cadence</span><span class="c-clock">09:03:00</span></div>
    <div class="c-body">
      <div class="c-map">{grid_svg(GRID_DECL, 250, labels=False, dark=True, ring=True)}</div>
      <div class="c-verdict">
        <div class="c-kind"><span class="badge">DECLARE</span><span class="conf">HIGH</span> 9 cells · ~4.0 km² · centred 37.5828N 36.9333E</div>
        <ul class="c-signals">{''.join(f'<li>{s}</li>' for s in sig)}</ul>
        <div class="c-triage"><span class="c-lbl">registry</span> 13 opted-in people inside · <b>6 unreachable</b></div>
        <table class="c-list">{''.join(person_row(p) for p in top3)}</table>
      </div>
    </div>
    <div class="c-foot"><span>declared 09:03:00 — 55 s after onset</span><span>13 inside · peak 6 unreachable</span><span>21 passes · 4,405 CAMARA calls</span><span>evidence: nabd-scene-quake.jsonl</span></div>
  </div>
  <p class="note">Later passes: footprint held; the list updates 6 → 4 as people answer again. Every element on the console is redrawn from the evidence log — the screen is a view over the record, never a second source of truth.</p>
</section>""")

# ---------- 10 does not cry wolf
slides.append(f"""
<section class="slide" id="slide-10">
  <div class="kicker">Evidence — the look-alikes</div>
  <h2>The agent does not cry wolf.</h2>
  <div class="three">
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_FAULT, 150, labels=False)}</div><div class="lbl">09:01:00 · single cell</div><p>“single-cell silence at C3: one sentinel unreachable, neighbours normal — consistent with a cell fault, not an impact”</p><b>ABSTAIN</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_MAINT, 150, labels=False)}</div><div class="lbl">09:03:00 · maintenance</div><p>“4 contiguous cells silent, but the block matches maintenance ticket MNT-2214 — expected silence, no alert”</p><b>ABSTAIN</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_CROWD, 150, labels=False)}</div><div class="lbl">09:05:00 · stadium kick-off</div><p>“congestion without silence: 9 contiguous cells at High but every sentinel answers — a crowd, not an impact”</p><b>ABSTAIN</b></div>
  </div>
  <p class="lead">Noise scene: 21 passes, three abstentions, <b>zero declarations</b> — each refusal with its reason in the log. The quiet scene stays quiet. Written reasons are what make a false alarm auditable and a true alarm trusted.</p>
</section>""")

# ---------- 11 CAMARA
slides.append("""
<section class="slide" id="slide-11">
  <div class="kicker">CAMARA on Nokia Network-as-Code</div>
  <h2>Remove the network APIs and nothing works. The network is the sensor.</h2>
  <div class="two apis">
    <table class="apit">
      <tr><th>API</th><th>Role</th><th>Prototype</th></tr>
      <tr><td class="api">Congestion Insights</td><td>detection — load per sentinel cell, the hot ring</td><td class="live">live path</td></tr>
      <tr><td class="api">Device Reachability Status</td><td>detection (sentinels) and triage (registry)</td><td class="live">live path</td></tr>
      <tr><td class="api">Location Retrieval</td><td>triage — last-seen position of the unreachable</td><td class="live">live path</td></tr>
      <tr><td class="api">Geofencing Subscriptions</td><td>boundary events as the footprint grows or shrinks</td><td class="road">roadmap</td></tr>
      <tr><td class="api">Quality on Demand</td><td>a priority channel for responders inside the footprint</td><td class="road">roadmap</td></tr>
    </table>
    <div class="why">
      <div class="lbl">Why CAMARA, not a control room</div>
      <p>An operator's NOC sees its own cells go down — from inside one operator.</p>
      <p>Responders — civil defence, the Red Crescent, municipalities, hospitals — sit <b>outside</b>, and cannot log into three operators in the middle of a disaster.</p>
      <p>Open Gateway is the <b>one standard door</b>: operator-independent, and it unifies every national operator behind a single interface. Stable since 2025, available on Network-as-Code today.</p>
    </div>
  </div>
</section>""")

# ---------- 12 live vs simulated, privacy, consent
slides.append("""
<section class="slide" id="slide-12">
  <div class="kicker">Honest boundaries</div>
  <h2>Live where it can be. Simulated where it must be. Private by design.</h2>
  <div class="three cols">
    <div class="col"><div class="lbl">Live vs simulated</div>
      <p>The sandbox cannot stage a disaster. So the split is explicit: the <b>live platform proves the contract</b> with real, recorded calls; the <b>simulator stages the disaster</b> through the same code path, shaped on the public record of the 2023 Kahramanmaraş outage.</p>
      <p>One gateway surface, two backends, identical agent code and identical evidence format.</p></div>
    <div class="col"><div class="lbl">Privacy</div>
      <p>Detection reads only <b>sentinel devices the city or operator owns</b> — never the public.</p>
      <p>Its output is <b>area-level</b>: cells and a footprint, not people. No cameras, no message content, no tracking.</p></div>
    <div class="col"><div class="lbl">Consent</div>
      <p>Triage touches an individual only if they <b>opted in</b> to be protected.</p>
      <p>The agency holds the registry; the operator honours it. IDs are pseudonymous, and <b>no location call is ever made outside a declared footprint</b>.</p></div>
  </div>
</section>""")

# ---------- 13 impact, scale, business
slides.append("""
<section class="slide" id="slide-13">
  <div class="kicker">Impact · scale · business</div>
  <h2>One engine, many hazards. Minutes, not hours.</h2>
  <div class="three cols">
    <div class="col"><div class="lbl">Impact</div>
      <p>Earthquake, flood, storm, mass outage — to the network each is an area going dark, so one engine covers them all.</p>
      <p>The first dispatch decision moves from <b>hours to minutes</b>, and the most vulnerable are reached first.</p></div>
    <div class="col"><div class="lbl">Scale</div>
      <p>A sentinel grid scales by <b>cell count</b>; SIMs are municipal or operator-owned, so a national rollout is a procurement, not a behaviour change.</p>
      <p>Open Gateway makes the same agent portable across operators and countries in the region.</p></div>
    <div class="col"><div class="lbl">Business</div>
      <p><b>Buyers:</b> civil-defence agencies (AFAD), Red Crescent societies, municipalities, hospital networks.</p>
      <p><b>Seller:</b> the operator, as an Open Gateway <b>impact-feed product</b> — a standing subscription for the grid, per-event triage on top.</p></div>
  </div>
  <div class="roadmap"><span class="lbl">Roadmap</span> Population Density Data as the detection upgrade once published on NaC &nbsp;·&nbsp; Geofencing for boundary events &nbsp;·&nbsp; QoD priority for responders inside the footprint &nbsp;·&nbsp; multi-operator fusion</div>
</section>""")

# ---------- 14 close
slides.append(f"""
<section class="slide cover close" id="slide-14">
  <div class="kicker">Nabd · نبض &nbsp;·&nbsp; Theme 6 &nbsp;·&nbsp; Prototype Phase</div>
  <h2 class="huge2">The network already knows.<br>Nabd makes it say so — in the first minute.</h2>
  <div class="next">
    <div><div class="lbl">Next</div><p>Live contract run on Network-as-Code devices · pilot with one civil-defence agency on one city's sentinel grid · Population Density upgrade when published</p></div>
    <div><div class="lbl">Team</div><p>Kadir Can Yıldırım — Kadir's Team, solo builder, Türkiye. Code, evidence logs and the command-centre console are in the submission links.</p></div>
  </div>
  <p class="doha">See you in Doha — MWC Doha, November 2026.</p>
  <div class="cover-grid small">{grid_svg(GRID_DECL, 220, labels=False, ring=True)}</div>
</section>""")

CSS = f"""
  @page {{ size: 1280px 720px; margin: 0; }}
  :root{{ --ink:{INK}; --soft:{SOFT}; --muted:{MUTED}; --acc:{ACC}; --rule:{RULE}; --surf:{SURF}; --alert:{ALERT}; --high:{HIGH};
          --serif:"Georgia","Times New Roman",serif; --sans:"Segoe UI","Helvetica Neue",Arial,sans-serif; --mono:Consolas,"Cascadia Mono",monospace; }}
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  body{{font-family:var(--serif);color:var(--ink);line-height:1.4}}
  .slide{{position:relative;width:1280px;height:720px;overflow:hidden;padding:56px 72px 60px;background:#fff;page-break-after:always;break-after:page;page-break-inside:avoid}}
  .slide:last-child{{page-break-after:auto;break-after:auto}}
  .slide::after{{content:attr(data-n);position:absolute;right:40px;bottom:26px;font-family:var(--sans);font-size:13px;color:var(--muted)}}
  .slide::before{{content:"Nabd · نبض";position:absolute;left:72px;bottom:26px;font-family:var(--sans);font-size:13px;color:var(--muted);letter-spacing:.02em}}
  .kicker{{font-family:var(--sans);font-size:15px;text-transform:uppercase;letter-spacing:.12em;color:var(--acc);font-weight:600;margin:0 0 14px}}
  h1{{font-family:var(--sans);font-size:104px;letter-spacing:-.02em;margin:26px 0 6px;line-height:1;font-weight:700}}
  h1 .ar{{font-family:var(--serif);font-weight:400;color:var(--muted);font-size:72px}}
  h2{{font-family:var(--sans);font-size:40px;letter-spacing:-.015em;line-height:1.15;margin:0 0 26px;font-weight:700}}
  h2.huge{{font-size:96px;margin:40px 0 24px}}
  h2.huge2{{font-size:50px;margin:40px 0 40px;max-width:1120px}}
  .tag{{font-family:var(--sans);font-size:34px;color:var(--acc);font-weight:600;margin:0 0 22px}}
  .cover-sub{{font-size:25px;max-width:760px;color:var(--soft);margin:0 0 34px;line-height:1.45}}
  .chips{{display:flex;flex-wrap:wrap;gap:10px;max-width:760px}}
  .chips span{{font-family:var(--sans);font-size:15px;border:1px solid var(--rule);background:var(--surf);border-radius:999px;padding:7px 14px;color:var(--soft)}}
  .cover-grid{{position:absolute;right:72px;top:150px}}
  .cover-grid.small{{top:auto;bottom:70px;right:72px}}
  .lead{{font-size:26px;line-height:1.45;color:var(--ink);margin:0 0 14px}}
  .lead.wide{{max-width:1000px;font-size:30px}}
  .note{{font-family:var(--sans);font-size:17px;color:var(--muted);margin:14px 0 0}}
  .lbl{{font-family:var(--sans);font-size:14px;text-transform:uppercase;letter-spacing:.1em;color:var(--acc);font-weight:600;margin-bottom:8px}}
  .stats3{{display:grid;grid-template-columns:repeat(3,1fr);gap:28px;margin:30px 0 44px}}
  .stats3 div{{background:var(--surf);border-left:4px solid var(--alert);padding:34px 26px 30px;border-radius:0 10px 10px 0}}
  .stats3 b{{display:block;font-family:var(--sans);font-size:78px;line-height:1;letter-spacing:-.02em;margin-bottom:16px}}
  .stats3 span{{font-family:var(--sans);font-size:19px;color:var(--soft);line-height:1.35}}
  .two{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
  .card{{background:var(--surf);border-radius:10px;padding:26px 28px}}
  .card p{{font-size:25px;margin:0;line-height:1.4}}
  .claims{{margin-top:32px}}
  .claims .no,.claims .yes{{border-radius:10px;padding:26px 28px}}
  .claims .no{{border:2px solid var(--rule)}}
  .claims .yes{{border:2px solid var(--acc);background:#eef6f2}}
  .claims .no .lbl{{color:var(--muted)}}
  .claims p{{font-size:25px;margin:0;line-height:1.4}}
  .steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin:26px 0 22px}}
  .steps div{{display:flex;gap:14px;align-items:flex-start;background:var(--surf);border-radius:10px;padding:18px 20px}}
  .steps i{{font-style:normal;font-family:var(--sans);font-weight:700;color:#fff;background:var(--acc);border-radius:50%;width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;flex:none;font-size:18px}}
  .steps p{{margin:0;font-size:22px;line-height:1.35}}
  .diagram{{width:1136px;height:464px;display:block;margin-top:4px}}
  .diagram .h{{font-family:var(--sans);font-size:15px;font-weight:700;letter-spacing:.1em;fill:var(--acc)}}
  .diagram .t{{font-family:var(--sans);font-size:19px;font-weight:600;fill:var(--ink)}}
  .diagram .s{{font-family:var(--sans);font-size:15px;fill:var(--muted)}}
  .diagram .api{{font-family:var(--sans);font-size:18px;font-weight:700;fill:var(--acc)}}
  .diagram .w{{font-family:var(--sans);font-size:19px;font-weight:700;fill:#fff}}
  .diagram .ws{{font-family:var(--sans);font-size:14px;fill:#d7e1ea}}
  .diagram .gate{{font-family:var(--sans);font-size:15px;font-weight:700;fill:var(--acc);letter-spacing:.06em}}
  .diagram .gs{{font-family:var(--sans);font-size:13px;fill:var(--soft)}}
  .sig{{display:grid;grid-template-columns:400px 1fr;gap:48px;align-items:start}}
  .legend{{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:10px;font-family:var(--sans);font-size:13px;color:var(--soft)}}
  .legend i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
  .sigrow{{margin:0 0 14px;padding-left:18px;border-left:3px solid var(--rule)}}
  .sigrow > b{{font-family:var(--sans);font-size:24px;display:block;margin-bottom:3px}}
  .sigrow p b{{font-family:var(--sans)}}
  .sigrow b.red{{color:var(--alert)}} .sigrow b.amber{{color:#b8671a}}
  .sigrow p{{margin:0;font-size:19px;color:var(--soft);line-height:1.35}}
  .agent{{display:grid;grid-template-columns:520px 1fr;gap:36px;align-items:start}}
  .topo{{width:540px;height:396px}}
  .topo .node rect{{fill:var(--surf);stroke:var(--rule);stroke-width:1.5}}
  .topo .node text{{font-family:var(--mono);font-size:19px;fill:var(--ink);text-anchor:middle}}
  .topo .node.key rect{{fill:var(--ink);stroke:var(--ink)}} .topo .node.key text{{fill:#fff}}
  .topo .node.key2 rect{{fill:#eef6f2;stroke:var(--acc);stroke-width:2}} .topo .node.key2 text{{fill:var(--acc);font-weight:700}}
  .topo .edge{{font-family:var(--sans);font-size:13px;fill:var(--muted)}} .topo .edge.green{{fill:var(--acc);font-weight:700}}
  .topo .side{{font-family:var(--sans);font-size:13px;fill:var(--acc)}}
  .agent-text p{{font-size:21px;line-height:1.4;margin:0 0 16px}}
  .agent-text b{{font-family:var(--sans)}}
  .built{{display:grid;grid-template-columns:1.25fr 1fr;gap:36px;align-items:start}}
  table{{border-collapse:collapse;width:100%}}
  .mods td{{font-family:var(--sans);font-size:17px;padding:10px 10px;border-bottom:1px solid var(--rule);vertical-align:top;color:var(--soft);line-height:1.35}}
  .mods td.mono{{font-family:var(--mono);color:var(--acc);font-weight:700;white-space:nowrap;font-size:16px}}
  .status div{{background:var(--surf);border-radius:10px;padding:14px 18px;margin-bottom:12px}}
  .status b{{display:block;font-family:var(--sans);font-size:20px;margin-bottom:3px}}
  .status span{{font-family:var(--sans);font-size:15px;color:var(--soft);line-height:1.35}}
  code{{font-family:var(--mono);background:#e6ede9;padding:1px 6px;border-radius:4px;font-size:.92em}}
  .console{{background:#0b1017;color:#d7e1ea;border-radius:12px;padding:16px 20px;font-family:var(--sans);border:1px solid #1e2a37}}
  .c-head{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #1e2a37;padding-bottom:10px;margin-bottom:12px}}
  .c-title{{font-family:var(--mono);letter-spacing:.14em;font-size:14px;color:#8a9bab}}
  .c-scene{{font-size:13px;color:#7f8f9f}}
  .c-clock{{font-family:var(--mono);font-size:24px;color:#fff}}
  .c-body{{display:grid;grid-template-columns:250px 1fr;gap:22px;align-items:start}}
  .c-kind{{font-size:17px;margin-bottom:8px}}
  .badge{{font-family:var(--mono);font-size:13px;padding:3px 8px;border-radius:4px;background:#3a1613;color:#ffb4ad;margin-right:8px;font-weight:700}}
  .conf{{font-family:var(--mono);font-size:13px;padding:3px 8px;border-radius:4px;background:#16324b;color:#7cc4ff;margin-right:10px;font-weight:700}}
  .c-signals{{margin:0 0 10px;padding-left:18px;font-size:14.5px;color:#d7e1ea;line-height:1.45}}
  .c-signals li::marker{{color:#4cc38a}}
  .c-triage{{font-size:15px;margin-bottom:6px}} .c-triage b{{color:#ffb4ad}}
  .c-lbl{{font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:#8a9bab;margin-right:6px}}
  .c-list td{{font-size:14px;padding:4px 8px 4px 0;border-bottom:1px solid #161c24;color:#d7e1ea}}
  .c-list td.mono{{font-family:var(--mono);color:#ffd98a}}
  .c-foot{{display:flex;justify-content:space-between;border-top:1px solid #1e2a37;margin-top:12px;padding-top:10px;font-family:var(--mono);font-size:12.5px;color:#8a9bab}}
  .three{{display:grid;grid-template-columns:repeat(3,1fr);gap:26px}}
  .wolf{{background:var(--surf);border-radius:10px;padding:18px 22px;display:flex;flex-direction:column;min-height:250px}}
  .wgrid{{margin:0 0 12px}}
  .wolf p{{font-size:18.5px;line-height:1.38;margin:0;flex:1;color:var(--ink)}}
  .wolf b{{font-family:var(--mono);color:var(--acc);font-size:16px;letter-spacing:.1em;margin-top:14px}}
  .wolf .lbl{{color:var(--muted)}}
  .three + .lead{{margin-top:22px;font-size:21px}}
  .apis{{grid-template-columns:1.15fr 1fr;gap:36px}}
  .apit th{{font-family:var(--sans);font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:left;padding:6px 10px;border-bottom:2px solid var(--rule)}}
  .apit td{{font-family:var(--sans);font-size:17px;padding:12px 10px;border-bottom:1px solid var(--rule);vertical-align:top;color:var(--soft);line-height:1.3}}
  .apit td.api{{color:var(--acc);font-weight:700;white-space:nowrap}}
  .apit td.live{{color:var(--acc);font-weight:700;white-space:nowrap}} .apit td.road{{color:var(--muted);white-space:nowrap}}
  .why{{background:var(--surf);border-radius:10px;padding:20px 24px}}
  .why p{{font-size:20px;line-height:1.4;margin:0 0 12px}}
  .cols .col{{background:var(--surf);border-radius:10px;padding:20px 22px;min-height:360px}}
  .cols .col p{{font-size:19.5px;line-height:1.4;margin:0 0 12px}}
  .roadmap{{margin-top:22px;font-family:var(--sans);font-size:16px;color:var(--soft);background:#eef6f2;border-radius:10px;padding:12px 18px}}
  .roadmap .lbl{{display:inline;margin-right:12px}}
  .close h2{{margin-top:70px}}
  .next{{display:grid;grid-template-columns:1fr 1fr;gap:36px;max-width:900px}}
  .next p{{font-size:20px;line-height:1.4;margin:0;color:var(--soft)}}
  .doha{{font-family:var(--sans);font-size:24px;color:var(--acc);font-weight:600;margin:44px 0 0}}
"""

SCRIPT = r"""<script>
(function(){
  // #slide-N shows that slide alone on screen (used for screenshots and for stepping through in a browser);
  // printing ignores the hash and lays out all fourteen.
  function apply(){
    var m=(location.hash||'').match(/^#slide-(\d+)$/);
    document.querySelectorAll('.slide').forEach(function(s){ s.style.display = (m && s.id!=='slide-'+m[1]) ? 'none' : ''; });
  }
  apply(); addEventListener('hashchange',apply);
  addEventListener('beforeprint',function(){document.querySelectorAll('.slide').forEach(function(s){s.style.display='';});});
  addEventListener('keydown',function(e){
    var m=(location.hash||'').match(/^#slide-(\d+)$/); var n=m?+m[1]:1;
    if(e.key==='ArrowRight'||e.key===' '){ n=Math.min(14,n+1); location.hash='#slide-'+n; }
    if(e.key==='ArrowLeft'){ n=Math.max(1,n-1); location.hash='#slide-'+n; }
  });
})();
</script>"""

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Nabd — Prototype Phase pitch deck</title>
<style>{CSS}</style>
</head>
<body>
{''.join(s.replace('<section class="slide', f'<section data-n="{i+1} / 14" class="slide', 1) for i, s in enumerate(slides))}
{SCRIPT}
</body>
</html>
"""
OUT.write_text(html, encoding="utf-8")
print("wrote", OUT, len(html), "bytes", len(slides), "slides")
