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
python -m nabd.scene                     # the four scenes, offline, no account needed
python -m nabd.scene --scene quake -v    # every pass, including routine ones
python -m nabd.scene --runner loop       # the same scenes without LangGraph
python -m nabd.scene --backend live      # the contract run against real NaC (needs nac/.env)
python -m nabd.scene --backend replay    # re-run the recorded live transcript, no account, no network
python -m nabd.scene --console           # ...and rebuild nabd/replay.html, the command-centre console
python -m nabd.parity                    # prove one agent runs on every backend
python -m tests.run                      # every suite
```

## Two layers

**Detection is aggregate.** A grid of sentinel devices — municipal or operator-owned
SIMs, one per cell, never the public — is read every 30 seconds through
*Congestion Insights* and *Device Reachability*. A disaster has a signature the
network cannot hide: a contiguous block of cells whose sentinels stop answering at
once, while the ring around it goes to High as everyone calls at the same time.

The sentinel mesh is not decoration. The CAMARA endpoints that reached stable
release are device-scoped — you ask about a device, not about an area — so a
sentinel per cell is how an area-level reading is built from the APIs that
actually ship. It is also what makes the anonymous layer genuinely anonymous: the
detection path never queries a member of the public, and that is a property of
the device list rather than a promise. And a fixed device is the better sensor —
a handset that stops answering may have moved or gone flat; a traffic cabinet did
not walk away.

**Triage is consented.** Only inside a declared footprint, and only for people who
opted in to be protected (elderly, disabled, pilgrimage groups, lone workers), the
agent asks *Device Reachability* who is unreachable and *Location Retrieval* where
they were last seen, and hands the command centre a ranked list.

## The agent does not cry wolf

The question that decides whether this is useful is not *can an outage be seen* —
it is *can a disaster footprint be told apart from every other reason cells go
quiet*. So nothing rests on one signature being right. What the detector rests on
is the **minimum observable pattern**: a contiguous block of cells that stops
answering together, in a place where that is not normal. Everything else is
corroboration.

| Signal | Role | Read from |
|---|---|---|
| contiguous silence | **gate** — a connected block at or above the size floor | Device Reachability |
| local baseline | **gate** — silence must be abnormal *here*, against these cells' own history | Device Reachability |
| synchronised onset | corroboration — the block went dark inside one window | Device Reachability |
| hot ring | corroboration — the surviving ring saturates as everyone calls at once | Congestion Insights |

A gate can veto a declaration but never cause one; a corroboration can raise
confidence but never carry it alone. Two corroborations make a HIGH-confidence
footprint, one makes MEDIUM, none is an abstention with the reason written down —
and a candidate must survive a second pass before it is published. Anything the
operator's maintenance calendar explains is removed before the geometry is
computed.

`CORROBORATIONS` in `detector.py` is a tuple of small named functions, and the
verdict arithmetic counts it. Adding a network surface — a real aggregate API,
when Open Gateway ships one — is an append to that tuple, not a redesign. That is
the whole reason the evidence is structured rather than a list of strings.

**Four look-alikes, demonstrated rather than asserted.** The noise scene runs
three of them in one morning — a single-cell fault, a maintenance window, a
stadium crowd — and the agent stays silent through all three, each with its own
written reason. The degraded scene runs the hardest one: a block on a failing
backhaul that reproduces *every* signal an impact has, including a synchronised
onset, and that no calendar explains. The first flaps are held for confirmation
and die before it is due; once the agent has measured the block it refuses it
outright, with the number it measured — *these four cells were already
unreachable in 3 of the last 11 passes*. Then a real earthquake hits the city
centre in the same run, and is declared 30 seconds after onset while the flaky
block stays held. The refusal is not blindness, and that is checked by a test.

The quake scene declares a nine-cell footprint 55 seconds after onset and lists 6
of the 13 registered people inside it as unreachable, with last-seen positions.

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

## What is live and what is simulated — and why the seam is checkable

The Network-as-Code sandbox cannot stage a disaster. So the two claims are
separated rather than blurred: **the live platform proves the integration, the
simulator proves the scenario.** The risk in that split is not the simulator — it
is a reader suspecting a discontinuity between the two paths. So the seam is
measured, not asserted.

`gateway.py` exposes one surface with three backends: `OfflineGateway` answers
from a `World` in the platform's own vocabulary and response shapes, `LiveGateway`
makes the same three calls through the Nokia SDK, and `ReplayGateway` serves a
recorded transcript. All three read every response through the *same three
parsing functions* — `parse_congestion`, `parse_reachability`, `parse_location` —
which is the mechanism the whole claim rests on.

`python -m nabd.parity` runs the four checks and writes
`nac/evidence/nabd-parity.md`:

1. **The agent cannot see the backend.** Every module between a response and a
   decision is parsed and checked to import no SDK, construct no gateway and name
   no simulated world. Read from the syntax tree, so a docstring that mentions a
   backend does not count as using one.
2. **One function chooses the network.** `gateway.build()` names all three
   backends; nothing else in the package names any of them.
3. **The live parsers read the simulator's bytes.** Every scene is recorded and
   replayed through `ReplayGateway`, and the evidence has to come out identical
   line for line. If the simulator answered in a shape the live code could not
   read, this fails.
4. **The live transcript replays with no account.** `--backend live` writes the
   raw exchanges to `nac/evidence/nabd-live-contract.jsonl`; `--backend replay`
   runs the same agent back over them offline. Until that file exists the check
   reports PENDING — never PASS.

## The privacy boundary is a number, not a paragraph

Three independent guarantees, in increasing order of how little they ask you to
trust:

- **Topology.** In `graph.py` the `triage` node — the only node that queries a
  personal device — is reachable only from a verdict with an active footprint.
  `render_mermaid()` prints that from the graph that actually runs.
- **Fuzzing.** `tests/test_nabd_detector` drives thousands of random passes and
  checks that every personal-device call belongs to a registered person whose
  home cell is inside the footprint.
- **Counting.** Every record in the evidence file carries a `privacy` block
  saying whether the personal-data path was open on that pass and how many
  personal calls it made. On an ordinary morning that number is zero on every
  line, and the console states it on screen for the pass being shown.

The at-risk register itself is a **stated assumption**: the disaster agency holds
it and operators honour it. That model needs the fewest parties to coordinate,
puts accountability where the duty of care already sits, is the easiest to explain
to a citizen, and is the only one that still works when the people inside one
footprint are spread across three networks. Building the demonstration around
emergency legal powers was deliberately avoided.

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
| `scene.py` | the four scenes |
| `parity.py` | the backend-parity harness: one agent, three backends, four checks |
| `console.py` | the command-centre console, generated from the evidence into `replay.html` |

Tests: `tests/test_nabd_detector.py` (the core, plus two fuzzed invariants: no
footprint without a contiguous block; no personal-device call outside a
footprint), `tests/test_nabd_scenes.py` (the four scenes end to end; both runners
diffed byte for byte; the privacy count reconciled against the raw calls) and
`tests/test_nabd_parity.py` (the parity checks as assertions, so a second code
path fails the build rather than degrading a paragraph in a report).

## CAMARA APIs

| API | Layer |
|---|---|
| Congestion Insights | **core** — detection: the ring around a silent block |
| Device Reachability Status | **core** — detection (sentinels) and triage (registry) |
| Location Retrieval | **core** — triage: last-seen position of the unreachable |
| Geofencing, Quality on Demand | roadmap — the footprint is drawn from cell geometry today |

Three APIs, each load-bearing: remove any one and Nabd stops answering the
question it exists to answer. The other two are named as a roadmap rather than
built — a small number of APIs at the centre of the value proposition beats a
longer list only loosely attached to it.
