"""The real event: measured ground motion driving which cells go silent.

Every other scene in Nabd is a world we drew. This one is not. The intensity
field comes from the USGS ShakeMap for **us6000jllz** — the M 7.8 Pazarcık
earthquake of 6 February 2023, 01:17:34 UTC, the first of the Kahramanmaraş
sequence — constrained by 262 seismic stations and 1,459 intensity
observations. `nabd/data/extract_shakemap.py` reduces the published 28 MB grid
to the hundred numbers this module reads, and records where they came from.

What is real and what is ours
-----------------------------
**Real:** the geometry, and the intensity of shaking in every cell.

**Ours, and stated as an assumption:** the rule that turns shaking into a
silent cell. Two mechanisms, both reported from the event rather than invented:

* *Collapse.* Turkish base stations are largely mounted on buildings, and the
  buildings came down: the Natural Hazards Center's field report records that
  "most of the base stations for mobile phones were destroyed along with the"
  structures that carried them. Above `collapse_mmi` a cell is dark from the
  first second.
* *Power.* Turkcell reported sending some 250 portable base stations because
  "more than half of the local base stations were rendered inoperative", with
  the survivors unable to run "due to power outages". Between `power_mmi` and
  `collapse_mmi` a site survives the shaking, runs on battery, and goes dark
  later — sooner where the shaking was worse.

The thresholds are calibrated so that the fraction of the monitored window
that eventually goes dark lands on that reported "more than half", and
`tests/test_nabd_real.py` asserts it still does. They remain an assumption; the
scene says so on its face, and changing them changes one line.

Sources
-------
* USGS ShakeMap, event us6000jllz, version 19 — the intensity field.
* Natural Hazards Center, *Communication and Coordination Networks in the 2023
  Kahramanmaraş Earthquakes* (quick response report) — collapse mechanism,
  ">half inoperative", power outages, and the multi-day restoration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from nabd.model import Cell, Grid

DATA = Path(__file__).resolve().parent / "data" / "shakemap-us6000jllz.json"


@dataclass(frozen=True)
class ShakeMap:
    """The extracted intensity window, with the provenance attached."""

    event: dict
    source: dict
    window: dict
    mmi: dict[str, float]
    centres: dict[str, list[float]]

    @property
    def citation(self) -> str:
        e, s = self.event, self.source
        return (
            f"USGS ShakeMap {e['id']} v{s['shakemap_version']} — M{e['magnitude']} "
            f"{e['description']}, {e['origin_utc']}Z, {e['seismic_stations']} stations / "
            f"{e['intensity_observations']} intensity observations"
        )

    def grid(self) -> Grid:
        """The monitored grid, at the real coordinates the intensities were sampled at."""
        rows, cols = self.window["rows"], self.window["cols"]
        letters = "ABCDEFGHIJKLMNOPQRST"
        cells = []
        for r in range(rows):
            for c in range(cols):
                cell_id = f"{letters[r]}{c + 1}"
                lat, lon = self.centres[cell_id]
                cells.append(Cell(cell_id, r, c, lat, lon, sentinel=f"+9990{r:02d}{c:02d}"))
        return Grid(tuple(cells), rows, cols, self.window["spacing_km"] * 1000.0)

    def band(self, low: float, high: float = 99.0) -> tuple[str, ...]:
        """Cells whose estimated intensity falls in [low, high)."""
        return tuple(sorted(c for c, v in self.mmi.items() if low <= v < high))


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> ShakeMap:
    raw = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    return ShakeMap(
        event=raw["event"],
        source=raw["source"],
        window=raw["window"],
        mmi=dict(raw["mmi"]),
        centres=dict(raw["centres"]),
    )
