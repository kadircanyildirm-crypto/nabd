#!/usr/bin/env python3
"""Extract the map furniture for the real-event scene: contours and the rupture.

    python nabd/data/extract_geometry.py cont_mi.json rupture.json

`extract_shakemap.py` takes the numbers the agent reasons over. This takes the
two things the *map* needs, so a viewer can see the declared footprint sitting on
the measured event rather than on an empty grid:

* **MMI contours** — the published isoseismals, at their official USGS colours.
  The footprint Nabd declares should hug the VIII line; that is the whole claim,
  and drawing both lets someone check it by eye in a second.
* **The rupture** — the finite-fault surface projection from the same ShakeMap
  product. The reason the footprint is a diagonal band and not a circle.

Both are clipped to the monitored window with a margin and thinned to about
500 m, which is finer than a 100 km map can show and small enough to inline.

Source: USGS ShakeMap us6000jllz v19 (see extract_shakemap.py for provenance).
    …/download/cont_mi.json      — 11 contour levels
    …/download/rupture.json      — finite-fault surface projection
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "shakemap-us6000jllz-geo.json"
WINDOW = HERE / "shakemap-us6000jllz.json"

MARGIN_DEG = 0.25  # a little beyond the grid, so lines enter and leave properly
MIN_STEP_DEG = 0.005  # ~500 m; finer than a 100 km map can resolve


def bounds() -> tuple[float, float, float, float]:
    """The monitored window, from the extract the agent already uses."""
    w = json.loads(WINDOW.read_text(encoding="utf-8"))
    lats = [c[0] for c in w["centres"].values()]
    lons = [c[1] for c in w["centres"].values()]
    half_lat = w["window"]["spacing_km"] / 111.0 / 2
    half_lon = half_lat / math.cos(math.radians(w["window"]["centre"][0]))
    return (
        min(lats) - half_lat - MARGIN_DEG, max(lats) + half_lat + MARGIN_DEG,
        min(lons) - half_lon - MARGIN_DEG, max(lons) + half_lon + MARGIN_DEG,
    )


def thin(points: list[list[float]]) -> list[list[float]]:
    """Drop points closer together than the map can show."""
    out: list[list[float]] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= MIN_STEP_DEG:
            out.append([round(p[0], 4), round(p[1], 4)])
    if len(out) < 2 and points:
        out = [[round(points[0][0], 4), round(points[0][1], 4)]]
    return out


def is_a_face(ring: list[list[float]]) -> bool:
    """Is this ring a surface, or a line pretending to be one?

    A steeply dipping fault projects to a sliver, so area is no use as a test —
    the real rupture is nearly zero-area too. What separates the two is that the
    degenerate ones fold back on themselves: [A, B, C, B, A] traces out and back
    along the same path, and drawing it produces a spike rather than an outline.
    Counting distinct vertices catches exactly that.
    """
    distinct = {tuple(p) for p in ring}
    return len(distinct) >= 4


def clip(points: list[list[float]], box) -> list[list[list[float]]]:
    """Split a line into the runs that fall inside the window."""
    lat0, lat1, lon0, lon1 = box
    runs, current = [], []
    for lon, lat, *_ in points:
        if lat0 <= lat <= lat1 and lon0 <= lon <= lon1:
            current.append([lon, lat])
        elif current:
            if len(current) > 1:
                runs.append(current)
            current = []
    if len(current) > 1:
        runs.append(current)
    return runs


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    box = bounds()
    contours = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    rupture = json.loads(Path(argv[2]).read_text(encoding="utf-8"))

    levels = []
    for feature in contours["features"]:
        geom, props = feature["geometry"], feature["properties"]
        lines = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
        kept = []
        for line in lines:
            for run in clip(line, box):
                thinned = thin(run)
                if len(thinned) > 1:
                    kept.append(thinned)
        if kept:
            levels.append({
                "mmi": props.get("value"),
                "color": props.get("color"),
                "lines": kept,
            })

    faces = []
    for feature in rupture["features"]:
        geom = feature["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for ring in poly:
                # Not thinned: the rupture is a few dozen points already, and
                # thinning is what folds a sliver into a spike.
                simple = [[round(c[0], 4), round(c[1], 4)] for c in ring]
                if is_a_face(simple):
                    faces.append(simple)

    payload = {
        "_": "Map furniture for the real-event scene: measured intensity contours and the "
             "finite-fault rupture. Generated by nabd/data/extract_geometry.py.",
        "source": {
            "event": "us6000jllz",
            "contours": "USGS ShakeMap cont_mi.json (isoseismals, official colours)",
            "rupture": "USGS ShakeMap rupture.json (finite-fault surface projection)",
            "retrieved": date.today().isoformat(),
        },
        "bounds": {"lat_min": round(box[0], 4), "lat_max": round(box[1], 4),
                   "lon_min": round(box[2], 4), "lon_max": round(box[3], 4)},
        "contours": levels,
        "rupture": faces,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    pts = sum(len(l) for lv in levels for l in lv["lines"])
    print(f"wrote {OUT.name}: {len(levels)} contour levels ({pts} pts), "
          f"{len(faces)} rupture face(s), {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
