# Nabd · نبض

**Read where the network goes silent.**

An AI agent that turns *coordinated network silence* into a live disaster-impact map
for command centres. It does not predict the earthquake. It answers the question that
costs lives in the first hours — **where is the damage worst, and who is cut off** — as
an impact map in the first minute and a ranked triage list across the first 72 hours.

Built for the **GSMA MENA Ignite Open Gateway Hackathon 2026** · Theme 6 — Climate
Resilience & Environmental Monitoring · on the **Nokia Network-as-Code** platform ·
agent layer on **LangGraph** (from the Resource & Tooling Guide).

| | |
|---|---|
| **Live demo** (command-centre console) | https://kadircanyildirm-crypto.github.io/nabd/ |
| **Demo video** | *(link in the HackerEarth submission)* |
| **Pitch deck** | [`Nabd-Pitch-Deck.pdf`](Nabd-Pitch-Deck.pdf) · [`Nabd-Project-Brief.pdf`](Nabd-Project-Brief.pdf) |
| **Team** | Kadir's Team — Kadir Can Yıldırım (solo), Türkiye |

```bash
git clone https://github.com/kadircanyildirm-crypto/nabd && cd nabd
python -m nabd.scene                     # the six scenes, offline, bare Python 3.12, nothing to install
python -m nabd.scene --scene maras       # a real one: the measured ground motion of 6 February 2023
python -m nabd.scene --scene atlas       # the second, Al Haouz 2023, on the same thresholds untouched
python -m tests.run                      # 79 tests across 10 suites, no test runner required
python -m nabd.parity                    # one agent, every backend — the seam measured, not asserted
pip install -r requirements.txt          # LangGraph (agent layer) + the Nokia NaC SDK (live backend)
python -m nabd.scene --runner graph      # the same scenes under LangGraph — evidence byte-identical
python -m nabd.scene --scene quake --llm groq   # a model phrases the brief; a guard rejects any invented number
python -m nabd.scene --console           # rebuild nabd/replay.html and docs/index.html, then open either
python -m nabd.scene --backend live      # the contract run against real Network-as-Code (needs nac/.env)
python -m nabd.scene --backend replay    # re-run that recording with no account and no network
```

---

## The problem

When the ground moves, a seismometer says *it happened* within seconds. What a command
centre needs next — **which district first, who is cut off** — arrives hours later,
assembled from phone calls, drone flights and social media. In Kahramanmaraş in 2023
that gap was measured in lives; so was Al Haouz, so was Derna.

Every existing signal answers *did it happen*. Nabd answers *who got hit, where*.

## The insight

A disaster has a signature the mobile network cannot hide: **a contiguous block of
cells goes silent at once, while the ring around it goes to High as everyone calls at
the same time.** The network already knows which area went dark. Nabd reads that
signature through standard CAMARA APIs and turns it into a footprint and a triage
list, without touching a single member of the public's device.

## Two layers

**Detection is aggregate.** A grid of *sentinel* devices — municipal or operator-owned
SIMs, one per cell, never the public — is read every 30 seconds through **Congestion
Insights** and **Device Reachability**. A contiguous block whose sentinels stop
answering is the hypothesis. It is corroborated by a synchronised onset or a hot ring,
must persist for a second pass, and anything the operator's maintenance calendar
already explains is removed first. Two corroborations make a HIGH-confidence footprint,
one makes MEDIUM, none is an abstention with the reason written down. And when the
platform itself stops answering — more than half the sentinels return no reading — the
pass is *blind*: nothing is declared, an open footprint is held rather than cleared, and
the log says the instrument failed, not the network.

**Triage is consented.** Only inside a declared footprint, and only for people who
opted in to be protected — elderly, disabled, pilgrimage groups, lone workers — the
agent asks **Device Reachability** who is unreachable and **Location Retrieval** where
they were last seen, and hands the command centre a ranked list by zone. A fuzzed
invariant guarantees no personal-device call is ever made outside a footprint.

## The agent (mandatory component)

The agent is a LangGraph graph over a pure, framework-free core:

```
sense ──▶ correlate ──▶ exclude ──▶ declare ──┬──▶ triage ──▶ brief ──▶ log
                                              └──▶ hold   ──▶ brief ──▶ log
```

`declare` ends in a **conditional edge**: triage runs only behind a declared footprint.
One signal never drives a declaration on its own, and the graph's decision is a
deterministic function of the network readings, so every run is replayable. The
LLM's place is `brief.py` — the command-centre sentence — never the detection path.
`python -m nabd.graph` prints the topology as Mermaid.

Two runners exist on purpose: the plain loop in `loop.py` and the LangGraph runner in
`graph.py`. `tests/test_nabd_scenes.py` runs every scene through both and diffs the
evidence byte for byte — the framework wraps the core rather than containing it.

## What the prototype does today

