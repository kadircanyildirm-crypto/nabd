#!/usr/bin/env python3
"""Extract the committed ShakeMap window from the USGS product.

    python nabd/data/extract_shakemap.py path/to/grid.xml

The event is read out of the grid itself and looked up in EVENTS below, so the
same command handles every earthquake the project carries. Adding one is a row
in that table: the window to watch, and the product it came from.

The published grid is 28 MB and 468,000 nodes; Nabd needs a hundred numbers.
This script does the reduction once and writes `shakemap-us6000jllz.json`, which
is what the package reads. It is committed alongside the extract so the number
in the repository can be traced back to the product it came from.

Source
------
USGS ShakeMap for **us6000jllz** — M 7.8 Pazarcık earthquake, Kahramanmaraş
sequence, 6 February 2023 01:17:34 UTC, 37.2256N 37.0143E, depth 10 km.
Grid product: https://earthquake.usgs.gov/product/shakemap/us6000jllz/us/1756921940993/download/grid.xml
ShakeMap version 19, constrained by 262 seismic stations and 1,459 intensity
observations, on a 0.0083° (~920 m) lattice covering 34–40°E, 34.6–40°N.

MMI here is ShakeMap's *estimated* macroseismic intensity — a model constrained
by those observations, not a measurement at every point. That distinction is
carried into the extract and into anything that quotes it.
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROW_LETTERS = "ABCDEFGHIJKLMNOPQRST"

# Each window is a 10x10 grid of 10 km cells, chosen at the scale the question
# "which district first" is actually asked at, and placed so the measured field
# varies across it — a window that is uniformly ruined or uniformly fine tests
# nothing.
EVENTS = {
    "us6000jllz": {
        "centre": (37.55, 37.05),
        "rows": 10, "cols": 10, "spacing_km": 10.0,
        "where": "Kahramanmaraş and the northern half of the rupture",
        "product": "https://earthquake.usgs.gov/product/shakemap/us6000jllz/us/1756921940993/download/grid.xml",
    },
    # The High Atlas above Marrakesh. Placed to hold both halves of what made
    # this event what it was: the mountain douars along the rupture, where the
    # roads were cut by landslides and nobody knew for days which had gone, and
    # Marrakesh itself in the north — a city of a million people that was shaken
    # hard enough to be on every television in the world and still answered.
    "us7000kufc": {
        "centre": (31.28, -8.28),
        "rows": 10, "cols": 10, "spacing_km": 10.0,
        "where": "the High Atlas from Amizmiz to Talat N'Yaaqoub, with Marrakesh in the north",
        "product": "https://earthquake.usgs.gov/product/shakemap/us7000kufc/us/1699242609676/download/grid.xml",
    },
}


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    spec = re.search(r"<grid_specification ([^/]*)/>", text).group(1)
    a = dict(re.findall(r'(\w+)="([^"]*)"', spec))
    ev = dict(re.findall(r'(\w+)="([^"]*)"', re.search(r"<event ([^/]*)/>", text).group(1)))
    fields = re.findall(r'<grid_field index="(\d+)" name="(\w+)"', text)
    names = [n for _, n in sorted(fields, key=lambda f: int(f[0]))]
    body = text[text.index("<grid_data>") + len("<grid_data>") : text.index("</grid_data>")]
    mmi_i = names.index("MMI")
    values = [float(line.split()[mmi_i]) for line in body.strip().split("\n")]
    return a, ev, values


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    a, ev, values = load(Path(argv[1]))
    event_id = argv[2] if len(argv) > 2 else ev.get("event_id")
    if event_id not in EVENTS:
        print(f"unknown event {event_id!r}; add a window for it to EVENTS", file=sys.stderr)
        return 2
    win = EVENTS[event_id]
    CENTRE, ROWS, COLS, SPACING_KM = win["centre"], win["rows"], win["cols"], win["spacing_km"]
    OUT = HERE / f"shakemap-{event_id}.json"
    lon0, lon1 = float(a["lon_min"]), float(a["lon_max"])
    lat0, lat1 = float(a["lat_min"]), float(a["lat_max"])
    nlon, nlat = int(a["nlon"]), int(a["nlat"])

    def node(i: int, j: int) -> float:
        return values[max(0, min(nlat - 1, i)) * nlon + max(0, min(nlon - 1, j))]

    clat, clon = CENTRE
    dlat = SPACING_KM / 111.0
    dlon = SPACING_KM / (111.0 * math.cos(math.radians(clat)))

    cells = {}
    geometry = {}
    for r in range(ROWS):
        for c in range(COLS):
            lat = clat + (ROWS / 2 - 0.5 - r) * dlat
            lon = clon + (c - COLS / 2 + 0.5) * dlon
            # The cell's own footprint, averaged — a mast's fate depends on the
            # shaking across the area it serves, not at a single point, and the
            # published field is patchy at station scale.
            i0 = round((lat1 - (lat + dlat / 2)) / (lat1 - lat0) * (nlat - 1))
            i1 = round((lat1 - (lat - dlat / 2)) / (lat1 - lat0) * (nlat - 1))
            j0 = round(((lon - dlon / 2) - lon0) / (lon1 - lon0) * (nlon - 1))
            j1 = round(((lon + dlon / 2) - lon0) / (lon1 - lon0) * (nlon - 1))
            window = [node(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
            cell_id = f"{ROW_LETTERS[r]}{c + 1}"
            cells[cell_id] = round(sum(window) / len(window), 2)
            geometry[cell_id] = [round(lat, 5), round(lon, 5)]

    payload = {
        "_": "Estimated macroseismic intensity (MMI) per monitored cell. Generated by "
             "nabd/data/extract_shakemap.py — do not edit by hand.",
        "event": {
            "id": ev.get("event_id"),
            "description": ev.get("event_description"),
            "magnitude": float(ev.get("magnitude", 0)),
            "depth_km": float(ev.get("depth", 0)),
            "origin_utc": ev.get("event_timestamp"),
            "epicentre": [float(ev.get("lat", 0)), float(ev.get("lon", 0))],
            "seismic_stations": int(ev.get("seismic_stations", 0)),
            "intensity_observations": int(ev.get("intensity_observations", 0)),
        },
        "source": {
            "product": win["product"],
            "shakemap_version": None,
            "retrieved": date.today().isoformat(),
            "note": "MMI is ShakeMap's estimated intensity field, constrained by the stations and "
                    "intensity observations above. It is a model, not a measurement at every point.",
        },
        "window": {
            "centre": list(CENTRE),
            "rows": ROWS,
            "cols": COLS,
            "spacing_km": SPACING_KM,
            "where": win["where"],
            "sampling": "mean of the published lattice nodes falling inside each cell",
        },
        "mmi": cells,
        "centres": geometry,
    }
    version = re.search(r'shakemap_version="(\d+)"', Path(argv[1]).read_text(encoding="utf-8")[:2000])
    if version:
        payload["source"]["shakemap_version"] = int(version.group(1))

    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lo = min(cells.values())
    hi = max(cells.values())
    print(f"wrote {OUT.name}: {len(cells)} cells, MMI {lo}–{hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
