"""Every number the film says out loud, checked against where it came from.

    python -m tests.test_nabd_provenance

A demo can be honest about its data and still drift: a script gets rewritten, a
scene gets re-tuned, and a sentence keeps a figure that stopped being true three
commits ago. Nobody notices, because narration is prose and prose is not run by
anything.

So it is run by this. Every number and every identifier in both narration
scripts has to be one of three things:

* **What the agent did in the scene that segment is showing** — read from
  `nac/evidence/nabd-scene-*.jsonl`. Scoped to that scene, so a figure that is
  true of some other scene does not pass here.
* **An external fact**, on the allowlist below with its source in writing.
* **A number that describes the design** — two gates, the three-cell floor, the
  thirty-second pass — also listed, also with what it refers to.

Adding a figure to a script means adding it here with where it came from. That
is the point: an unsourced number cannot reach the film.

The first version of this suite passed a deliberate lie — it allowed a
tolerance of ±1 on every figure, and "thirty-four cells" slid through on the
back of a thirty-three that existed in a different scene. `test_the_guard_
catches_a_lie` is here so that cannot go unnoticed twice.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from nabd import shakemap

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "nac" / "evidence"
ONSET = 125.0  # every scene's onset; the scripts count seconds from it

#: Facts about the world rather than about a run, each with its source.
EXTERNAL = {
    7.8: "USGS us6000jllz — magnitude 7.8",
    6.8: "USGS us7000kufc — magnitude 6.8",
    262: "USGS us6000jllz grid.xml — seismic_stations=262",
    1459: "USGS us6000jllz grid.xml — intensity_observations=1459",
    822: "USGS us7000kufc grid.xml — intensity_observations=822",
    19: "USGS us7000kufc — depth 19.0 km",
    2023: "both events occurred in 2023",
    2026: "MENA Ignite 2026",
    4: "04:17 local — the hour of the Pazarcık earthquake (01:17:34 UTC + 3)",
    17: "04:17 local — minutes past the hour",
    53000: "AFAD's official toll for the February 2023 sequence: 53,537",
    417: "04:17 local — the minute the Pazarcık earthquake struck",
    902: "09:02 — the scenes' own wall clock, thirty seconds after onset",
    72: "the 72-hour window — survival under rubble collapses past three days, "
        "standard urban search-and-rescue doctrine",
    7800: "Türkiye 783,562 km² ÷ 100 km² a cell = 7,836 sentinel cells",
    85: "Türkiye's population, about 85 million — the point being that the grid "
        "scales with land area and not with people",
}

#: Numbers that describe how the agent is built, not what it found.
DESIGN = {
    1: "one signal never declares alone; one function chooses the network; one more pass",
    2: "two layers; two gates; two corroborations; two claims separated",
    3: "the three-cell size floor; three CAMARA APIs; three abstentions in the noise scene",
    30: "the thirty-second pass cadence",
    55: "declared 55 s after onset — asserted separately by tests/test_nabd_real.py",
}

WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
}
TR_WORDS = {
    "sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6,
    "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30,
    "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80,
    "doksan": 90, "yüz": 100, "bin": 1000,
}
LETTERS = "abcdefghijr"  # a cell's row letter, or the R of a registry id

#: A year, a clock and a date are not claims about data, so they are read as
#: what they are before anything is counted. Each is here with what it says.
NORMALISE = [
    (r"twenty twenty[- ]three", " 2023 "),                 # the year, spoken
    (r"twenty twenty[- ]six", " 2026 "),                   # the year, spoken
    (r"iki bin yirmi üç", " 2023 "),
    (r"iki bin yirmi altı", " 2026 "),
    (r"seventeen minutes past four in the morning", " 0417 "),   # 04:17 local
    (r"dördü on yedi geçe", " 0417 "),
    (r"nine oh two", " 0902 "),                            # the scenes' wall clock
    (r"dokuz sıfır iki", " 0902 "),
    (r"sixth of february", " datemark "),                  # a date is not a figure
    (r"altı şubat", " datemark "),
    (r"eighth of september", " datemark "),
    (r"sekiz eylül", " datemark "),
    # Turkish takes suffixes on its number words, which would end a run early:
    # "elli üç binden fazla" is fifty-three thousand, not fifty-three.
    (r"\bbin(?:den|e|i|in|le|lerce)\b", " bin "),
    # "yüz" is deliberately not treated this way: "bu yüzden" and "o yüzden"
    # mean *therefore*, and reading them as a hundred is how this suite first
    # accused the Turkish script of saying 102.
    (r"\bnineteen kilometres\b", " 19km "),                # the depth, in the allowlist
    (r"\bon dokuz kilometre\b", " 19km "),
]

#: Words that continue a spoken number rather than ending it.
CONTINUE = {"and", "ve"}


def normalise(text: str) -> str:
    out = text.lower()
    for pattern, replacement in NORMALISE:
        out = re.sub(pattern, replacement, out)
    return out


def _ids(text: str, words: dict[str, int]) -> tuple[set[str], str]:
    """Pull "F five" and "R zero one zero" out as ids, and return the rest.

    Spoken identifiers would otherwise be read as quantities — "F five" as a
    five — so they are lifted out and checked against the registry and the grid
    instead, which is a stronger check than counting them.
    """
    names = "|".join(words)
    pattern = re.compile(rf"\b([{LETTERS}])\s+((?:(?:{names})\s*){{1,3}})", re.I)
    found: set[str] = set()
    for m in pattern.finditer(text):
        digits = [str(words[w]) for w in re.findall(rf"{names}", m.group(2).lower())]
        if not digits:
            continue
        letter = m.group(1).upper()
        found.add(f"{letter}-{''.join(digits)}" if len(digits) > 1 else f"{letter}{digits[0]}")
    return found, pattern.sub(" ", text)


def spoken_numbers(text: str, words: dict[str, int]) -> set[int]:
    """Every number a listener would hear, from digits and from number words."""
    found: set[int] = set()
    for token in re.findall(r"\d[\d,.]*", text):
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        if value == int(value):
            found.add(int(value))

    tokens = re.findall(r"[a-zçğıöşü]+", text.lower().replace("-", " "))
    run, total, current = False, 0, 0
    for word in tokens + ["."]:
        if run and word in CONTINUE:      # "two hundred and sixty-two"
            continue
        if word in words:
            run = True
            value = words[word]
            if value == 100:
                current = max(current, 1) * 100
            elif value == 1000:
                total += max(current, 1) * 1000
                current = 0
            else:
                current += value
        elif run:
            found.add(total + current)
            run, total, current = False, 0, 0
    return {n for n in found if n}


def scene_facts(name: str) -> tuple[set[int], set[str]]:
    """(numbers, identifiers) that are true of one scene, from its evidence."""
    path = EVIDENCE / f"nabd-scene-{name}.jsonl"
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    nums: set[int] = {len(records)}
    ids: set[str] = set()
    kinds: dict[str, int] = {}
    for r in records:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        nums |= {int(r["t"]), int(r["t"] - ONSET), round((r["t"] - ONSET) / 60)}
        if r["cells"]:
            nums.add(len(r["cells"]))
            ids |= set(r["cells"])
            for spacing in (0.67, 10.0):          # the city grid, and the regional one
                nums.add(round(len(r["cells"]) * spacing ** 2))
        for line in r["signals"] + [r["reason"], r.get("brief") or ""]:
            nums |= spoken_numbers(line, WORDS)
        if r.get("triage"):
            nums |= {r["triage"]["inside"], r["triage"]["unreachable"], r["triage"]["calls"]}
            for person in r["triage"]["top"]:
                ids.add(person["person"])
                ids.add(person["cell"])
                if person.get("last_seen"):
                    radius = person["last_seen"]["radius_m"]
                    nums |= {radius, round(radius / 100) * 100, round(radius, -2)}
        if r.get("privacy"):
            nums.add(r["privacy"].get("personal", 0))
    nums |= set(kinds.values())                    # "three abstentions"
    return {n for n in nums if n}, ids


def segments() -> list[tuple[str, str, str, list[str]]]:
    """(id, english, turkish, the scenes that segment shows)."""
    tree = ast.parse((ROOT / "docs/video/build.py").read_text(encoding="utf-8"))
    order, english, scenes, turkish = [], {}, {}, {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        name = getattr(node.targets[0], "id", "")
        if name == "SEGMENTS":
            for call in node.value.elts:
                sid = call.args[0].value
                order.append(sid)
                english[sid] = next(k.value.value for k in call.keywords if k.arg == "text")
                frames = next((k.value for k in call.keywords if k.arg == "frames"), None)
                scenes[sid] = sorted({e.elts[0].value for e in frames.elts}) if frames else []
        elif name == "TURKISH":
            turkish = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
    return [(sid, english[sid], turkish.get(sid, ""), scenes[sid]) for sid in order]


def _check(sid: str, text: str, words: dict[str, int], scenes: list[str]) -> list[str]:
    """Anything in this segment's narration that nothing backs."""
    ids, rest = _ids(normalise(text), words)
    said = spoken_numbers(rest, words)

    allowed: set[int] = set(DESIGN)
    known_ids: set[str] = set()
    for value in EXTERNAL:
        allowed |= spoken_numbers(str(value), words)
    for scene in scenes:
        nums, sids = scene_facts(scene)
        allowed |= nums
        known_ids |= sids

    def backed(n: int) -> bool:
        # Exact under a hundred: a count is a count. A narrator rounds larger
        # figures — "six thousand three hundred", "thirteen hundred metres" —
        # so a percent of slack is allowed there and nowhere else.
        return n in allowed or (n >= 100 and any(abs(n - a) <= a * 0.01 for a in allowed if a >= 100))

    bad = [f"{n}" for n in sorted(said) if not backed(n)]
    bad += [f"id {i}" for i in sorted(ids) if known_ids and i not in known_ids]
    return bad