Three scenes over a 10×10 grid of cells covering Kahramanmaraş, a 48-person
pseudonymous opt-in registry, and an operator maintenance calendar. Every CAMARA call
is recorded as evidence in `nac/evidence/`.

| Scene | What happens | What the agent does |
|---|---|---|
| **Quiet** | an ordinary morning | holds — 21 passes, nothing declared |
| **Earthquake** | nine cells fall silent at once; the ring goes hot | declares a **9-cell footprint 55 s after onset, HIGH** (synchronised onset + 16/16 ring cells High); 13 registered people inside, **6 unreachable**, ranked by zone with last-seen positions; the list updates 6 → 4 as people answer |
| **Look-alikes** | a single-cell fault · a maintenance window (ticket MNT-2214) · a stadium crowd | **abstains three times**, each with its own written reason; declares nothing |

The **command-centre console** (`nabd/replay.html`, served as the live demo) is one
self-contained file: the monitored grid as a live map, the verdict and its signals, the
brief, priority zones, the registry list, the agent's log. The six scenes run as one
film: <kbd>space</kbd> plays through from wherever you are at 1×, 1.5× or 2×, each
chapter opening with a card; the strip across the top is the timeline, and clicking a
chapter jumps there. The arrow keys step, 1–6 jump, and a pass can be deep-linked:
`#quake/6` is the declaration, `#quake/14` the update, `#noise/10` the stadium crowd
being held. Nothing on screen exists that the evidence file does not contain.

## CAMARA APIs on Network-as-Code

| API | Layer | Status |
|---|---|---|
| Congestion Insights | detection — per sentinel cell | orchestrated |
| Device Reachability Status | detection (sentinels) and triage (registry) | orchestrated |
| Location Retrieval | triage — last-seen position of the unreachable | orchestrated |
| Geofencing Subscription | footprint boundary events for responders | roadmap |
| Quality on Demand | priority for responder devices inside the footprint | roadmap |
| Population Density Data | aggregate detection without sentinels | roadmap — not yet published on NaC |

*If we removed the network APIs, nothing works: the network is the sensor.* And why
CAMARA rather than an operator's own NOC: the NOC lives inside one operator, while the
responders — civil defence, Red Crescent, municipalities, hospitals — sit outside all of
them. CAMARA is the one standard, operator-independent door.

## What is live and what is simulated

The Network-as-Code sandbox cannot stage a disaster, so the split is explicit:

- `nabd/gateway.py` exposes one surface with two backends. `OfflineGateway` answers
  from a `World` in the platform's own vocabulary and response shapes; `LiveGateway`
  makes the same three calls through the Nokia SDK.
- The agent code is identical on both, and both record every call in the same `Call`
  shape. `--backend live` proves the contract on real simulator devices and writes the
  raw exchanges to `nac/evidence/nabd-live-contract.jsonl`, next to the offline scenes.
- The disaster itself is staged offline, shaped on the public record of the 2023
  Kahramanmaraş outage, through the same code path the live backend uses.

To run live: register at `networkascode.nokia.io`, copy `nac/.env.example` to
`nac/.env`, fill in `NAC_API_KEY` and a few simulator MSISDNs in `NAC_MSISDNS`.

## Privacy

Detection never touches the public: sentinels are municipal or operator-owned SIMs,
and the footprint is an area, not a list of people. Triage is opt-in only, the registry
is pseudonymous (`R-022`, not a name), the agency holds it and the operator honours it,
and the agent may only query it inside a declared footprint — enforced by a test that
fuzzes thousands of worlds looking for a violation.

## Impact and scale

One engine, many hazards: earthquake, flood, storm, wildfire, mass outage — each is
*an area going dark*. Buyers are civil-defence agencies and municipalities; the
operator sells the impact feed as an Open Gateway product; sentinel SIMs cost what a
municipality already pays for its IoT, and the system scales by cell count, not by
population. Roadmap: Geofencing for boundary events, QoD priority for responders inside
the footprint, Population Density Data for sentinel-free detection once it ships on
Network-as-Code.

## Layout

```
nabd/       model      the vocabulary: cells, readings, verdicts, the registry
            world      the offline world: grid, opt-in registry, events, maintenance calendar
            gateway    one CAMARA surface, two backends (offline | live)
            detector   the deterministic core: correlate → exclude → declare — no framework import
            triage     per-person reachability and last-seen, inside the footprint only
            brief      the command-centre sentence (the only place an LLM belongs)
            log        the evidence record → terminal, JSONL, console
            loop       the plain runner
            graph      the LangGraph runner (mandatory tooling); python -m nabd.graph prints the topology
            scene      the six scenes, --backend, --runner, --console
            shakemap   the measured intensity field for 6 Feb 2023, and what the outage model assumes
            parity     the backend-parity harness: one agent, three backends, four checks
            console    the command-centre console → nabd/replay.html and docs/index.html
nabd/data/  the committed ShakeMap extracts (two events) and the scripts that produced them
nac/        client.py (Nokia SDK wiring), evidence/ (every recorded call), .env.example
tests/      run.py + test_nabd_{detector,scenes,parity,real,live_wiring}.py
docs/       index.html (live demo), nabd-deck.html (the deck), snapshots/,
            video/ (cards.html, build.py and the generated shot-list.md)
```

