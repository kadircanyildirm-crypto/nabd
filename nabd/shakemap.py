"""The real events: measured ground motion driving which cells go silent.

Four of Nabd's scenes are worlds we drew. Two are not. The intensity fields
come from published USGS ShakeMaps, and `nabd/data/extract_shakemap.py` reduces
each 7-to-28 MB grid to the hundred numbers this module reads, recording where
they came from.

* **us6000jllz** — M7.8 Pazarcık, 6 February 2023 01:17:34 UTC, the first of
  the Kahramanmaraş sequence. ShakeMap v19, constrained by 262 seismic stations
  and 1,459 intensity observations.
* **us7000kufc** — M6.8 Al Haouz, 8 September 2023 22:11:01 UTC, in the High
  Atlas above Marrakesh. ShakeMap v14, constrained by **3** seismic stations
  and 822 intensity observations.

Those two station counts are worth sitting with. The instrument network that
tells a responder what happened is not evenly distributed across the world, and
in the places where it is thinnest the answer arrives slowest. The mobile
network is already there and already talking.

What is real and what is ours
-----------------------------
**Real:** the geometry, and the intensity of shaking in every cell.

**Ours, and stated as an assumption:** the rule that turns shaking into a
silent cell. Two mechanisms, both reported from the 2023 Türkiye event rather
than invented:

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

The thresholds are calibrated so that the fraction of the Kahramanmaraş window
that eventually goes dark lands on that reported "more than half", and
`tests/test_nabd_real.py` asserts it still does. They remain an assumption; the
scenes say so on their face, and changing them changes one line.

Why a second event
------------------
Because a detector validated against the one event it was tuned on has not been
validated. Al Haouz is a **held-out test**: the same thresholds, not touched, in
a different country, a different terrain and a different kind of earthquake, and
`test_nothing_was_retuned_for_the_second_event` is what keeps that true.

It does not flatter the detector, which is the point. An M6.8 at 19 km depth
puts almost nothing above the collapse threshold — a pocket at the epicentre,
below the three-cell size floor — so the agent abstains on the first pass and
declares nearly four minutes later, at MEDIUM rather than HIGH, once enough
sites have drained their batteries to make a block. The reason is written into
the evidence: the onset genuinely was not synchronised. Meanwhile Marrakesh, in
the north of the window at about intensity 6, is shaken hard enough to lead the
news everywhere and answers throughout, and is never named.

Sources
-------
* USGS ShakeMap, event us6000jllz v19, and event us7000kufc v14 — the fields.
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

DATA = Path(__file__).resolve().parent / "data"

#: The earthquakes the project carries, newest window first in the demo order.
#: Both go through this module unchanged; nothing here knows which country it is
#: reading, which is the whole reason the second one is worth anything.
KAHRAMANMARAS = "us6000jllz"
AL_HAOUZ = "us7000kufc"

#: Which event a scene is run over, so a test or a view can look it up by name.
EVENT_OF = {"maras": KAHRAMANMARAS, "atlas": AL_HAOUZ}


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


@lru_cache(maxsize=4)
def load(event: str = KAHRAMANMARAS) -> ShakeMap:
    """The extracted window for one USGS event id."""
    raw = json.loads((DATA / f"shakemap-{event}.json").read_text(encoding="utf-8"))
    return ShakeMap(
        event=raw["event"],
        source=raw["source"],
        window=raw["window"],
        mmi=dict(raw["mmi"]),
        centres=dict(raw["centres"]),
    )