def test_every_number_in_the_narration_is_sourced():
    """No figure reaches the film that its own scene, or a cited source, cannot back."""
    problems = []
    for sid, en, tr, scenes in segments():
        for lang, text, words in (("en", en, WORDS), ("tr", tr, TR_WORDS)):
            if not text:
                continue
            bad = _check(sid, text, words, scenes)
            if bad:
                problems.append(f"{sid} [{lang}] says {bad}"
                                + (f" — shown scenes: {scenes}" if scenes else " — card, no scene"))
    assert not problems, "unsourced figures in the narration:\n  " + "\n  ".join(problems)
    print("        every number and id in both scripts traces to its own scene or to a cited source")


def test_the_guard_catches_a_lie():
    """The suite's own test: a wrong figure in a real segment must not pass.

    The first version of this file allowed ±1 on everything and let a
    thirty-four through because some other scene had a thirty-three.
    """
    _, _, _, scenes = next(s for s in segments() if s[0] == "11-real")
    honest = "It declares twenty-one cells, about six thousand three hundred square kilometres."
    lie = "It declares thirty-four cells, about six thousand three hundred square kilometres."
    assert not _check("11-real", honest, WORDS, scenes), "the honest sentence should pass"
    assert _check("11-real", lie, WORDS, scenes) == ["34"], "the guard missed a wrong cell count"
    print("        a wrong cell count in the real-event segment is caught")


