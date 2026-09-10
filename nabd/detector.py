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

from nabd.model import Confidence, Evidence, Grid, Kind, Level, Maintenance, Reach, Snapshot, Verdict


@dataclass(frozen=True)
class Policy:
    min_cells: int = 3
    confirm_passes: int = 2
    sync_window_s: float = 120.0
    ring_hot_fraction: float = 0.4
    clear_after_s: float = 600.0
    pass_interval_s: float = 30.0
    # The local-baseline gate. A block is suppressed only on positive evidence
    # that silence is normal there: at least `baseline_min_passes` observations
    # of those cells, of which at least `baseline_dark_rate` were already dark.
    # Below that many observations the gate cannot fire, so a system that has
    # just started never suppresses a real impact for lack of history.
    baseline_min_passes: int = 10
    baseline_dark_rate: float = 0.20
    # A pass is blind when this share of the monitored sentinels returned no
    # reading at all — the platform, not the network, is silent. A blind pass
    # declares nothing, clears nothing and teaches the baseline nothing.
    blind_share: float = 0.5


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
    # Rolling local baseline: how many passes have been observed at all, and how
    # many of them each cell spent unreachable. Only accumulated while no
    # footprint is active, so a long disaster never teaches the detector that
    # its own footprint is normal.
    passes_observed: int = 0
    dark_passes: dict[str, int] = field(default_factory=dict)
    # ...and how many of those the cell has been dark for *without interruption*,
    # up to now. An outage that is still running is the thing being judged, not
    # evidence about what is normal, so it is taken back out below.
    dark_run: dict[str, int] = field(default_factory=dict)

    def baseline(self, cell: str) -> tuple[int, int]:
        """(ordinary passes, of which dark) — discounting the silence running now."""
        run = self.dark_run.get(cell, 0)
        return (max(0, self.passes_observed - run),
                max(0, self.dark_passes.get(cell, 0) - run))

    def dark_rate(self, cell: str) -> float:
        observed, dark = self.baseline(cell)
        return dark / observed if observed else 0.0


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
    unknown: tuple[str, ...] = ()  # Device Status returned nothing: no reading, not silence


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
    unknown = tuple(c for c in monitored if snapshot[c].reach is Reach.UNKNOWN)
    return Correlation(
        t=t,
        monitored=monitored,
        dark=dark,
        hot=hot,
        unread=unread,
        unknown=unknown,
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


def blind(corr: Correlation, policy: Policy) -> bool:
    """Too few sentinels answered for the pass to say anything about the network."""
    return bool(corr.monitored) and len(corr.unknown) > policy.blind_share * len(corr.monitored)


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

    # -- a blind pass: the platform is silent, which says nothing about the network
    if blind(corr, policy):
        n, m = len(corr.unknown), len(corr.monitored)
        signal = (f"Device Status: no reading from {n}/{m} sentinels",)
        if state.footprint:
            return Verdict(
                Kind.SUSTAIN, t, state.footprint, state.confidence,
                reason=f"footprint held: no reading from {n}/{m} sentinels this pass — the platform is not answering; nothing confirmed, nothing cleared",
                signals=signal,
            )
        return Verdict(
            Kind.ABSTAIN, t, (),
            reason=f"blind: no reading from {n} of {m} sentinels — the platform is not answering, and that is not the network going silent; nothing declared",
            signals=signal,
        )

    # -- an active footprint: sustain, update or clear -------------------------
    if state.footprint and len(lead) < policy.min_cells:
        # Unknown is not back. Only a cell that answered counts towards clearing.
        back = [c for c in state.footprint if c not in corr.dark and c not in corr.unknown]
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
        ctx = SignalContext(lead, corr, state, grid, policy, t)
        evidence, corroborations, veto = weigh(ctx)
        signals = rendered(evidence)

        # An established footprint is maintained on geometry alone. The gates and
        # corroborations are the evidence for *declaring* an impact, and they are
        # not re-litigated every pass afterwards: a real event that spreads over
        # an hour has a staggered onset and a ring that cools as it is
        # overtaken, and neither of those makes the disaster less real. A
        # published footprint ends when its cells answer again, not when the
        # evidence that opened it fades.
        if state.footprint:
            confidence = state.confidence
            if set(lead) != set(state.footprint):
                grown = len(set(lead) - set(state.footprint))
                shrunk = len(set(state.footprint) - set(lead))
                return Verdict(
                    Kind.UPDATE, t, lead, confidence,
                    reason=f"footprint updated: +{grown} / -{shrunk} cells, now {len(lead)}",
                    signals=signals, evidence=evidence,
                )
            return Verdict(Kind.SUSTAIN, t, lead, confidence, reason="footprint held", signals=signals, evidence=evidence)

        # A gate said no. The block is real; the claim that it means an impact
        # is not, and the measurement that refuses it is written down.
        if veto is not None:
            key = f"{veto.name}|{','.join(lead)}"
            reason = f"{len(lead)} contiguous cells silent, but {veto.detail} — no alert"
            if key in state.explained:
                return Verdict(Kind.QUIET, t, lead, reason=f"holding: {reason}", key=key)
            return Verdict(Kind.ABSTAIN, t, lead, reason=reason, signals=signals, evidence=evidence, key=key)

        if corroborations == 0:
            absent = ", ".join(e.detail for e in evidence if e.role == "corroboration" and not e.present)
            key = f"uncorroborated|{','.join(lead)}"
            reason = (
                f"{len(lead)} contiguous cells silent but nothing corroborates an impact: "
                f"{absent} — held, not declared"
            )
            if key in state.explained:
                return Verdict(Kind.QUIET, t, lead, reason=f"holding: {reason}", key=key)
            return Verdict(Kind.ABSTAIN, t, lead, reason=reason, signals=signals, evidence=evidence, key=key)
        confidence = Confidence.HIGH if corroborations >= 2 else Confidence.MEDIUM
        passes = _passes(lead, state)
        if passes < policy.confirm_passes:
            return Verdict(
                Kind.CANDIDATE, t, lead, confidence,
                reason=f"candidate footprint, {len(lead)} cells — holding {policy.confirm_passes - passes} more pass for confirmation",
                signals=signals, evidence=evidence,
            )
        return Verdict(
            Kind.DECLARE, t, lead, confidence,
            reason=f"impact footprint declared: {len(lead)} contiguous cells, ~{grid.area_km2(len(lead))} km²",
            signals=signals, evidence=evidence,
        )

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

    # The local baseline learns only from ordinary time. While a footprint is
    # published the grid is not ordinary, so the history pauses rather than
    # teaching the detector that the disaster it is watching is normal. A blind
    # pass saw nothing, so it teaches nothing either.
    if not state.footprint and not blind(corr, policy):
        state.passes_observed += 1
        for cell in list(state.dark_run):
            if cell not in dark:
                del state.dark_run[cell]
        for cell in dark:
            state.dark_passes[cell] = state.dark_passes.get(cell, 0) + 1
            state.dark_run[cell] = state.dark_run.get(cell, 0) + 1

    if verdict.kind in (Kind.CANDIDATE, Kind.DECLARE, Kind.UPDATE) or (
        verdict.kind is Kind.SUSTAIN and verdict.signals
    ):
        state.candidate_passes = _passes(verdict.cells, state)
        state.candidate = verdict.cells
    elif verdict.kind in (Kind.QUIET, Kind.ABSTAIN, Kind.CLEAR):
        state.candidate = ()
        state.candidate_passes = 0

    if verdict.kind is Kind.ABSTAIN:
        if verdict.key:
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
        unknown = set(corr.unknown)
        if all(c not in dark and c not in unknown for c in state.footprint):
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


# ----------------------------------------------------------------------------
# Evidence: the extensible part
# ----------------------------------------------------------------------------
#
# The detector does not depend on any one disaster signature being right. What
# it depends on is the *minimum observable pattern*: a block of adjacent cells
# that stops answering together, in a place where that is not normal. Everything
# beyond that — the hot ring, the synchronised onset — is corroboration that
# raises confidence, and each one is a small named function below.
#
# Adding a network surface is therefore an append to `CORROBORATIONS`, not a
# redesign: a future aggregate-traffic or cell-outage API becomes one more
# `Evidence` in the same list, weighed the same way, and the verdict arithmetic
# never changes.


@dataclass(frozen=True)
class SignalContext:
    """Everything a signal function is allowed to look at."""

    cluster: tuple[str, ...]
    corr: Correlation
    state: State
    grid: Grid
    policy: Policy
    t: float


def sig_synchronised_onset(ctx: SignalContext) -> Evidence:
    """Did the block go dark together? Corroborates: impact is instantaneous."""
    firsts = [ctx.state.dark_since.get(c, ctx.t) for c in ctx.cluster]
    spread = max(firsts) - min(firsts)
    if spread <= ctx.policy.sync_window_s:
        return Evidence(
            "synchronised-onset", "corroboration", True,
            f"onset synchronised: all {len(ctx.cluster)} cells went dark within {spread:.0f}s",
            "Device Reachability Status",
        )
    return Evidence(
        "synchronised-onset", "corroboration", False,
        f"onset staggered over {spread:.0f}s",
        "Device Reachability Status",
    )


def sig_hot_ring(ctx: SignalContext) -> Evidence:
    """Is the surviving ring saturated? Corroborates: everyone calls at once."""
    ring = ctx.grid.ring(ctx.cluster)
    live = [c for c in ring if c in ctx.corr.monitored and c not in ctx.corr.dark]
    hot = [c for c in live if c in ctx.corr.hot]
    if live and len(hot) / len(live) >= ctx.policy.ring_hot_fraction:
        return Evidence(
            "hot-ring", "corroboration", True,
            f"hot ring: {len(hot)}/{len(live)} neighbouring cells at High congestion",
            "Congestion Insights",
        )
    return Evidence(
        "hot-ring", "corroboration", False,
        f"no hot ring: {len(hot)}/{len(live)} neighbouring cells at High" if live else "no live neighbouring cells to read",
        "Congestion Insights",
    )


def gate_local_baseline(ctx: SignalContext) -> Evidence:
    """Is this silence abnormal *here*? A gate: it can veto, never declare.

    A block of cells that is unreachable a fifth of the time anyway is chronic
    degradation — a bad backhaul, a rural edge, a site on generator power. It
    reproduces every other signal of an impact, including a synchronised onset,
    and it is the look-alike no calendar explains. The measurement is the
    defence: silence is only news where silence is not the local normal.
    """
    state, policy = ctx.state, ctx.policy
    # Every count here sets aside the unbroken silence running now, so the gate
    # is asked about the cells' ordinary life rather than about the outage it is
    # being shown. Judged on the cluster's median, so one odd cell cannot carry
    # or sink the block.
    stats = [state.baseline(c) for c in ctx.cluster]
    ordinary = sorted(o for o, _ in stats)[len(stats) // 2]
    if ordinary < policy.baseline_min_passes:
        return Evidence(
            "local-baseline", "gate", True,
            f"no local baseline yet ({ordinary} ordinary passes observed) — not enough history to call this normal",
            "Device Reachability Status",
        )
    typical = sorted(state.dark_rate(c) for c in ctx.cluster)[len(ctx.cluster) // 2]
    dark_counts = sum(d for _, d in stats) / len(stats)
    if typical >= policy.baseline_dark_rate:
        return Evidence(
            "local-baseline", "gate", False,
            f"silence is the local baseline: these {len(ctx.cluster)} cells were already unreachable in "
            f"{dark_counts:.0f} of the last {ordinary} ordinary passes ({typical:.0%} of the time)",
            "Device Reachability Status",
        )
    return Evidence(
        "local-baseline", "gate", True,
        f"against local baseline: these cells were unreachable in {dark_counts:.1f} of the last "
        f"{ordinary} ordinary passes ({typical:.0%}) — this silence is abnormal here",
        "Device Reachability Status",
    )


#: Necessary conditions. Any one of them absent vetoes the declaration.
GATES: tuple = (gate_local_baseline,)

#: Supporting evidence. One makes MEDIUM, two or more make HIGH, none abstains.
#: A new network surface is appended here and nothing else changes.
CORROBORATIONS: tuple = (sig_synchronised_onset, sig_hot_ring)


def weigh(ctx: SignalContext) -> tuple[tuple[Evidence, ...], int, Evidence | None]:
    """Run every signal over the pass. Returns (evidence, corroborations, veto)."""
    n = len(ctx.cluster)
    base = [
        Evidence(
            "contiguous-silence", "gate", True,
            f"Device Reachability: {n} contiguous cells unreachable (~{ctx.grid.area_km2(n)} km²)",
            "Device Reachability Status",
        )
    ]
    unread = [c for c in ctx.cluster if c in ctx.corr.unread]
    if unread:
        base.append(
            Evidence(
                "no-congestion-reading", "gate", True,
                f"Congestion Insights: no reading from {len(unread)}/{n} of those cells",
                "Congestion Insights",
            )
        )
    gates = [gate(ctx) for gate in GATES]
    corroborations = [signal(ctx) for signal in CORROBORATIONS]
    evidence = tuple(base + gates + corroborations)
    veto = next((e for e in gates if not e.present), None)
    return evidence, sum(1 for e in corroborations if e.present), veto


def rendered(evidence: tuple[Evidence, ...]) -> tuple[str, ...]:
    """The evidence as the lines a duty officer reads. Order is the weighing order."""
    return tuple(e.detail for e in evidence)


def _passes(cluster: tuple[str, ...], state: State) -> int:
    if state.candidate and set(cluster) & set(state.candidate):
        return state.candidate_passes + 1
    return 1
