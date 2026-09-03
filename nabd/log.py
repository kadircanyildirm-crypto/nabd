"""The evidence record: what the command centre sees and the jury reads.

Every verdict is written with the signals that produced it and the CAMARA calls
that fed it. Two renderings from one record — JSONL for the evidence file, a
terminal view for the live run — and the console renders the same records, so
nothing on screen exists that the evidence file does not also contain.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from nabd.model import Grid, Kind, Level, Reach, Snapshot, Verdict
from nabd.triage import TriageResult, summary as triage_summary

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "nac" / "evidence"

_GLYPH = {
    Kind.QUIET: "·",
    Kind.CANDIDATE: "?",
    Kind.DECLARE: "!",
    Kind.UPDATE: "▲",
    Kind.SUSTAIN: "·",
    Kind.ABSTAIN: "—",
    Kind.CLEAR: "✓",
}


def clock(t: float) -> str:
    from nabd.gateway import EPOCH

    return (EPOCH + timedelta(seconds=t)).strftime("%H:%M:%S")


# One character per cell, row-major, so the console can redraw the map from the
# evidence alone: '.' low, 'm' medium, 'H' high, 'D' sentinel unreachable, 'x' unmonitored.
def grid_string(snapshot: Snapshot, grid: Grid) -> str:
    out = []
    for cell in grid.cells:
        reading = snapshot.get(cell.id) if cell.sentinel else None
        if reading is None:
            out.append("x")
        elif reading.reach is Reach.UNREACHABLE:
            out.append("D")
        elif reading.congestion is Level.HIGH:
            out.append("H")
        elif reading.congestion is Level.MEDIUM:
            out.append("m")
        else:
            out.append(".")
    return "".join(out)


@dataclass
class Record:
    t: float
    kind: str
    cells: list[str]
    confidence: str | None
    reason: str
    signals: list[str]
    triage: dict[str, Any] | None
    api_calls: list[str] = field(default_factory=list)
    brief: str = ""
    grid: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def record_from(
    verdict: Verdict, triage: TriageResult | None, api_calls: list[str], brief: str, grid: str = ""
) -> Record:
    return Record(
        t=round(verdict.t, 1),
        kind=verdict.kind.value,
        cells=list(verdict.cells),
        confidence=None if verdict.confidence is None else verdict.confidence.value,
        reason=verdict.reason,
        signals=list(verdict.signals),
        triage=triage_summary(triage),
        api_calls=list(api_calls),
        brief=brief,
        grid=grid,
    )


class EvidenceLog:
    def __init__(self, name: str) -> None:
        self.name = name
        self.records: list[Record] = []

    def add(self, record: Record) -> Record:
        self.records.append(record)
        return record

    # -- rendering ----------------------------------------------------------

    def render(self, record: Record, verbose: bool = False) -> str:
        kind = Kind(record.kind)
        head = f"  {clock(record.t)}  {_GLYPH[kind]} {record.kind:<9}"
        routine = kind in (Kind.QUIET, Kind.SUSTAIN)
        changed = self._registry_change(record)
        if routine and not verbose and changed is None:
            # Routine passes collapse to one line so the moments that matter are
            # the ones visible on stage. A held abstention still says it is held.
            if record.reason.startswith("holding"):
                return f"{head} held"
            return head.rstrip()

        reason = record.reason
        if changed is not None:
            before, after = changed
            reason = f"{reason} — registry: {before} → {after} unreachable"
        lines = [f"{head} {reason}"]
        for signal in record.signals:
            lines.append(f"              ├─ {signal}")
        if record.triage:
            tri = record.triage
            lines.append(f"              ├─ registry: {tri['inside']} inside, {tri['unreachable']} unreachable")
            for entry in tri["top"][:3]:
                seen = entry["last_seen"]
                where = "" if seen is None else f", last seen {seen['age_s']}s ago ±{seen['radius_m']} m"
                lines.append(f"              │    {entry['person']}  {entry['class']:<18} {entry['cell']}{where}")
        if record.api_calls:
            counted: dict[str, int] = {}
            for name in record.api_calls:
                counted[name] = counted.get(name, 0) + 1
            lines.append("              └─ CAMARA: " + ", ".join(f"{n}×{c}" for n, c in counted.items()))
        elif len(lines) > 1:
            lines[-1] = lines[-1].replace("├─", "└─")
        if record.brief and kind in (Kind.DECLARE, Kind.UPDATE, Kind.CLEAR):
            lines.append(f"              » {record.brief}")
        return "\n".join(lines)

    def _registry_change(self, record: Record) -> tuple[int, int] | None:
        """(before, after) when this pass changed the unreachable count, else None.

        A sustained footprint is routine; a person answering again inside it is
        not, and it must surface on stage without an operator touching anything.
        """
        if not record.triage:
            return None
        previous = None
        for earlier in self.records:
            if earlier is record:
                break
            if earlier.triage:
                previous = earlier
        if previous is None:
            return None
        before, after = previous.triage["unreachable"], record.triage["unreachable"]
        return None if before == after else (before, after)

    # -- summary --------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        declared = next((r for r in self.records if r.kind == Kind.DECLARE.value), None)
        abstains = [r for r in self.records if r.kind == Kind.ABSTAIN.value]
        unreachable = [r.triage["unreachable"] for r in self.records if r.triage]
        return {
            "name": self.name,
            "passes": len(self.records),
            "declared_at": None if declared is None else declared.t,
            "footprint_cells": None if declared is None else len(declared.cells),
            "confidence": None if declared is None else declared.confidence,
            "updates": sum(1 for r in self.records if r.kind == Kind.UPDATE.value),
            "abstains": [r.reason for r in abstains],
            "unreachable_peak": max(unreachable) if unreachable else 0,
            "api_calls": sum(len(r.api_calls) for r in self.records),
        }

    def write(self, name: str | None = None) -> Path:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE_DIR / f"{name or self.name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for record in self.records:
                fh.write(record.to_json() + "\n")
        return path
