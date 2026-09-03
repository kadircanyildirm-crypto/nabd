# Nabd · نبض

**Read where the network goes silent.**

An AI agent that turns coordinated network silence into a live disaster-impact map
for command centres. It does not predict the earthquake; it answers the question
that costs lives in the first hours — *where is the damage worst, and who is cut
off* — as an impact map in the first minute and a triage list over the first 72 hours.

Built for the **GSMA MENA Ignite Hackathon 2026** · Theme 6 — Climate Resilience &
Environmental Monitoring · on the **Nokia Network-as-Code** platform · agent layer on
**LangGraph**.

```bash
python -m nabd.scene                     # the three scenes, offline, no account needed
python -m nabd.scene --scene quake -v    # every pass, including routine ones
python -m nabd.scene --runner loop       # the same scenes without LangGraph
python -m nabd.scene --backend live      # the contract run against real NaC (needs nac/.env)
python -m nabd.scene --console           # ...and rebuild nabd/replay.html, the command-centre console
python -m tests.run                      # every suite
```

## Two layers

**Detection is aggregate.** A grid of sentinel devices — municipal or operator-owned
SIMs, one per cell, never the public — is read every 30 seconds through
*Congestion Insights* and *Device Reachability*. A disaster has a signature the
network cannot hide: a contiguous block of cells whose sentinels stop answering at
once, while the ring around it goes to High as everyone calls at the same time.

**Triage is consented.** Only inside a declared footprint, and only for people who
opted in to be protected (elderly, disabled, pilgrimage groups, lone workers), the
agent asks *Device Reachability* who is unreachable and *Location Retrieval* where
they were last seen, and hands the command centre a ranked list.

## The agent does not cry wolf

One signal never drives a declaration on its own. A silent block must be
corroborated by a synchronised onset or a hot ring, must persist for a second pass,
and anything the operator's maintenance calendar already explains is removed first.
Two corroborations make a HIGH-confidence footprint, one makes MEDIUM, none is an
abstention with the reason written down.

The noise scene runs the three look-alikes — a single-cell fault, a maintenance
window, a stadium crowd — and the agent stays silent through all three, each with
its own written reason. The quake scene declares a nine-cell footprint 55 seconds
after onset and lists 6 of the 13 registered people inside it as unreachable, with
last-seen positions.

## The command centre

`nabd/replay.html` is what the room watches: one self-contained file, no server,
no network, the evidence inlined. Open it in a browser. It shows the monitored
grid as a live map (congestion, silent sentinels, the declared footprint, the
last-seen positions of the unreachable), the current verdict with its signals,
the command-centre brief, priority zones ranked by registered people unreachable,
the registry list, and the agent's log. Play a scene with <kbd>space</kbd>, step
with the arrow keys, switch scenes with 1/2/3, or deep-link a pass for a slide:
`replay.html#quake/6` is the declaration, `#quake/14` the update, `#noise/10` the
stadium crowd being held.

The console is a view over the records `log.py` writes — the map is redrawn from
the per-pass grid string in each record, the lists from the triage summary, the
log from the verdicts. Nothing on screen exists that the evidence file does not
contain, which is the answer when a judge asks whether the screen is theatre.

## What is live and what is simulated

The Network-as-Code sandbox cannot stage a disaster. So the split is explicit:

- `gateway.py` exposes one surface with two backends. `OfflineGateway` answers from
  a `World` in the platform's own vocabulary and response shapes; `LiveGateway` makes
  the same three calls through the Nokia SDK.
- The agent code is identical on both, and both record every call in the same
  `Call` shape. `--backend live` proves the contract on the account's real devices
  and writes the raw exchanges to `nac/evidence/nabd-live-contract.jsonl`, next to
  the offline scenes.

## Layout

| Module | What it owns |
|---|---|
| `model.py` | the vocabulary: cells, readings, verdicts, the registry |
| `world.py` | the offline world: grid, opt-in registry, events, maintenance calendar |
| `gateway.py` | one CAMARA surface, two backends |
| `detector.py` | the deterministic core: correlate → exclude → declare; no framework import |
| `triage.py` | per-person reachability and last-seen, inside the footprint only |
| `brief.py` | the command-centre sentence (the only place an LLM belongs) |
| `log.py` | the evidence record, JSONL and terminal |
| `loop.py` | the plain runner |
| `graph.py` | the LangGraph runner; `python -m nabd.graph` prints the topology |
| `scene.py` | the three scenes |
| `console.py` | the command-centre console, generated from the evidence into `replay.html` |

Tests: `tests/test_nabd_detector.py` (the core, plus two fuzzed invariants: no
footprint without a contiguous block; no personal-device call outside a footprint)
and `tests/test_nabd_scenes.py` (the three scenes end to end; both runners diffed
byte for byte).

## CAMARA APIs

| API | Layer |
|---|---|
| Congestion Insights | detection — per sentinel cell |
| Device Reachability Status | detection (sentinels) and triage (registry) |
| Location Retrieval | triage — last-seen position of the unreachable |
| Geofencing, Quality on Demand | roadmap — the footprint is drawn from cell geometry today |
