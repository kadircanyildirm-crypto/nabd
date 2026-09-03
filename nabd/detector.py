"""The deterministic core: correlate → exclude → declare.

Three pure functions and one mutation, with no framework import anywhere. The
LangGraph runner in `nabd/graph.py` calls them as three nodes; the plain runner
in `nabd/loop.py` calls them in a row. Both produce byte-identical evidence,
which is how "the framework wraps the core rather than containing it" is a diff
rather than a slide.

The claim the core has to earn is not "it detects" but "it does not cry wolf".
So one signal never drives a declaration on its own:

* silence is the hypothesis — a contiguous block of monitored cells whose
  sentinels stop answering (Device Reachability);
* it must be corroborated by at least one of: a synchronised onset (all cells
  went dark inside one window) or a hot ring (the cells around the block at
  High congestion as everyone calls at once — Congestion Insights);
* it must persist for `confirm_passes` before it is published;
* and anything the maintenance calendar already explains is removed first.

Two corroborations make a HIGH-confidence footprint, one makes MEDIUM, none is
an abstention with the reason written down. A single dark cell, a block that
matches a maintenance ticket, and congestion without silence each end in an
abstention, and the noise scene runs all three.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from nabd.model import Confidence, Grid, Kind, Level, Maintenance, Reach, Snapshot, Verdict


@dataclass(frozen=True)
class Policy:
    min_cells: int = 3
    confirm_passes: int = 2
    sync_window_s: float = 120.0
    ring_hot_fraction: float = 0.4
    clear_after_s: float = 600.0
    pass_interval_s: float = 30.0


DEFAULT_POLICY = Policy()


@dataclass
class State:
    """Everything the detector remembers between passes."""

    dark_since: dict[str, float] = field(default_factory=dict)
    candidate: tuple[str, ...] = ()
    candidate_passes: int = 0
    footprint: tuple[str, ...] = ()
    declared_at: float | None = None
    confidence: Confidence | None = None
    clear_since: float | None = None
    explained: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Correlation:
    """What the pass looks like once the readings are laid on the grid."""

    t: float
    monitored: tuple[str, ...]
    dark: tuple[str, ...]  # sentinel unreachable
    hot: tuple[str, ...]  # High congestion
    unread: tuple[str, ...]  # Congestion Insights returned nothing
    dark_clusters: tuple[tuple[str, ...], ...]
    hot_clusters: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Exclusion:
    """The same picture with the explained silence removed."""

    maintenance: dict[str, str]  # cell -> ticket
    clusters: tuple[tuple[str, ...], ...]  # dark clusters after exclusion
    notes: tuple[str, ...]


# ----------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------


def clusters(cells: tuple[str, ...] | list[str], grid: Grid) -> tuple[tuple[str, ...], ...]:
    """Connected components under eight-way adjacency, largest first."""
    pending = set(cells)
    out: list[tuple[str, ...]] = []
    for start in cells:
        if start not in pending:
            continue
        seen = {start}
        queue = deque([start])
        pending.discard(start)
        while queue:
            current = queue.popleft()
            for n in grid.neighbours(current):
                if n in pending:
                    pending.discard(n)
                    seen.add(n)
                    queue.append(n)
        out.append(tuple(sorted(seen, key=_grid_key(grid))))
    out.sort(key=lambda c: (-len(c), c))
    return tuple(out)


def _grid_key(grid: Grid):
    def key(cell_id: str) -> tuple[int, int]:
        c = grid.by_id(cell_id)
        return (c.row, c.col)

    return key


# ----------------------------------------------------------------------------
# The three stages
# ----------------------------------------------------------------------------


def correlate(snapshot: Snapshot, grid: Grid, t: float) -> Correlation:
    monitored = tuple(c.id for c in grid.monitored() if c.id in snapshot)
    dark = tuple(c for c in monitored if snapshot[c].reach is Reach.UNREACHABLE)
    hot = tuple(c for c in monitored if snapshot[c].congestion is Level.HIGH)
    unread = tuple(c for c in monitored if snapshot[c].congestion is Level.UNKNOWN)
    return Correlation(
        t=t,
        monitored=monitored,
        dark=dark,
        hot=hot,
        unread=unread,
        dark_clusters=clusters(dark, grid),
        hot_clusters=clusters(hot, grid),
    )


def exclude(corr: Correlation, grid: Grid, calendar: tuple[Maintenance, ...], t: float) -> Exclusion:
    explained: dict[str, str] = {}
    for cell in corr.dark:
        for m in calendar:
            if m.covers(cell, t):
                explained[cell] = m.ticket
                break
    remaining = tuple(c for c in corr.dark if c not in explained)
    notes = []
    if explained:
        tickets = sorted(set(explained.values()))
        notes.append(f"{len(explained)} silent cell(s) fall inside maintenance ticket(s) {', '.join(tickets)}")
    return Exclusion(maintenance=explained, clusters=clusters(remaining, grid), notes=tuple(notes))


def declare(
    corr: Correlation,
    excl: Exclusion,
    state: State,
    grid: Grid,
    policy: Policy,
    t: float,
) -> Verdict:
    """The verdict for this pass. Pure: reads `state`, never writes it."""
    lead = excl.clusters[0] if excl.clusters else ()

    # -- an active footprint: sustain, update or clear -------------------------
    if state.footprint and len(lead) < policy.min_cells:
        back = [c for c in state.footprint if c not in corr.dark]
        if len(back) == len(state.footprint):
            since = state.clear_since if state.clear_since is not None else t
            if t - since >= policy.clear_after_s:
                return Verdict(
                    Kind.CLEAR, t, state.footprint,
                    reason=f"all {len(state.footprint)} footprint cells reachable for {t - since:.0f}s — footprint cleared",
                )
            return Verdict(
                Kind.SUSTAIN, t, state.footprint, state.confidence,
                reason=f"footprint held: all cells reachable again for {t - since:.0f}s, clearing at {policy.clear_after_s:.0f}s",
            )
        return Verdict(
            Kind.SUSTAIN, t, state.footprint, state.confidence,
            reason=f"footprint held: {len(state.footprint) - len(back)}/{len(state.footprint)} cells still silent",
        )

    # -- the hypothesis: a block of silent cells -------------------------------
    if len(lead) >= policy.min_cells:
        signals, corroborations = _signals(lead, corr, state, grid, policy, t)
        if corroborations == 0:
            key = f"uncorroborated|{','.join(lead)}"
            reason = (
                f"{len(lead)} contiguous cells silent but nothing corroborates an impact: "
                "onset staggered and no hot ring — held, not declared"
            )
            if key in state.explained:
                return Verdict(Kind.QUIET, t, lead, reason=f"holding: {reason}", key=key)
            return Verdict(Kind.ABSTAIN, t, lead, reason=reason, signals=signals, key=key)
        confidence = Confidence.HIGH if corroborations >= 2 else Confidence.MEDIUM
        passes = _passes(lead, state)
        if passes < policy.confirm_passes:
            return Verdict(
                Kind.CANDIDATE, t, lead, confidence,
                reason=f"candidate footprint, {len(lead)} cells — holding {policy.confirm_passes - passes} more pass for confirmation",
                signals=signals,
            )
        if not state.footprint:
            return Verdict(
                Kind.DECLARE, t, lead, confidence,
                reason=f"impact footprint declared: {len(lead)} contiguous cells, ~{grid.area_km2(len(lead))} km²",
                signals=signals,
            )
        if set(lead) != set(state.footprint):
            grown = len(set(lead) - set(state.footprint))
            shrunk = len(set(state.footprint) - set(lead))
            return Verdict(
                Kind.UPDATE, t, lead, confidence,
                reason=f"footprint updated: +{grown} / -{shrunk} cells, now {len(lead)}",
                signals=signals,
            )
        return Verdict(Kind.SUSTAIN, t, lead, confidence, reason="footprint held", signals=signals)

    # -- anomalies below the bar: each one explained once, none of them hidden --
    # Every explained anomaly is reported the first time it is seen and held
    # quietly afterwards; a held one must never mask a new one, which is why
    # this collects all of them and returns the first that is still unreported.
    found: list[tuple[tuple[str, ...], str, str, tuple[str, ...]]] = []
    if excl.maintenance:
        for block in clusters(tuple(excl.maintenance), grid):
            if len(block) >= policy.min_cells:
                tickets = sorted({excl.maintenance[c] for c in block})
                found.append((
                    block, "maintenance",
                    f"{len(block)} contiguous cells silent, but the block matches maintenance ticket {', '.join(tickets)} — expected silence, no alert",
                    tuple(excl.notes),
                ))
    for small in excl.clusters:
        if len(small) == 1:
            found.append((
                small, "single-cell",
                f"single-cell silence at {small[0]}: one sentinel unreachable, neighbours normal — consistent with a cell fault, not an impact",
                (f"Device Reachability: {small[0]} unreachable", f"neighbours of {small[0]}: all reachable"),
            ))
        else:
            found.append((
                small, "below-floor",
                f"{len(small)} silent cells ({', '.join(small)}) — below the {policy.min_cells}-cell floor for a footprint",
                (f"Device Reachability: {len(small)} cells unreachable",),
            ))
    unexplained_dark = {c for cluster in excl.clusters for c in cluster}
    for hot_block in corr.hot_clusters:
        if len(hot_block) < policy.min_cells:
            continue
        touching = any(n in unexplained_dark for c in hot_block for n in grid.neighbours(c))
        if touching:
            continue  # a hot ring around real silence is the disaster signal, not a crowd
        found.append((
            hot_block, "congestion-only",
            f"congestion without silence: {len(hot_block)} contiguous cells at High but every sentinel answers — a crowd, not an impact",
            (f"Congestion Insights: {len(hot_block)} cells High", "Device Reachability: all reachable"),
        ))
    held = None
    for cells, tag, reason, signals in found:
        key = f"{tag}|{','.join(cells)}"
        if key in state.explained:
            held = held or Verdict(Kind.QUIET, t, cells, reason=f"holding: {reason}", key=key)
            continue
        return Verdict(Kind.ABSTAIN, t, cells, reason=reason, signals=signals, key=key)
    return held or Verdict(Kind.QUIET, t)


def apply(verdict: Verdict, corr: Correlation, state: State, policy: Policy, t: float) -> None:
    """Commit the pass. The only place `State` is written."""
    dark = set(corr.dark)
    for cell in dark:
        state.dark_since.setdefault(cell, t)
    for cell in list(state.dark_since):
        if cell not in dark:
            del state.dark_since[cell]

    if verdict.kind in (Kind.CANDIDATE, Kind.DECLARE, Kind.UPDATE) or (
        verdict.kind is Kind.SUSTAIN and verdict.signals
    ):
        state.candidate_passes = _passes(verdict.cells, state)
        state.candidate = verdict.cells
    elif verdict.kind in (Kind.QUIET, Kind.ABSTAIN, Kind.CLEAR):
        state.candidate = ()
        state.candidate_passes = 0

    if verdict.kind is Kind.ABSTAIN:
        state.explained.add(verdict.key)
    elif verdict.kind is Kind.DECLARE:
        state.footprint = verdict.cells
        state.declared_at = t
        state.confidence = verdict.confidence
        state.clear_since = None
    elif verdict.kind is Kind.UPDATE:
        state.footprint = verdict.cells
        state.confidence = verdict.confidence
        state.clear_since = None
    elif verdict.kind is Kind.SUSTAIN:
        if all(c not in dark for c in state.footprint):
            if state.clear_since is None:
                state.clear_since = t
        else:
            state.clear_since = None
    elif verdict.kind is Kind.CLEAR:
        state.footprint = ()
        state.declared_at = None
        state.confidence = None
        state.clear_since = None
        state.explained.clear()


def assess(
    snapshot: Snapshot,
    state: State,
    grid: Grid,
    calendar: tuple[Maintenance, ...],
    policy: Policy,
    t: float,
) -> Verdict:
    """The three stages and the commit, in a row. What the plain runner calls."""
    corr = correlate(snapshot, grid, t)
    excl = exclude(corr, grid, calendar, t)
    verdict = declare(corr, excl, state, grid, policy, t)
    apply(verdict, corr, state, policy, t)
    return verdict


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _signals(
    cluster: tuple[str, ...], corr: Correlation, state: State, grid: Grid, policy: Policy, t: float
) -> tuple[tuple[str, ...], int]:
    n = len(cluster)
    signals = [f"Device Reachability: {n} contiguous cells unreachable (~{grid.area_km2(n)} km²)"]
    unread = [c for c in cluster if c in corr.unread]
    if unread:
        signals.append(f"Congestion Insights: no reading from {len(unread)}/{n} of those cells")
    corroborations = 0

    firsts = [state.dark_since.get(c, t) for c in cluster]
    spread = max(firsts) - min(firsts)
    if spread <= policy.sync_window_s:
        signals.append(f"onset synchronised: all {n} cells went dark within {spread:.0f}s")
        corroborations += 1
    else:
        signals.append(f"onset staggered over {spread:.0f}s")

    ring = grid.ring(cluster)
    ring_live = [c for c in ring if c in corr.monitored and c not in corr.dark]
    ring_hot = [c for c in ring_live if c in corr.hot]
    if ring_live and len(ring_hot) / len(ring_live) >= policy.ring_hot_fraction:
        signals.append(f"hot ring: {len(ring_hot)}/{len(ring_live)} neighbouring cells at High congestion")
        corroborations += 1
    elif ring_live:
        signals.append(f"no hot ring: {len(ring_hot)}/{len(ring_live)} neighbouring cells at High")
    return tuple(signals), corroborations


def _passes(cluster: tuple[str, ...], state: State) -> int:
    if state.candidate and set(cluster) & set(state.candidate):
        return state.candidate_passes + 1
    return 1