def test_the_shakemap_extracts_match_the_products_they_name():
    """The committed numbers cannot drift from the ShakeMaps they were reduced from."""
    expected = {
        shakemap.KAHRAMANMARAS: dict(magnitude=7.8, stations=262, observations=1459,
                                     origin="2023-02-06T01:17:34", version=19),
        shakemap.AL_HAOUZ: dict(magnitude=6.8, stations=3, observations=822,
                                origin="2023-09-08T22:11:01", version=14),
    }
    for event, want in expected.items():
        sm = shakemap.load(event)
        assert sm.event["id"] == event
        assert sm.event["magnitude"] == want["magnitude"], sm.event
        assert sm.event["seismic_stations"] == want["stations"], sm.event
        assert sm.event["intensity_observations"] == want["observations"], sm.event
        assert sm.event["origin_utc"].startswith(want["origin"]), sm.event
        assert sm.source["shakemap_version"] == want["version"], sm.source
        assert event in sm.source["product"] and "earthquake.usgs.gov" in sm.source["product"]
        print(f"        {event}: M{want['magnitude']}, {want['stations']} stations, "
              f"v{want['version']} — as published")


def test_every_committed_data_file_says_where_it_came_from():
    """A map or a field with no provenance is a drawing, and cannot be used as evidence."""
    for path in sorted((ROOT / "nabd" / "data").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        source = raw.get("source")
        assert source, f"{path.name} carries no source"
        text = json.dumps(source, ensure_ascii=False).lower()
        assert any(k in text for k in ("openstreetmap", "usgs", "natural earth", "geonames")), \
            f"{path.name}: source names no origin — {source}"
        assert "retrieved" in text or "shakemap_version" in text, f"{path.name}: source has no date"
    print("        every file under nabd/data names its origin and when it was taken")


def test_the_console_says_it_is_a_simulator_on_every_frame():
    """Nothing on screen may let a viewer believe a live network answered."""
    html = (ROOT / "nabd" / "replay.html").read_text(encoding="utf-8")
    assert "offline simulator" in html, "the console must name its backend"
    assert "OpenStreetMap contributors" in html and "USGS ShakeMap" in html, "credits missing"
    print("        the console names its backend and its sources in shot, on every frame")


if __name__ == "__main__":
    from tests.run import main as _run

    raise SystemExit(_run(["tests.test_nabd_provenance"]))
