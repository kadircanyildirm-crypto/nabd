# What is real, and what is ours

Nabd shows a map. This is the line-by-line answer to the only question that
matters about it: **where did that come from?**

The short version: **the world is real, the network is simulated.** Every
geographic and seismic fact on screen is a published dataset, committed with
its product URL and retrieval date. Every network reading is produced by a
simulator, and the console says so on every frame — the footer reads
`backend offline simulator`.

Nothing here is asserted. `tests/test_nabd_provenance.py` checks it, and
`python -m nabd.parity` measures the seam between the simulated path and the
live one.

---

## Real — published data, committed with its source

| On screen | Source | Where it lives |
|---|---|---|
| Roads, water, railways, place names | **OpenStreetMap** contributors (ODbL), via the Overpass API | `nabd/data/basemap-{city,mid,region}*.json` |
| Provincial and national boundaries | **Natural Earth** (public domain) | `nabd/data/basemap.json` |
| Populated-place names and ranks | OpenStreetMap; **GeoNames** (CC BY) for the regional set | same files |
| Shaking intensity per cell (MMI) | **USGS ShakeMap** `us6000jllz` v19 — M7.8 Pazarcık, 6 Feb 2023, 262 seismic stations, 1,459 intensity observations | `nabd/data/shakemap-us6000jllz.json` |
| Isoseismal contours and their colours | the same product's `cont_mi.json` | `nabd/data/shakemap-us6000jllz-geo.json` |
| Fault rupture (surface projection) | the same product's `rupture.json` | same file |
| Shaking, contours and rupture, second event | **USGS ShakeMap** `us7000kufc` v14 — M6.8 Al Haouz, 8 Sep 2023, 3 seismic stations, 822 intensity observations | `nabd/data/shakemap-us7000kufc*.json` |
| The grid's own coordinates | computed from the ShakeMap window, at the real latitude and longitude of every cell | `nabd/shakemap.py` |

Every one of those files carries a `source` block with the product URL and the
date it was taken, and a test fails if any of them does not.

## Ours — a model, and it says so

| On screen | What it actually is |
|---|---|
| Which cells fall silent, and when | **Our rule**, applied to the real intensity field: above MMI 8 a mast is dark from the first second; between 7 and 8 it survives, runs on battery and dies later, sooner where the shaking was worse. Stated as an assumption in `nabd/shakemap.py`, with the two field reports it is drawn from. |
| Congestion levels (Low / Medium / High) | Simulated. A real Congestion Insights feed would supply these. |
| The 48-person registry | **Invented and pseudonymous.** `R-001`…`R-048`, generated from a seed. No real person appears anywhere in this project. |
| Last-seen positions and their radii | Simulated, inside the cell the person belongs to. |
| The maintenance calendar (ticket `MNT-2214`) | Invented, to give the detector something legitimate to refuse. |
| Scenes 1–4 (quiet, earthquake, look-alikes, chronic degradation) | **Entirely drawn worlds.** They are the unit tests of the idea, not observations. |
| Every CAMARA call | Made against the offline gateway. The call *shapes* are the real SDK's — `tests/test_nabd_live_wiring.py` resolves all three endpoints against the installed `network_as_code` package — but no call has left this machine. |

## Not done yet, and never claimed as done

- **The live Network-as-Code run.** It needs an API key. Until it happens,
  `python -m nabd.parity` reports check 4 as **PENDING**, never as PASS, and
  the deck's honest-boundaries slide says so in as many words.

---

## How this is enforced

| Check | What it catches |
|---|---|
| `test_every_number_in_the_narration_is_sourced` | A figure in either narration script that the scene it is showing does not support, or that is not on a written allowlist of external facts. Scoped per segment, so a number true of another scene does not pass. |
| `test_the_guard_catches_a_lie` | The guard above going soft. It plants a wrong cell count and requires it to be caught — the first version of the suite let one through. |
| `test_the_shakemap_extracts_match_the_products_they_name` | The committed intensity fields drifting from the ShakeMaps they were reduced from. |
| `test_every_committed_data_file_says_where_it_came_from` | A map file with no source or no date. |
| `test_the_console_says_it_is_a_simulator_on_every_frame` | The console ever hiding that its backend is a simulator, or dropping its map and intensity credits. |
| `test_nothing_was_retuned_for_the_second_event` | Al Haouz being quietly tuned into agreement. Both real scenes must run on the same thresholds, and those must be the class's own defaults. |
| `test_neither_map_names_a_cell_the_shaking_leaves_standing` | The map inventing damage — every cell either scene ever declares must be one the measured field condemns. |
| `python -m nabd.parity` | The simulated path and the live path diverging. Every scene is replayed through the same three response parsers the live gateway uses, and the evidence has to come out identical, line for line. |

## Two figures worth naming

Both were wrong until this audit, and both are now what the record supports:

- **Türkiye's population**, about 85 million — the point being that a sentinel
  grid scales with land area rather than with people. It previously said "85
  million subscribers", which conflated the population with mobile
  subscriptions (about 91 million).
- **Derna, Libya: 4,000+ confirmed dead, thousands still missing.** It
  previously said 11,000+, a figure from an early Libyan Red Crescent
  statement that the organisation's own head later disowned; WHO and OCHA
  verified about four thousand.
