#!/usr/bin/env python3
"""Clip a street-level base map for the city-scale scenes.

    python nabd/data/extract_city.py osm-city.json   basemap-city.json    5
    python nabd/data/extract_city.py osm-region.json basemap-region.json 16

The third argument is the thinning step in SCALE units. A 15 km view resolves
about 15 m to the pixel and a 150 km view about 150 m, so the region is thinned
ten times harder than the city for the same apparent detail — and stays small.

Both windows are drawn from the same source, so the scenes look like each other:
the four city scenes watch a 6.7 km square over Kahramanmaraş, and the real-event
scene watches 100 km of the rupture. Natural Earth carries two roads and one dot
across the city square, which is not a map — it is a dark rectangle with squares
on it. OpenStreetMap carries the streets, the water and the place names at both
scales, and that is what makes either of them legible.

Source: OpenStreetMap contributors, via the Overpass API. ODbL; credited in the
extract and in the console's footer.

Kept small enough to inline in a file that must open with no network:
coordinates are stored as integers in ten-thousandths of a degree (about 11 m),
delta-encoded along each way, which is roughly a quarter of the size of the
plain decimals and costs nothing to decode.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "basemap-city.json"  # overridden by argv[2]

SCALE = 10000  # ten-thousandths of a degree, ~11 m
MIN_STEP = 5   # in those units, ~55 m; overridden by argv[3]

MAJOR = {"motorway", "trunk", "primary", "secondary"}
MINOR = {"tertiary", "unclassified"}
LOCAL = {"residential"}


def encode(points: list[tuple[float, float]], step: int = MIN_STEP) -> list[int] | None:
    """Delta-encoded [lon0, lat0, dlon, dlat, ...] in SCALE units."""
    out: list[int] = []
    last: tuple[int, int] | None = None
    for lon, lat in points:
        x, y = round(lon * SCALE), round(lat * SCALE)
        if last is None:
            out += [x, y]
            last = (x, y)
        elif abs(x - last[0]) + abs(y - last[1]) >= step:
            out += [x - last[0], y - last[1]]
            last = (x, y)
    return out if len(out) >= 4 else None


def label(tags: dict) -> str | None:
    """A name the console's monospace font can actually draw.

    Moroccan places carry three scripts in one `name` tag — "Imlil ⵉⵎⵍⵉⵍ إمليل" —
    and Tifinagh comes out of a terminal font as a row of boxes. Where the local
    name is already Latin it is kept exactly as it is, which leaves every Turkish
    label untouched; where it is not, OSM's own `name:en` / `name:fr` is used
    rather than transliterating anything ourselves.
    """
    def latin(text: str) -> bool:
        return bool(text) and all(ord(ch) < 0x250 for ch in text)

    name = tags.get("name") or ""
    if latin(name):
        return name
    for key in ("name:en", "name:fr"):
        if latin(tags.get(key) or ""):
            return tags[key]
    return "".join(ch for ch in name if ord(ch) < 0x250).strip() or None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    out_path = HERE / argv[2] if len(argv) > 2 else OUT
    step = int(argv[3]) if len(argv) > 3 else MIN_STEP
    elements = json.loads(Path(argv[1]).read_text(encoding="utf-8"))["elements"]

    roads: dict[str, list] = {"major": [], "minor": [], "local": []}
    water: list = []
    streams: list = []
    rail: list = []
    places: list = []

    for e in elements:
        tags = e.get("tags", {})
        if e["type"] == "node":
            kind = tags.get("place")
            name = label(tags)
            if not name or kind not in ("city", "town", "village", "suburb", "neighbourhood"):
                continue
            places.append({
                "name": name, "lon": round(e["lon"], 4), "lat": round(e["lat"], 4),
                "rank": {"city": 1, "town": 2, "village": 3, "suburb": 4}.get(kind, 5),
            })
            continue
        geom = [(p["lon"], p["lat"]) for p in e.get("geometry", [])]
        if len(geom) < 2:
            continue
        line = encode(geom, step)
        if line is None:
            continue
        highway = tags.get("highway")
        if highway in MAJOR:
            roads["major"].append(line)
        elif highway in MINOR:
            roads["minor"].append(line)
        elif highway in LOCAL:
            roads["local"].append(line)
        elif tags.get("natural") == "water" or tags.get("landuse") in ("reservoir", "basin"):
            water.append(line)
        elif tags.get("waterway") in ("river", "stream"):
            streams.append(line)
        elif tags.get("railway") == "rail":
            rail.append(line)

    # A 150 km window over the High Atlas comes back with three and a half
    # thousand wadis, most of them two points long. Past a few hundred they stop
    # being terrain and start being noise, and they are what makes the file big,
    # so keep the long ones and drop the trickles.
    def longest(bucket: list, keep: int) -> list:
        return sorted(bucket, key=len, reverse=True)[:keep] if len(bucket) > keep else bucket

    streams = longest(streams, 900)
    water = longest(water, 260)

    # Cities and towns are all kept. Villages are not: there are hundreds, and
    # taking the first twenty-two alphabetically gave a window over the High
    # Atlas whose every label began with A and which named none of the places the
    # event happened in. Spread them instead — each new one as far as possible
    # from the ones already chosen — so the labels cover the window evenly.
    places.sort(key=lambda p: (p["rank"], p["name"]))
    seen: set[str] = set()
    places = [p for p in places if not (p["name"] in seen or seen.add(p["name"]))]
    named = [p for p in places if p["rank"] <= 2]
    rest = [p for p in places if p["rank"] > 2]
    spread: list[dict] = []
    while rest and len(spread) < 22:
        anchors = named + spread
        if not anchors:
            spread.append(rest.pop(0))
            continue
        far = max(rest, key=lambda p: min((p["lon"] - a["lon"]) ** 2 + (p["lat"] - a["lat"]) ** 2 for a in anchors))
        rest.remove(far)
        spread.append(far)
    places = named + spread

    payload = {
        "_": "Street-level base map for the city-scale scenes. Coordinates are delta-encoded "
             "integers in 1e-4 degrees. Generated by nabd/data/extract_city.py.",
        "source": {
            "data": "OpenStreetMap contributors (ODbL), via the Overpass API",
            "retrieved": date.today().isoformat(),
        },
        "scale": SCALE,
        "roads": roads,
        "water": water,
        "streams": streams,
        "rail": rail,
        "places": places,
    }
    out_path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path.name}: {len(roads['major'])} major / {len(roads['minor'])} minor / "
          f"{len(roads['local'])} local roads, {len(water)} water, {len(streams)} stream(s), "
          f"{len(rail)} rail, {len(places)} places, {out_path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
