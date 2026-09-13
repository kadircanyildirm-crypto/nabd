"""One CAMARA surface, two backends: `offline` and `live`.

The agent never imports the SDK and never learns which backend it is talking to.
`OfflineGateway` answers from a `World` in the platform's own vocabulary and
response shapes; `LiveGateway` makes the same three calls against Nokia
Network-as-Code through the SDK. Both record every call in the same `Call`
shape, so an offline run and a live run produce comparable evidence files —
which is the whole basis of the "live proves the contract, the simulator stages
the disaster" split.

The three calls are the entire network surface of the prototype:

    congestion(device)    Congestion Insights   — detection, per sentinel cell
    reachability(device)  Device Status         — detection (sentinels) and triage (registry)
    location(device)      Location Retrieval    — triage only, last-seen position
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from nabd.model import Level, Location, Reach
from nabd.world import World

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "nac" / "evidence"

# Simulated clock origin. Timestamps in offline responses are ISO-8601 like the
# platform's, so a reader cannot tell the two evidence files apart by shape.
EPOCH = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)


def iso(t: float) -> str:
    return (EPOCH + timedelta(seconds=t)).isoformat().replace("+00:00", "Z")


@dataclass
class Call:
    """One API interaction, recorded whether it succeeded or not."""

    name: str
    request: dict[str, Any]
    response: Any = None
    ok: bool = True
    error: str | None = None
    t: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class Gateway(Protocol):
    backend: str
    calls: list[Call]

    def tick(self, t: float) -> None: ...
    def congestion(self, device: str) -> tuple[Level, int | None]: ...
    def reachability(self, device: str) -> Reach: ...
    def location(self, device: str, max_age_s: int = 3600) -> Location | None: ...


def write_calls(calls: list[Call], name: str) -> Path:
    """Raw request/response lines — the same shape the live run writes."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for call in calls:
            fh.write(call.to_json() + "\n")
    return path


# ----------------------------------------------------------------------------
# Offline
# ----------------------------------------------------------------------------


class OfflineGateway:
    """The platform, simulated from a `World`."""

    backend = "offline"

    def __init__(self, world: World) -> None:
        self.world = world
        self.calls: list[Call] = []
        self.now = 0.0
        self._cells = {c.sentinel: c.id for c in world.grid.cells if c.sentinel}
        self._people = {p.msisdn: p for p in world.registry}

    def tick(self, t: float) -> None:
        self.now = t

    def _record(self, name: str, request: dict, response: Any, ok: bool = True, error: str | None = None):
        self.calls.append(Call(name=name, request=request, response=response, ok=ok, error=error, t=self.now))

    def _state(self, device: str) -> tuple[Reach, Level] | None:
        cell = self._cells.get(device)
        if cell is not None:
            return self.world.cell_state(cell, self.now)
        person = self._people.get(device)
        if person is not None:
            reach, _ = self.world.person_state(person, self.now)
            return reach, Level.UNKNOWN
        return None

    def congestion(self, device: str) -> tuple[Level, int | None]:
        request = {"device": {"phoneNumber": device}}
        state = self._state(device)
        if state is None:
            self._record("congestion.query", request, None, ok=False, error="404 DEVICE_NOT_FOUND")
            return Level.UNKNOWN, None
        reach, level = state
        if reach is Reach.UNREACHABLE:
            # A cell that has stopped answering yields no interval at all — the
            # platform returns an empty list, not an error. That absence is data.
            self._record("congestion.query", request, [])
            return Level.UNKNOWN, None
        confidence = {Level.LOW: 85, Level.MEDIUM: 70, Level.HIGH: 80}.get(level, 50)
        self._record(
            "congestion.query",
            request,
            [
                {
                    "timeIntervalStart": iso(self.now),
                    "timeIntervalStop": iso(self.now + 900),
                    "congestionLevel": level.value,
                    "confidenceLevel": confidence,
                }
            ],
        )
        return level, confidence

    def reachability(self, device: str) -> Reach:
        request = {"device": {"phoneNumber": device}}
        state = self._state(device)
        if state is None:
            self._record("device_status.connectivity", request, None, ok=False, error="404 DEVICE_NOT_FOUND")
            return Reach.UNKNOWN
        reach, _ = state
        status = "CONNECTED_DATA" if reach is Reach.REACHABLE else "NOT_CONNECTED"
        self._record("device_status.connectivity", request, {"connectivityStatus": status})
        return reach

    def location(self, device: str, max_age_s: int = 3600) -> Location | None:
        request = {"device": {"phoneNumber": device}, "maxAge": max_age_s}
        person = self._people.get(device)
        if person is not None:
            _, loc = self.world.person_state(person, self.now)
        elif device in self._cells:
            cell = self.world.grid.by_id(self._cells[device])
            loc = Location(cell.lat, cell.lon, 300, 0.0)
        else:
            self._record("location.retrieve", request, None, ok=False, error="404 DEVICE_NOT_FOUND")
            return None
        if loc.age_s > max_age_s:
            self._record("location.retrieve", request, None, ok=False, error="404 LOCATION_RETRIEVAL.UNABLE_TO_LOCATE")
            return None
        self._record(
            "location.retrieve",
            request,
            {
                "lastLocationTime": iso(self.now - loc.age_s),
                "area": {
                    "areaType": "CIRCLE",
                    "center": {"latitude": loc.lat, "longitude": loc.lon},
                    "radius": loc.radius_m,
                },
            },
        )
        return loc


