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
    """Raw request/response lines — the same file `nac/probe.py` writes."""
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
# Live
# ----------------------------------------------------------------------------


class LiveGateway:
    """The same three calls against Nokia Network-as-Code.

    Written to the SDK's shape before an account exists, mirroring the calls in
    `nac/probe.py`, so the swap under time pressure is one flag rather than a
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

    def _call(self, name: str, fn, **kwargs):
        try:
            response = self.nac.to_jsonable(fn(**kwargs))
            self.calls.append(Call(name=name, request=kwargs, response=response, ok=True, t=self.now))
            return response
        except Exception as exc:
            self.calls.append(
                Call(name=name, request=kwargs, response=None, ok=False, error=f"{type(exc).__name__}: {exc}", t=self.now)
            )
            return None

    def congestion(self, device: str) -> tuple[Level, int | None]:
        fn = self.nac.resolve(self.client.congestion_insights, "query_v1", "query_v_1", "query")
        response = self._call("congestion.query", fn, device={"phoneNumber": device})
        if not response:
            return Level.UNKNOWN, None
        first = response[0] if isinstance(response, list) else response
        try:
            return Level((first or {}).get("congestionLevel", "Unknown")), (first or {}).get("confidenceLevel")
        except ValueError:
            return Level.UNKNOWN, None

    def reachability(self, device: str) -> Reach:
        fn = self.nac.resolve(
            self.client.device_status, "get_connectivity_v1", "get_connectivity_v_1", "get_connectivity"
        )
        response = self._call("device_status.connectivity", fn, device={"phoneNumber": device})
        if not response:
            return Reach.UNKNOWN
        status = response.get("connectivityStatus", "")
        return Reach.REACHABLE if "CONNECTED" in status and "NOT" not in status else Reach.UNREACHABLE

    def location(self, device: str, max_age_s: int = 3600) -> Location | None:
        fn = self.nac.resolve(self.client.location_retrieval, "retrieve_v1", "retrieve_v_1", "retrieve")
        response = self._call("location.retrieve", fn, device={"phoneNumber": device}, max_age=max_age_s)
        if not response:
            return None
        area = response.get("area", {})
        centre = area.get("center", {})
        age = 0.0
        stamp = response.get("lastLocationTime")
        if stamp:
            try:
                seen = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                age = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
            except ValueError:
                pass
        try:
            return Location(float(centre["latitude"]), float(centre["longitude"]), int(area.get("radius", 0)), age)
        except (KeyError, TypeError, ValueError):
            return None


def build(backend: str = "offline", world: World | None = None) -> Gateway:
    """Pick a backend. The only line in the package that knows the difference."""
    if backend == "live":
        return LiveGateway()
    if world is None:
        raise ValueError("offline backend needs a world")
    return OfflineGateway(world)
