#!/usr/bin/env python3
"""Platform probe — measures the open questions about what the platform actually grants.

Each probe answers one row of that table against the live platform and writes its
raw request/response to nac/evidence/ as committed proof. A 4xx is frequently the
measurement itself (a rejected radius tells us the floor), so probes record errors
as results rather than aborting.

    python nac/probe.py --check          # SDK wiring only, no credentials needed
    python nac/probe.py --all            # every probe
    python nac/probe.py --p02            # one probe
    python nac/probe.py --p00 --profiles # add the destructive QoS profile sweep

Probe map:
    p00  QoD reservation is actually granted, and which QoS profiles exist
    p02  Congestion Insights forecast horizon and bucket width
    p03  Which allocated MSISDNs actually answer
    p04  Location verification radius floor and network location uncertainty
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nac import client as nac  # noqa: E402

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

# Riyadh — a stand-in venue centre, only used when the network cannot tell us where
# the device is. Overridden by location.retrieve whenever that call succeeds.
FALLBACK_CENTRE = {"latitude": 24.7136, "longitude": 46.6753}


def now() -> datetime:
    return datetime.now(timezone.utc)


def record(call: str, fn, **kwargs) -> dict[str, Any]:
    """Invoke an SDK call, capturing either the response or the failure verbatim."""
    started = time.monotonic()
    entry: dict[str, Any] = {
        "call": call,
        "request": nac.to_jsonable(kwargs),
        "at": now().isoformat(),
    }
    try:
        response = fn(**kwargs)
        entry["ok"] = True
        entry["response"] = nac.to_jsonable(response)
    except Exception as exc:  # noqa: BLE001 — a failure is a datapoint here
        entry["ok"] = False
        entry["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "status": getattr(exc, "status_code", None),
            "body": nac.to_jsonable(getattr(exc, "body", None)),
        }
    entry["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return entry


# ----------------------------------------------------------------------------
# p02 — Congestion Insights horizon and step
# ----------------------------------------------------------------------------

HORIZONS_HOURS = [0.25, 1, 6, 24, 72, 168]


def probe_p02(client, devices: list[str]) -> dict[str, Any]:
    """How far ahead does the forecast reach, and at what granularity?

    This is the measurement that fixes the product headline: a minute-scale horizon
    makes in-flight rerouting the story, an hour-scale one makes mission-window
    planning the story. The API accepts an arbitrary start/end, so the real limit is
    found by asking for progressively longer windows and seeing what comes back.
    """
    device = {"phoneNumber": devices[0]}
    calls = [
        record(
            "congestion_insights.query[default]",
            client.congestion_insights.query,
            device=device,
        ),
        record(
            "congestion_insights.query[historical:-24h]",
            client.congestion_insights.query,
            device=device,
            start=now() - timedelta(hours=24),
            end=now(),
        ),
    ]
    for hours in HORIZONS_HOURS:
        calls.append(
            record(
                f"congestion_insights.query[+{hours}h]",
                client.congestion_insights.query,
                device=device,
                start=now(),
                end=now() + timedelta(hours=hours),
            )
        )

    findings = []
    for call in calls:
        summary: dict[str, Any] = {"call": call["call"], "ok": call["ok"]}
        items = call.get("response") if call["ok"] else None
        if isinstance(items, list) and items:
            widths = []
            stops = []
            for item in items:
                start_s, stop_s = item.get("timeIntervalStart"), item.get("timeIntervalStop")
                if start_s and stop_s:
                    a = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
                    b = datetime.fromisoformat(stop_s.replace("Z", "+00:00"))
                    widths.append(int((b - a).total_seconds()))
                    stops.append(b)
            summary.update(
                buckets=len(items),
                bucket_seconds=Counter(widths).most_common(1)[0][0] if widths else None,
                covered_until=max(stops).isoformat() if stops else None,
                levels=sorted({i.get("congestionLevel") for i in items if i.get("congestionLevel")}),
                has_confidence=any(i.get("confidenceLevel") is not None for i in items),
            )
        elif call["ok"]:
            summary["buckets"] = 0
        else:
            summary["error"] = call["error"]["message"][:200]
        findings.append(summary)

    served = [f for f in findings if f.get("buckets")]
    return {
        "probe": "p02",
        "question": "Congestion Insights forecast horizon and step",
        "device": devices[0],
        "verdict": {
            "max_covered_until": max((f["covered_until"] for f in served), default=None),
            "bucket_seconds": Counter(
                f["bucket_seconds"] for f in served if f.get("bucket_seconds")
            ).most_common(1)[0][0]
            if served
            else None,
            "deepest_window_served": served[-1]["call"] if served else None,
            "confidence_returned": any(f.get("has_confidence") for f in served),
        },
        "summary": findings,
        "calls": calls,
    }


# ----------------------------------------------------------------------------
# p00 — QoD reservation
# ----------------------------------------------------------------------------

# The SDK's own example uses DOWNLINK_M_UPLINK_L, so the two directions are separate
# axes. A caller reserving uplink needs to know which uplink tiers exist, so it is a design input, not
# trivia. There is no list-profiles endpoint — the catalogue is found by trying.
CANDIDATE_PROFILES = [
    "QOS_E",
    "QOS_S",
    "QOS_M",
    "QOS_L",
    "DOWNLINK_S_UPLINK_S",
    "DOWNLINK_S_UPLINK_M",
    "DOWNLINK_M_UPLINK_M",
    "DOWNLINK_M_UPLINK_L",
    "DOWNLINK_L_UPLINK_L",
]

# Any routable address works as the flow's far end: QoD reserves a device↔server
# flow, not a blanket device priority, and the reservation is what we are measuring.
APP_SERVER = {"ipv4Address": "8.8.8.8"}


def _create_session(client, device_msisdn: str, profile: str, duration: int = 60):
    create = nac.resolve(client.qod, "create_session_v1", "create_session_v_1")
    return record(
        f"qod.create_session_v1[{profile}]",
        create,
        device={"phoneNumber": device_msisdn},
        application_server=APP_SERVER,
        qos_profile=profile,
        duration=duration,
    )


def probe_p00(client, devices: list[str], sweep_profiles: bool = False) -> dict[str, Any]:
    """Does a reservation actually get granted, and does it produce a session?

    Note the platform's release semantics: after a session ends, its resources are
    held for up to 360 seconds and a new session for the same device and flow is
    refused until the old one is explicitly deleted. That is a demo hazard — an A/B
    run that reserves, releases, then reserves again will collide with it. The probe
    deletes explicitly and reports how long the delete took to take effect.
    """
    airframe = devices[0]
    calls: list[dict[str, Any]] = []
    granted: list[str] = []
    rejected: list[str] = []

    profiles = CANDIDATE_PROFILES if sweep_profiles else ["DOWNLINK_M_UPLINK_L", "QOS_M"]
    delete = nac.resolve(client.qod, "delete_session_v1", "delete_session_v_1")
    get = nac.resolve(client.qod, "get_session_v1", "get_session_v_1")

    for profile in profiles:
        created = _create_session(client, airframe, profile)
        calls.append(created)
        if not created["ok"]:
            rejected.append(profile)
            continue
        granted.append(profile)

        response = created.get("response") or {}
        session_id = response.get("sessionId") or response.get("id")
        if not session_id:
            continue

        # qosStatus is frequently REQUESTED on creation and only settles to
        # AVAILABLE once the network confirms — so read it back before judging.
        time.sleep(2)
        calls.append(record(f"qod.get_session_v1[{profile}]", get, session_id=session_id))
        calls.append(record(f"qod.delete_session_v1[{profile}]", delete, session_id=session_id))
        # Give the platform room before the next create for the same device+flow.
        time.sleep(3)

    statuses = [
        (c["response"] or {}).get("qosStatus")
        for c in calls
        if c["ok"] and c["call"].startswith("qod.get_session")
    ]
    return {
        "probe": "p00",
        "question": "QoD reservation granted, and which QoS profiles exist",
        "device": airframe,
        "verdict": {
            "profiles_accepted": granted,
            "profiles_rejected": rejected,
            "qos_statuses_observed": [s for s in statuses if s],
            "uplink_tier_selectable": any("UPLINK" in p for p in granted),
        },
        "calls": calls,
    }


# ----------------------------------------------------------------------------
# p03 — MSISDN inventory
# ----------------------------------------------------------------------------


def probe_p03(client, devices: list[str]) -> dict[str, Any]:
    """How many allocated numbers actually answer — the ceiling on scout coverage."""
    retrieve = nac.resolve(
        client.device_status, "retrieve_reachability_status", "check_connectivity"
    )
    calls = [
        record(f"device_status.reachability[{m}]", retrieve, device={"phoneNumber": m})
        for m in devices
    ]
    live = [m for m, c in zip(devices, calls) if c["ok"]]
    return {
        "probe": "p03",
        "question": "How many simulator MSISDNs are usable",
        "verdict": {
            "allocated": len(devices),
            "answering": len(live),
            "usable_numbers": live,
            "forward_scouts_available": max(0, len(live) - 1),  # one is the airframe
        },
        "calls": calls,
    }


# ----------------------------------------------------------------------------
# p04 — Location radius floor
# ----------------------------------------------------------------------------

RADII_M = [100, 250, 500, 1000, 2000, 5000, 10000]


def probe_p04(client, devices: list[str]) -> dict[str, Any]:
    """What is the smallest circle the network will verify against?

    Two things come out of this. The first is the hard floor — the radius below
    which the API rejects the request, which is what bounds the zone-level claim.
    The second is subtler and more useful: when the result is PARTIAL the response
    carries matchRate = (requested ∩ network) / network * 100. Sweeping the radius
    and watching matchRate climb toward 100 reveals the network's own location
    uncertainty, which is the honest number to put in front of a jury.
    """
    device = {"phoneNumber": devices[0]}

    # Centre the circles on where the network actually places the device — verifying
    # against an arbitrary point would make TRUE/FALSE meaningless.
    retrieved = record(
        "location.retrieve", client.location.retrieve, device=device, max_age=0
    )
    centre = FALLBACK_CENTRE
    centre_source = "fallback"
    if retrieved["ok"]:
        area = (retrieved.get("response") or {}).get("area") or {}
        found = area.get("center") or area.get("centre")
        if found and found.get("latitude") is not None:
            centre = {"latitude": found["latitude"], "longitude": found["longitude"]}
            centre_source = "location.retrieve"

    verify = nac.resolve(client.location, "verify_v1", "verify_v_1", "verify")
    calls = [retrieved]
    observations = []
    for radius in RADII_M:
        call = record(
            f"location.verify_v1[r={radius}m]",
            verify,
            device=device,
            area={"areaType": "CIRCLE", "center": centre, "radius": radius},
            max_age=0,
        )
        calls.append(call)
        response = call.get("response") or {}
        observations.append(
            {
                "radius_m": radius,
                "accepted": call["ok"],
                "result": response.get("verificationResult"),
                "match_rate": response.get("matchRate"),
                "error": None if call["ok"] else call["error"]["message"][:160],
            }
        )

    accepted = [o for o in observations if o["accepted"]]
    conclusive = [o for o in accepted if o["result"] == "TRUE"]
    return {
        "probe": "p04",
        "question": "Location verification radius floor and network uncertainty",
        "centre": centre,
        "centre_source": centre_source,
        "verdict": {
            "smallest_radius_accepted_m": min((o["radius_m"] for o in accepted), default=None),
            "smallest_radius_verified_true_m": min(
                (o["radius_m"] for o in conclusive), default=None
            ),
            "match_rate_curve": {
                o["radius_m"]: o["match_rate"] for o in accepted if o["match_rate"] is not None
            },
            "corridor_claim_supportable": bool(conclusive)
            and min(o["radius_m"] for o in conclusive) <= 500,
        },
        "observations": observations,
        "calls": calls,
    }


# ----------------------------------------------------------------------------
# Wiring check — runs without credentials
# ----------------------------------------------------------------------------


def check() -> int:
    """Verify the SDK is installed and every method this probe needs resolves."""
    print("SDK wiring check\n" + "-" * 60)
    try:
        import network_as_code
    except ImportError:
        print("  FAIL  network_as_code not installed — pip install -r nac/requirements.txt")
        return 1
    print(f"  ok    network_as_code {getattr(network_as_code, '__version__', 'unknown')}")

    from network_as_code import NetworkAsCodeApi, NetworkAsCodeApiEnvironment

    print(f"  ok    environment {NetworkAsCodeApiEnvironment.DEFAULT.value}")

    # A syntactically valid but fake key: enough to build the object graph and read
    # method names off it without touching the network.
    probe_client = NetworkAsCodeApi(
        api_key="wiring-check", environment=NetworkAsCodeApiEnvironment.DEFAULT
    )
    wanted = [
        ("congestion_insights", ("query",)),
        ("qod", ("create_session_v1", "create_session_v_1")),
        ("qod", ("delete_session_v1", "delete_session_v_1")),
        ("qod", ("get_session_v1", "get_session_v_1")),
        ("location", ("verify_v1", "verify_v_1", "verify")),
        ("location", ("retrieve",)),
        ("device_status", ("retrieve_reachability_status", "check_connectivity")),
        ("geofencing", ("create_subscription",)),
    ]
    failures = 0
    for namespace_name, candidates in wanted:
        namespace = getattr(probe_client, namespace_name, None)
        if namespace is None:
            print(f"  FAIL  client.{namespace_name} missing")
            failures += 1
            continue
        try:
            resolved = nac.resolve(namespace, *candidates)
            print(f"  ok    client.{namespace_name}.{resolved.__name__}")
        except AttributeError as exc:
            print(f"  FAIL  client.{namespace_name}: {exc}")
            failures += 1

    print("-" * 60)
    creds = "set" if _has_key() else "NOT SET — probes will not run"
    print(f"  NAC_API_KEY: {creds}")
    print(f"  NAC_MSISDNS: {len(nac.msisdns())} number(s)")
    print(f"  NAC_WEBHOOK_BASE: {nac.webhook_base() or 'not set'}")
    return 1 if failures else 0


def _has_key() -> bool:
    try:
        nac.api_key()
        return True
    except nac.MissingCredentials:
        return False


# ----------------------------------------------------------------------------


def save(result: dict[str, Any]) -> Path:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    path = EVIDENCE_DIR / f"{result['probe']}-{stamp}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify SDK wiring, no network calls")
    parser.add_argument("--all", action="store_true", help="run every probe")
    parser.add_argument("--p00", action="store_true", help="QoD reservation")
    parser.add_argument("--p02", action="store_true", help="congestion horizon")
    parser.add_argument("--p03", action="store_true", help="MSISDN inventory")
    parser.add_argument("--p04", action="store_true", help="location radius floor")
    parser.add_argument(
        "--profiles",
        action="store_true",
        help="p00: sweep the full QoS profile catalogue (slow, creates real sessions)",
    )
    args = parser.parse_args()

    if args.check or not any([args.all, args.p00, args.p02, args.p03, args.p04]):
        return check()

    try:
        client = nac.build()
    except nac.MissingCredentials as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    devices = nac.msisdns()
    if not devices:
        print("error: NAC_MSISDNS is empty — every probe needs at least one number.", file=sys.stderr)
        return 2

    selected = []
    if args.all or args.p02:
        selected.append(("p02", lambda: probe_p02(client, devices)))
    if args.all or args.p00:
        selected.append(("p00", lambda: probe_p00(client, devices, args.profiles)))
    if args.all or args.p03:
        selected.append(("p03", lambda: probe_p03(client, devices)))
    if args.all or args.p04:
        selected.append(("p04", lambda: probe_p04(client, devices)))

    exit_code = 0
    for name, run in selected:
        print(f"\n=== {name} " + "=" * (56 - len(name)))
        try:
            result = run()
        except Exception:  # noqa: BLE001 — one probe failing must not sink the rest
            traceback.print_exc()
            exit_code = 1
            continue
        path = save(result)
        print(json.dumps(result["verdict"], indent=2, ensure_ascii=False))
        print(f"evidence: {path.relative_to(nac.REPO_ROOT)}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