Tests, in the order a reviewer should read them: `test_nabd_detector.py` (the core,
plus two fuzzed invariants: no footprint without a contiguous block; no personal-device
call outside a footprint), `test_nabd_scenes.py` (the six scenes end to end, both
runners diffed byte for byte, the privacy count reconciled against the raw calls),
`test_nabd_parity.py` (one agent on every backend, proven by replay),
`test_nabd_real.py` (the agent against two earthquakes that happened, plus
provenance assertions so the data cannot drift from the claims made about it — and
`test_nothing_was_retuned_for_the_second_event`, which is what makes Al Haouz a
held-out test rather than a second calibration) and
`test_nabd_live_wiring.py` (the live path resolved against the installed Nokia SDK
without spending a call), `test_nabd_llm.py` (the model's guard: a sentence with an invented
number is thrown away) and `test_nabd_false_alarm.py` (0 of 90 ordinary mornings declared under
1–3% random sentinel dropout, and the edge near 5% written down). `python -m tests.run` → 79/79
across 7 suites.

## Where the data comes from

**The world is real; the network is simulated.** Every geographic and seismic
fact on screen is a published dataset committed with its product URL and
retrieval date — OpenStreetMap, Natural Earth, GeoNames, and the USGS ShakeMaps
for Kahramanmaraş 2023 and Al Haouz 2023. Every network reading comes from a
simulator, and the console says `backend offline simulator` on every frame.

[`docs/PROVENANCE.md`](docs/PROVENANCE.md) sets it out line by line — what is
real, what is ours, what is not done yet — and `tests/test_nabd_provenance.py`
enforces it: no figure reaches the narration that the scene it is showing, or a
written source, cannot back.

## Questions a jury will ask

**Did you actually call Nokia's APIs?** Yes — the contract run is recorded. On 10 September
2026, `python -m nabd.scene --backend live` ran the same agent against Nokia Network-as-Code in
Simulator mode: **18 of 18 calls answered**, and the raw exchanges are committed in
`nac/evidence/nabd-live-contract.jsonl`. `python -m nabd.parity` now reports **4/4**, and its
fourth check is the one anyone can repeat — it replays that transcript through the same agent
**with no credentials at all**. Before the run it reported PENDING and never PASS; nothing in
this repository has ever claimed a live call that was not made.

**Where is the language model?** In one node — the brief — and nowhere else. Bind it with
`--llm groq` (or Gemini, OpenRouter, Ollama; one client, no wheel). A guard reads its sentence
back against the facts it was given and throws away any sentence in which it invents a number.
Offline, the same facts render through a template, so the demo never waits on a network.

**Isn't a sentinel per cell a huge deployment?** No — the sentinels already exist. Operators
and municipalities run fixed SIMs in meters, traffic lights, pumps, ATMs and site monitors; a
sentinel is one such device per cell, opted in by its owner. Watching all of Türkiye is 7,836 of
them, not 85 million people, and the bill scales with land area and cadence.

**What is the false-alarm rate?** Four shaped look-alikes get four written abstentions. Under
random sentinel dropout — the plainer case — **0 of 90 ordinary mornings** are declared at 1–3%
per pass; around 5% the floor becomes marginal, and that edge is written down as a deployment
requirement rather than hidden.

**Was the detector tuned to the one event you show?** It was calibrated on Kahramanmaraş and
then run, untouched, on Al Haouz — a different country, terrain and magnitude. It declares
later there, at MEDIUM, for a reason that is in the evidence, and it never names Marrakesh.
`test_nothing_was_retuned_for_the_second_event` keeps that true.

**Why CAMARA and not the operator's own NOC?** Responders sit outside every operator and
cannot log into three of them in the middle of a disaster. Open Gateway is the one standard,
operator-independent door — and it is how the same agent moves between countries.

**Who consents, and to what?** Detection never touches a member of the public. Triage touches
only people who opted in, only inside a declared footprint, and every evidence line says how
many personal calls it made — zero on a quiet day. The register is held by the agency and
honoured by the operator, the model that needs the fewest parties to coordinate.

## Compliance

- **CAMARA APIs on Nokia Network-as-Code:** Congestion Insights, Device Reachability
  Status, Location Retrieval — all three on the platform's published API list.
- **AI agent layer:** LangGraph, from the Resource & Tooling Guide; no other agent
  tooling. Python 3.12 standard library elsewhere.
- **Original code**, written during the hackathon window. Theme 6.

## License

Intellectual property belongs to the team, per hackathon rules. Not licensed for reuse.
