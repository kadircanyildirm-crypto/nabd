"""The agent layer: LangGraph orchestration wrapped around the deterministic core.

The Resource & Tooling Guide makes an approved agent framework a mandatory
component, and LangGraph is on the list. This module is that binding, and it is
deliberately thin: the graph owns order, branching and the record; the verdict
belongs to `nabd/detector.py`, which has no framework import.

The chain is sense → correlate → exclude → declare, then one conditional edge
that is the privacy claim made literal: the `triage` node — the only node that
ever queries a personal device — is reachable only from a verdict with an
active footprint. Every other pass routes through `hold`, which touches nothing.
Delete the conditional and the registry is polled every pass; keep it and the
claim "no personal device is queried outside a declared footprint" is a
property of the topology, which `render_mermaid` prints from the code that runs.

Where an LLM belongs: the `brief` node, and nowhere else. It phrases a record
for the duty officer; it never decides.
"""

from __future__ import annotations

from typing import Any, TypedDict

from nabd.brief import Composer, compose
from nabd.detector import DEFAULT_POLICY, Policy, State, apply, correlate, declare, exclude
from nabd.log import EvidenceLog, Record, grid_string, record_from
from nabd.loop import sense
from nabd.model import Grid, Maintenance, Person
from nabd.triage import TriageState, run as run_triage

try:  # pragma: no cover - exercised by whether the import lands
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False
    START = "__start__"
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]


class PassState(TypedDict, total=False):
    """One pass through the graph; each key is its own channel."""

    t: float
    calls_before: int
    snapshot: Any
    correlation: Any
    exclusion: Any
    verdict: Any
    triage: Any
    brief: str


class NabdGraph:
    """The agent, as a compiled LangGraph, with the same `step(t)` as `NabdLoop`."""

    def __init__(
        self,
        gateway,
        grid: Grid,
        registry: tuple[Person, ...] = (),
        calendar: tuple[Maintenance, ...] = (),
        policy: Policy = DEFAULT_POLICY,
        name: str = "nabd",
        composer: Composer | None = None,
    ) -> None:
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "langgraph is not installed. `pip install langgraph`, or run the same "
                "scene through nabd.loop.NabdLoop, which needs nothing."
            )
        self.gw = gateway
        self.grid = grid
        self.registry = registry
        self.calendar = calendar
        self.policy = policy
        self.composer = composer
        self.state = State()
        self.triage = TriageState()
        self.log = EvidenceLog(name)
        self.graph = self._build()

    # -- nodes ----------------------------------------------------------------

    def _sense(self, s: PassState) -> PassState:
        return {"snapshot": sense(self.gw, self.grid, s["t"])}

    def _correlate(self, s: PassState) -> PassState:
        return {"correlation": correlate(s["snapshot"], self.grid, s["t"])}

    def _exclude(self, s: PassState) -> PassState:
        return {"exclusion": exclude(s["correlation"], self.grid, self.calendar, s["t"])}

    def _declare(self, s: PassState) -> PassState:
        verdict = declare(s["correlation"], s["exclusion"], self.state, self.grid, self.policy, s["t"])
        apply(verdict, s["correlation"], self.state, self.policy, s["t"])
        return {"verdict": verdict}

    def _triage(self, s: PassState) -> PassState:
        verdict = s["verdict"]
        return {"triage": run_triage(self.gw, self.registry, verdict.cells, self.triage, s["t"])}

    def _hold(self, s: PassState) -> PassState:
        """No footprint: nothing personal is queried. This node exists to be routed to."""
        return {"triage": None}

    def _brief(self, s: PassState) -> PassState:
        return {"brief": compose(s["verdict"], s.get("triage"), self.grid, self.composer)}

    def _log(self, s: PassState) -> PassState:
        api_calls = [c.name for c in self.gw.calls[s["calls_before"] :]]
        self.log.add(
            record_from(s["verdict"], s.get("triage"), api_calls, s.get("brief", ""), grid_string(s["snapshot"], self.grid))
        )
        return {}

    # -- the edge -------------------------------------------------------------

    def _route(self, s: PassState) -> str:
        return "triage" if s["verdict"].footprint_active else "hold"

    def _build(self):
        graph = StateGraph(PassState)
        graph.add_node("sense", self._sense)
        graph.add_node("correlate", self._correlate)
        graph.add_node("exclude", self._exclude)
        graph.add_node("declare", self._declare)
        graph.add_node("triage", self._triage)
        graph.add_node("hold", self._hold)
        graph.add_node("brief", self._brief)
        graph.add_node("log", self._log)

        graph.add_edge(START, "sense")
        graph.add_edge("sense", "correlate")
        graph.add_edge("correlate", "exclude")
        graph.add_edge("exclude", "declare")
        graph.add_conditional_edges("declare", self._route, {"triage": "triage", "hold": "hold"})
        graph.add_edge("triage", "brief")
        graph.add_edge("hold", "brief")
        graph.add_edge("brief", "log")
        graph.add_edge("log", END)
        return graph.compile()

    # -- the same surface as NabdLoop -----------------------------------------

    def step(self, t: float) -> Record:
        self.gw.tick(t)
        self.graph.invoke({"t": t, "calls_before": len(self.gw.calls)})
        return self.log.records[-1]


def render_mermaid() -> str:
    """The topology, generated from the graph that actually runs."""
    if not LANGGRAPH_AVAILABLE:
        return "langgraph not installed"
    stub = NabdGraph.__new__(NabdGraph)
    return NabdGraph._build(stub).get_graph().draw_mermaid()


if __name__ == "__main__":
    print(render_mermaid())
