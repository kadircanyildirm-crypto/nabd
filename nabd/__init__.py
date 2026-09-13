"""Nabd — read where the network goes silent.

An agent that turns coordinated network silence into a disaster-impact map for
command centres. Two layers: aggregate detection over a grid of sentinel devices
(no personal device is ever touched), and consented triage for an opt-in registry
of vulnerable people, run only inside a declared footprint.

    python -m nabd.scene            # the three scenes, offline, no account needed
    python -m nabd.scene --console  # ...and rebuild replay.html, the command-centre console
    python -m tests.run             # every suite

Modules, in the order a reviewer should read them:

    model      the vocabulary: cells, readings, verdicts, the registry
    world      the offline simulator's world: grid, events, maintenance calendar
    gateway    one CAMARA surface, two backends (offline simulator, live NaC)
    detector   the deterministic core: correlate → exclude → declare
    triage     per-person reachability and last-seen, inside the footprint only
    brief      the command-centre sentence
    log        the evidence record, JSONL and terminal
    loop       the plain runner (no framework)
    graph      the LangGraph runner (the mandatory agent layer)
    scene      the demonstration
    console    the command-centre console, one HTML file generated from the evidence
"""
