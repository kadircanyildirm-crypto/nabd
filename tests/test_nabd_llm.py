"""The language model, and the guard that keeps it to phrasing.

    python -m tests.test_nabd_llm

No network here. A model is stood in for by small functions that behave the
way models behave — faithfully, or with a number of their own — and the guard
is checked against each. The contract under test is the one the whole design
rests on: the model may phrase the facts of a pass and may never add to them.
"""

from __future__ import annotations

import io

from nabd import llm
from nabd.brief import compose, facts, template
from nabd.model import Confidence, Kind, Verdict
from nabd.scene import build

GRID = build("quake").world.grid
DECLARE = Verdict(
    Kind.DECLARE, 180.0, ("E5", "E6", "F5", "F6"), Confidence.HIGH,
    reason="impact footprint declared: 4 contiguous cells, ~1.8 km²",
    signals=("Device Reachability: 4 contiguous cells unreachable (~1.8 km²)", "hot ring: 12/12 neighbouring cells at High congestion"),
)


def test_the_template_and_the_model_are_given_the_same_facts():
    """One facts dict feeds both, so a rejected sentence falls back to the same numbers."""
    f = facts(DECLARE, None, GRID)
    assert f["cells"] == ["E5", "E6", "F5", "F6"] and f["confidence"] == "HIGH"
    assert compose(DECLARE, None, GRID) == template(f)
    assert "4 cells" in template(f) and "HIGH" in template(f)


def test_a_faithful_sentence_passes_the_guard():
    def model(f):
        return f"Impact declared over {len(f['cells'])} cells near {f['centre']['lat']:.4f}N, confidence {f['confidence']}."

    out = io.StringIO()
    text = llm.guarded(model, name="fake", report=out)(facts(DECLARE, None, GRID))
    assert text.startswith("Impact declared over 4 cells"), text
    assert out.getvalue() == "", out.getvalue()


def test_an_invented_number_is_rejected_and_the_template_speaks():
    """The model says twelve cells; the facts say four. Its sentence is thrown away."""
    def model(f):
        return "Impact declared over 12 cells, roughly 5.5 km², confidence HIGH."

    out = io.StringIO()
    f = facts(DECLARE, None, GRID)
    text = llm.guarded(model, name="fake", report=out)(f)
    assert text == template(f), text
    # 12 is allowed — it is in the hot-ring signal — so the number named is 5.5.
    assert "rejected" in out.getvalue() and "5.5" in out.getvalue(), out.getvalue()


def test_an_invented_person_is_rejected():
    """Person ids are numbers too: R-099 was never in the registry facts."""
    from nabd.scene import run

    scenario = build("quake")
    log, _ = run(scenario, runner="loop")
    rec = next(r for r in log.records if r.kind == Kind.DECLARE.value and r.triage)
    allowed_people = {e["person"] for e in rec.triage["top"]}

    def model(f):
        first = f["registry"]["first"][0]["person"]
        return f"Reach {first} first, then R-099."

    f = {"kind": "DECLARE", "t": rec.t, "cells": list(rec.cells), "confidence": rec.confidence, "reason": "", "signals": [],
         "area_km2": 4.0, "centre": {"lat": 37.5, "lon": 36.9},
         "registry": {"inside": rec.triage["inside"], "unreachable": rec.triage["unreachable"],
                      "first": [{"person": p, "class": "elderly", "cell": "E6", "last_seen_age_s": 120, "radius_m": 900} for p in sorted(allowed_people)[:1]]}}
    out = io.StringIO()
    text = llm.guarded(model, name="fake", report=out)(f)
    assert text == template(f)
    assert "R-099" in out.getvalue(), out.getvalue()


def test_a_model_that_fails_is_a_template_not_a_crash():
    def model(f):
        raise ConnectionError("no route to host")

    out = io.StringIO()
    f = facts(DECLARE, None, GRID)
    assert llm.guarded(model, name="fake", report=out)(f) == template(f)
    assert "unavailable" in out.getvalue()


def test_the_numbers_a_sentence_may_use_come_only_from_the_facts():
    f = facts(DECLARE, None, GRID)
    allowed = llm.numbers_of(f)
    assert {"4", "HIGH"} & (allowed | {"HIGH"})  # the count is derivable; words are not numbers
    assert "4" in allowed and "1.8" in allowed and "E5" in allowed and "12" in allowed
    assert "99" not in allowed and "7" not in allowed


def test_every_approved_provider_is_reachable_by_one_client():
    """Four routes, one shape: nothing to install and one function to read."""
    assert set(llm.PROVIDERS) == {"groq", "gemini", "openrouter", "ollama"}
    for name, (url, key, model) in llm.PROVIDERS.items():
        assert url.endswith("/chat/completions"), url
        assert model
    # The two that need a key say so, by name, instead of failing later.
    import os

    for name in ("groq", "gemini", "openrouter"):
        os.environ.pop(llm.PROVIDERS[name][1], None)
        try:
            llm.chat(name)
        except RuntimeError as exc:
            assert llm.PROVIDERS[name][1] in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{name} accepted no key")


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_llm"]))
