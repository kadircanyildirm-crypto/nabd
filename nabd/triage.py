"""Triage: who inside the footprint is unreachable, and where they were last seen.

This is the only layer that touches a personal device, and it touches only two
kinds: registry members who opted in, and only while their home cell sits inside
a declared footprint. The check is a hard invariant — `tests/test_nabd_detector`
fuzzes it — not a policy setting.

Cost-aware by construction. Reachability is one call per registered person per
pass; Location Retrieval, the expensive one, runs only for a person who has just
become unreachable and is refreshed no more than every `relocate_after_s`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nabd.model import Location, Person, Reach, TriageEntry


@dataclass
class TriageState:
    unreachable_since: dict[str, float] = field(default_factory=dict)
    located_at: dict[str, float] = field(default_factory=dict)
    locations: dict[str, Location] = field(default_factory=dict)


@dataclass(frozen=True)
class TriageResult:
    t: float
    footprint: tuple[str, ...]
    inside: int
    unreachable: int
    entries: tuple[TriageEntry, ...]  # ranked: unreachable by priority, then reachable
    calls: int

    def top(self, n: int = 3) -> tuple[TriageEntry, ...]:
        return tuple(e for e in self.entries if e.reach is Reach.UNREACHABLE)[:n]


def run(
    gateway,
    registry: tuple[Person, ...],
    footprint: tuple[str, ...],
    state: TriageState,
    t: float,
    relocate_after_s: float = 300.0,
) -> TriageResult:
    inside = set(footprint)
    before = len(gateway.calls)
    entries: list[TriageEntry] = []
    for person in registry:
        if person.home_cell not in inside:
            continue  # the invariant: nobody outside the footprint is ever queried
        reach = gateway.reachability(person.msisdn)
        if reach is Reach.UNREACHABLE:
            since = state.unreachable_since.setdefault(person.id, t)
            located = state.located_at.get(person.id)
            if located is None or t - located >= relocate_after_s:
                loc = gateway.location(person.msisdn)
                if loc is not None:
                    state.locations[person.id] = loc
                state.located_at[person.id] = t
            loc = state.locations.get(person.id)
            if loc is not None:
                # A cached position is still the last one the network has, but it
                # is older now than when it was fetched. The age must say so.
                loc = Location(loc.lat, loc.lon, loc.radius_m, loc.age_s + (t - state.located_at[person.id]))
            entries.append(TriageEntry(person.id, person.vulnerability, person.home_cell, reach, loc, since))
        else:
            state.unreachable_since.pop(person.id, None)
            state.located_at.pop(person.id, None)
            state.locations.pop(person.id, None)
            entries.append(TriageEntry(person.id, person.vulnerability, person.home_cell, reach, None, None))

    unreachable = sorted((e for e in entries if e.reach is Reach.UNREACHABLE), key=TriageEntry.rank_key)
    reachable = [e for e in entries if e.reach is not Reach.UNREACHABLE]
    return TriageResult(
        t=t,
        footprint=tuple(footprint),
        inside=len(entries),
        unreachable=len(unreachable),
        entries=tuple(unreachable + reachable),
        calls=len(gateway.calls) - before,
    )


def summary(result: TriageResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "inside": result.inside,
        "unreachable": result.unreachable,
        "calls": result.calls,
        "top": [
            {
                "person": e.person,
                "class": e.vulnerability.value,
                "cell": e.cell,
                "unreachable_since": e.unreachable_since,
                "last_seen": None
                if e.location is None
                else {"lat": e.location.lat, "lon": e.location.lon, "radius_m": e.location.radius_m, "age_s": round(e.location.age_s)},
            }
            for e in result.entries
            if e.reach is Reach.UNREACHABLE
        ],
    }
