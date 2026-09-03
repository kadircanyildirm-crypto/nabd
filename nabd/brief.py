"""The command-centre sentence.

The detection path is deterministic end to end; this is the one place a language
model belongs, because turning a decision record into a sentence an exhausted
duty officer can read is a job where being wrong costs a sentence. The facts the
sentence is built from are computed here and handed over as a dict — the model
may phrase them, never invent them. With no model bound, the same facts render
through a fixed template, so the offline demo never waits on a network.
"""

from __future__ import annotations

from typing import Any, Callable

from nabd.model import Grid, Kind, Reach, Verdict
from nabd.triage import TriageResult

Composer = Callable[[dict[str, Any]], str]


def facts(verdict: Verdict, triage: TriageResult | None, grid: Grid) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": verdict.kind.value,
        "t": verdict.t,
        "cells": list(verdict.cells),
        "confidence": None if verdict.confidence is None else verdict.confidence.value,
        "reason": verdict.reason,
        "signals": list(verdict.signals),
    }
    if verdict.cells:
        lat, lon = grid.centroid(verdict.cells)
        out["area_km2"] = grid.area_km2(len(verdict.cells))
        out["centre"] = {"lat": round(lat, 4), "lon": round(lon, 4)}
    if triage is not None:
        out["registry"] = {
            "inside": triage.inside,
            "unreachable": triage.unreachable,
            "first": [
                {
                    "person": e.person,
                    "class": e.vulnerability.value,
                    "cell": e.cell,
                    "last_seen_age_s": None if e.location is None else round(e.location.age_s),
                    "radius_m": None if e.location is None else e.location.radius_m,
                }
                for e in triage.top(3)
            ],
        }
    return out


def compose(verdict: Verdict, triage: TriageResult | None, grid: Grid, llm: Composer | None = None) -> str:
    f = facts(verdict, triage, grid)
    if llm is not None:
        return llm(f)
    kind = verdict.kind
    if kind is Kind.QUIET:
        return ""
    if kind is Kind.CANDIDATE:
        return (
            f"Possible impact footprint over {len(verdict.cells)} cells "
            f"({verdict.cells[0]}–{verdict.cells[-1]}); holding one pass for confirmation before alerting."
        )
    if kind is Kind.ABSTAIN:
        return f"No alert. {verdict.reason}."
    if kind is Kind.CLEAR:
        return "Footprint cleared: every cell is answering again."
    if kind in (Kind.DECLARE, Kind.UPDATE):
        head = "Impact footprint declared" if kind is Kind.DECLARE else "Footprint updated"
        c = f["centre"]
        text = (
            f"{head}: {len(verdict.cells)} cells, about {f['area_km2']} km², "
            f"centred {c['lat']:.4f}N {c['lon']:.4f}E, confidence {f['confidence']}. "
            f"Signals: {'; '.join(verdict.signals)}."
        )
        return text + _registry_sentence(triage)
    # SUSTAIN
    return f"Footprint holds ({len(verdict.cells)} cells)." + _registry_sentence(triage)


def _registry_sentence(triage: TriageResult | None) -> str:
    if triage is None:
        return ""
    if triage.inside == 0:
        return " No registered people inside the footprint."
    text = f" Registry: {triage.inside} opted-in people inside, {triage.unreachable} unreachable."
    first = triage.top(3)
    if first:
        parts = []
        for e in first:
            seen = ""
            if e.location is not None:
                seen = f", last seen {_age(e.location.age_s)} ago within {e.location.radius_m} m"
            parts.append(f"{e.person} ({e.vulnerability.value}, {e.cell}{seen})")
        text += " First to reach: " + "; ".join(parts) + "."
    return text


def _age(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.0f} min"