# ----------------------------------------------------------------------------
# Reading a CAMARA response
# ----------------------------------------------------------------------------
#
# These three functions are the only place a platform response becomes a
# reading, and every backend goes through them — live, offline replay, and the
# parity harness alike. That is what makes "the same logic runs on both" a
# property of the code rather than a claim on a slide: if the simulator's
# responses were the wrong shape, the live parser would not read them, and
# `nabd/parity.py` runs exactly that check.


def parse_congestion(response: Any) -> tuple[Level, int | None]:
    """Congestion Insights. An empty list is not an error — it is a silent cell."""
    if not response:
        return Level.UNKNOWN, None
    first = response[0] if isinstance(response, list) else response
    try:
        return Level((first or {}).get("congestionLevel", "Unknown")), (first or {}).get("confidenceLevel")
    except ValueError:
        return Level.UNKNOWN, None


def parse_reachability(response: Any) -> Reach:
    """Device Status. Anything that is not a positive answer is unreachable.

    The platform exposes two vocabularies for the same question — connectivity
    (`CONNECTED_DATA` / `NOT_CONNECTED`) and reachability (`REACHABLE_DATA` /
    `NOT_REACHABLE`) — and which one an account gets depends on the SDK release.
    Both are read here, because for Nabd they answer the same question: did this
    sentinel answer.
    """
    if not response:
        return Reach.UNKNOWN
    status = response.get("connectivityStatus") or response.get("reachabilityStatus") or ""
    positive = "CONNECTED" in status or "REACHABLE" in status
    return Reach.REACHABLE if positive and "NOT" not in status else Reach.UNREACHABLE


