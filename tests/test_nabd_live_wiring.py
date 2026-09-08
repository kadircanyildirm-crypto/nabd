"""The live path, checked against the installed SDK without spending a call.

    python -m tests.test_nabd_live_wiring

The Nokia SDK is generated from the CAMARA specs, and both the namespace and the
method name have moved between releases: Location Retrieval has been `location`
and `location_retrieval`; Device Status has offered `get_connectivity`,
`check_connectivity` and `retrieve_reachability_status`. A rename upstream is
invisible until the one moment it matters — the live run, under time pressure,
with an audience.

So the resolution is checked here instead. No credentials are needed and no
request is made: the client is constructed with a dummy key and only the method
lookup is exercised. If the SDK is not installed the suite says so and passes,
because the offline demonstration must never depend on it.
"""

from __future__ import annotations

from nabd.gateway import LiveGateway, parse_congestion, parse_location, parse_reachability
from nabd.model import Level, Reach

try:
    from network_as_code import NetworkAsCodeApi, NetworkAsCodeApiEnvironment

    SDK = True
except ImportError:  # pragma: no cover - exercised by whether the import lands
    SDK = False


def _stub() -> LiveGateway:
    """A LiveGateway wired to a real client object, with a key that is never used."""
    from nac import client as nac

    gateway = LiveGateway.__new__(LiveGateway)
    gateway.client = NetworkAsCodeApi(api_key="not-a-real-key", environment=NetworkAsCodeApiEnvironment.DEFAULT)
    gateway.nac = nac
    gateway.calls = []
    gateway.now = 0.0
    return gateway


def test_every_live_endpoint_resolves_on_the_installed_sdk():
    if not SDK:
        print("        network_as_code is not installed — offline path unaffected")
        return
    gateway = _stub()
    resolved = {}
    for call in LiveGateway.ENDPOINTS:
        fn = gateway._resolve(call)
        assert callable(fn), (call, fn)
        resolved[call] = fn.__qualname__
    assert set(resolved) == {"congestion.query", "device_status.connectivity", "location.retrieve"}
    for call, qualname in resolved.items():
        print(f"        {call:<28} -> {qualname}")


def test_the_request_shape_matches_the_sdk_signature():
    """Every endpoint must accept the keywords the gateway actually passes."""
    if not SDK:
        print("        network_as_code is not installed — nothing to check")
        return
    import inspect

    gateway = _stub()
    expected = {
        "congestion.query": {"device"},
        "device_status.connectivity": {"device"},
        "location.retrieve": {"device", "max_age"},
    }
    for call, keywords in expected.items():
        params = set(inspect.signature(gateway._resolve(call)).parameters)
        missing = keywords - params
        assert not missing, f"{call} does not accept {sorted(missing)}; it takes {sorted(params)}"


def test_a_moved_endpoint_is_recorded_rather_than_raised():
    """A rename upstream must degrade into a logged failure, not abort a live run."""
    if not SDK:
        print("        network_as_code is not installed — nothing to check")
        return
    gateway = _stub()
    original = dict(LiveGateway.ENDPOINTS)
    try:
        LiveGateway.ENDPOINTS = {**original, "congestion.query": (("no_such_namespace",), ("nope",))}
        assert gateway.congestion("+900000000") == (Level.UNKNOWN, None)
    finally:
        LiveGateway.ENDPOINTS = original
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert not call.ok and "AttributeError" in (call.error or ""), call
    print("        a moved endpoint is recorded as a failed call, and the pass continues")


def test_both_device_status_vocabularies_are_read():
    """The platform answers connectivity or reachability depending on the release."""
    assert parse_reachability({"connectivityStatus": "CONNECTED_DATA"}) is Reach.REACHABLE
    assert parse_reachability({"connectivityStatus": "NOT_CONNECTED"}) is Reach.UNREACHABLE
    assert parse_reachability({"reachabilityStatus": "REACHABLE_DATA"}) is Reach.REACHABLE
    assert parse_reachability({"reachabilityStatus": "REACHABLE_SMS"}) is Reach.REACHABLE
    assert parse_reachability({"reachabilityStatus": "NOT_REACHABLE"}) is Reach.UNREACHABLE
    assert parse_reachability(None) is Reach.UNKNOWN
    assert parse_reachability({}) is Reach.UNKNOWN


def test_the_parsers_survive_a_platform_saying_nothing():
    """An empty or malformed answer is data, not a crash."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    assert parse_congestion([]) == (Level.UNKNOWN, None)
    assert parse_congestion(None) == (Level.UNKNOWN, None)
    assert parse_congestion([{"congestionLevel": "nonsense"}]) == (Level.UNKNOWN, None)
    assert parse_congestion([{"congestionLevel": "High", "confidenceLevel": 80}]) == (Level.HIGH, 80)
    assert parse_location(None, now) is None
    assert parse_location({"area": {}}, now) is None
    assert parse_location({"area": {"center": {"latitude": 1.0, "longitude": 2.0}, "radius": 300}}, now) is not None


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_live_wiring"]))