def parse_location(response: Any, now: datetime) -> Location | None:
    """Location Retrieval. `now` is passed in so a replay ages the fix the same
    way the live call did, instead of against the wall clock of the replay."""
    if not response:
        return None
    area = response.get("area", {})
    centre = area.get("center", {})
    age = 0.0
    stamp = response.get("lastLocationTime")
    if stamp:
        try:
            seen = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            age = max(0.0, (now - seen).total_seconds())
        except ValueError:
            pass
    try:
        return Location(float(centre["latitude"]), float(centre["longitude"]), int(area.get("radius", 0)), age)
    except (KeyError, TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# Live
# ----------------------------------------------------------------------------


class LiveGateway:
    """The same three calls against Nokia Network-as-Code.

    Written to the SDK's shape before an account exists, mirroring the calls the
    live client makes, so the swap under time pressure is one flag rather than a
    new file. A platform 'no' is recorded as a result, never raised.
    """

    backend = "live"

    def __init__(self, client=None) -> None:
        from nac import client as nac_client

        self.client = client or nac_client.build()
        self.nac = nac_client
        self.calls: list[Call] = []
        self.now = 0.0

    def tick(self, t: float) -> None:
        self.now = t

    # Where each of the three calls lives on the SDK. Both the namespace and the
    # method have moved between generated releases, so every hop is a list of
    # candidates rather than a name — see `nac.client.namespace` / `.resolve`.
    # `tests/test_nabd_live_wiring.py` checks these against the installed SDK, so
    # a rename upstream fails the build instead of the demonstration.
    ENDPOINTS = {
        "congestion.query": (
            ("congestion_insights",),
            ("query_v1", "query_v_1", "query"),
        ),
        "device_status.connectivity": (
            ("device_status",),
            ("check_connectivity", "get_connectivity_v1", "get_connectivity_v_1",
             "get_connectivity", "retrieve_reachability_status"),
        ),
        "location.retrieve": (
            ("location", "location_retrieval"),
            ("retrieve_v1", "retrieve_v_1", "retrieve"),
        ),
    }

    def _resolve(self, call: str):
        spaces, methods = self.ENDPOINTS[call]
        return self.nac.resolve(self.nac.namespace(self.client, *spaces), *methods)

    def _call(self, name: str, **kwargs):
        """Invoke one endpoint. A platform 'no' — including a name that has moved
        out from under us — is recorded as a result, never raised."""
        try:
            response = self.nac.to_jsonable(self._resolve(name)(**kwargs))
            self.calls.append(Call(name=name, request=kwargs, response=response, ok=True, t=self.now))
            return response
        except Exception as exc:
            self.calls.append(
                Call(name=name, request=kwargs, response=None, ok=False, error=f"{type(exc).__name__}: {exc}", t=self.now)
            )
            return None

    def congestion(self, device: str) -> tuple[Level, int | None]:
        return parse_congestion(self._call("congestion.query", device={"phoneNumber": device}))

    def reachability(self, device: str) -> Reach:
        return parse_reachability(self._call("device_status.connectivity", device={"phoneNumber": device}))

    def location(self, device: str, max_age_s: int = 3600) -> Location | None:
        response = self._call("location.retrieve", device={"phoneNumber": device}, max_age=max_age_s)
        return parse_location(response, datetime.now(timezone.utc))


# ----------------------------------------------------------------------------
# Replay
# ----------------------------------------------------------------------------


class ReplayGateway:
    """A recorded transcript, answered back through the live parsers.

    This is the backend that makes the parity claim checkable by someone who has
    no account. It takes a `.jsonl` of `Call` records — written either by a live
    run or by an offline one, they are the same shape — and serves the recorded
    responses in the order they were recorded, reading each one with
    `parse_congestion` / `parse_reachability` / `parse_location`, the same three
    functions `LiveGateway` uses.

    Two things follow. Replaying an *offline* transcript proves the simulator's
    responses are the shape the live code reads, and that the agent's decisions
    depend on the responses rather than on the object that returned them.
    Replaying a *live* transcript re-runs the agent on real platform bytes,
    with no credentials and no network, which is what a judge can do.
    """

    backend = "replay"

    def __init__(self, calls: list[Call], source: str = "") -> None:
        self.source = source
        self.calls: list[Call] = []
        self.now = 0.0
        self.missing = 0
        self._queues: dict[tuple[str, str], deque[Call]] = {}
        for call in calls:
            self._queues.setdefault((call.name, _device_of(call.request)), deque()).append(call)

    @classmethod
    def from_file(cls, path: Path) -> "ReplayGateway":
        calls = [
            Call(**json.loads(line))
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(calls, source=Path(path).name)

    def devices(self) -> tuple[str, ...]:
        """Every device the transcript carries, in a stable order."""
        return tuple(sorted({device for (_, device) in self._queues}))

    def tick(self, t: float) -> None:
        self.now = t

    def _next(self, name: str, device: str) -> Call | None:
        queue = self._queues.get((name, device))
        if not queue:
            self.missing += 1
            return None
        call = queue.popleft() if len(queue) > 1 else queue[0]
        self.calls.append(Call(name=call.name, request=call.request, response=call.response, ok=call.ok, error=call.error, t=self.now))
        return call

    def congestion(self, device: str) -> tuple[Level, int | None]:
        call = self._next("congestion.query", device)
        return parse_congestion(None if call is None else call.response)

    def reachability(self, device: str) -> Reach:
        call = self._next("device_status.connectivity", device)
        return parse_reachability(None if call is None else call.response)

    def location(self, device: str, max_age_s: int = 3600) -> Location | None:
        call = self._next("location.retrieve", device)
        if call is None:
            return None
        return parse_location(call.response, EPOCH + timedelta(seconds=self.now))


def _device_of(request: dict) -> str:
    device = request.get("device") or {}
    if isinstance(device, dict):
        return str(device.get("phoneNumber", ""))
    return str(device)


def build(
    backend: str = "offline",
    world: World | None = None,
    transcript: Path | None = None,
    calls: list[Call] | None = None,
) -> Gateway:
    """Pick a backend. The only function in the package that knows the difference.

    Everything else — every runner, every scene, the parity harness itself —
    reaches the network through here, which is what `nabd.parity` check 2
    enforces by refusing to pass if any other module names a backend class.
    """
    if backend == "live":
        return LiveGateway()
    if backend == "replay":
        if calls is not None:
            return ReplayGateway(calls, source="memory")
        if transcript is None:
            raise ValueError("replay backend needs a transcript or a list of calls")
        return ReplayGateway.from_file(transcript)
    if world is None:
        raise ValueError("offline backend needs a world")
    return OfflineGateway(world)
