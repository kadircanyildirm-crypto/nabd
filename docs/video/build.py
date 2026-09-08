#!/usr/bin/env python3
"""Build Nabd-Demo.mp4 from the evidence, the console and a narration script.

    pip install playwright edge-tts && playwright install chromium
    python docs/video/build.py                # everything, resumable
    python docs/video/build.py --only 11-real # rebuild one segment's assets
    python docs/video/build.py --no-tts       # reuse the narration already rendered

The previous build of this video lived in a session scratchpad and was lost, so
the deck could no longer be regenerated when the prototype moved on. It lives in
the repository now.

Nothing on screen is mocked. Card frames are `docs/video/cards.html`; every
other frame is `nabd/replay.html` — the real command-centre console — opened at
a named pass, and the console draws only from `nac/evidence/nabd-scene-*.jsonl`.
Change the agent, re-run the scenes, re-run this, and the video follows.

Pipeline: narration → edge-tts mp3 per segment (durations measured with
ffprobe) → Playwright/Chromium screenshots at 1920×1080 → ffmpeg concat
demuxer, durations quantised to whole frames so picture and voice never drift.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
CARDS = HERE / "cards.html"
CONSOLE = ROOT / "nabd" / "replay.html"
OUT = ROOT / "Nabd-Demo.mp4"

FPS = 30
VOICE = "en-US-AndrewNeural"
RATE = "+10%"
TAIL_PAD = 0.45  # silence after each narration segment, so cuts never clip a word

# The console is built for a browser window, not a 16:9 frame. This makes the
# map big enough to read at 1080p and lays the side panels out in two columns
# so a whole pass fits one frame without scrolling.
CONSOLE_CSS = """
  header { padding: 10px 22px; }
  main { grid-template-columns: 660px 1fr !important; gap: 14px; padding: 12px 22px; }
  aside { display: grid !important; grid-template-columns: 1fr 1fr; gap: 10px; align-content: start; }
  aside > .card:first-child { grid-column: 1 / -1; }
  /* Keep the tall panels from pushing the registry and the log off the frame:
     a video frame has to show the whole pass at once. */
  .brief { font-size: 12.5px !important; line-height: 1.34 !important; max-height: 232px; overflow: hidden; }
  #zones { max-height: 232px; overflow: hidden; }
  #registry { max-height: 214px; overflow: hidden; }
  .log { max-height: 214px; }
  aside .card h3 { margin-bottom: 6px; }
  .controls { display: none !important; }
"""


@dataclass
class Segment:
    id: str
    text: str
    card: str | None = None
    frames: list[tuple[str, int]] = field(default_factory=list)  # (scene, pass)
    min_s: float = 0.0

    @property
    def audio(self) -> Path:
        return BUILD / f"{self.id}.mp3"

    def stills(self) -> list[Path]:
        if self.card:
            return [BUILD / f"{self.id}.png"]
        return [BUILD / f"{self.id}-{i:02d}.png" for i in range(len(self.frames))]


SEGMENTS = [
    Segment(
        "01-title", card="c01-title",
        text="Nabd. Read where the network goes silent. An AI agent for disaster impact mapping, "
             "built on Nokia Network-as-Code and LangGraph.",
    ),
    Segment(
        "02-problem", card="c02-problem",
        text="A seismometer says 'it happened' within seconds. The question that costs lives — which "
             "district first, and who is cut off — arrives hours later. In Kahramanmaraş in 2023, more "
             "than fifty-three thousand people died. Nabd is not early warning. It is the impact map in "
             "the first minute, and triage across the first seventy-two hours.",
    ),
    Segment(
        "03-insight", card="c03-insight",
        text="Coordinated network silence is a sensor. Detection is aggregate: a grid of sentinel "
             "devices — municipal or operator-owned SIMs, one per cell, never the public — read every "
             "thirty seconds. Triage is consented: only inside a declared footprint, and only for people "
             "who opted in to be found.",
    ),
    Segment(
        "04-quiet", frames=[("quiet", 2), ("quiet", 6), ("quiet", 9)],
        text="This is the command centre. Each square is a cell with one sentinel. On an ordinary "
             "morning every sentinel answers, and the agent has nothing to report.",
    ),
    Segment(
        "05-onset", frames=[("quake", 4), ("quake", 5)],
        text="Nine-oh-two: an earthquake. Nobody yet knows which neighbourhoods are hit. Nine cells fall "
             "silent at once — but the agent marks a candidate and holds one more pass, because one "
             "signal never declares alone.",
    ),
    Segment(
        "06-declare", frames=[("quake", 6)],
        text="Fifty-five seconds after onset it declares: nine cells, about four square kilometres, "
             "confidence HIGH. Two gates passed — the block is contiguous, and this silence is abnormal "
             "here — and two corroborations: a synchronised onset, and a hot ring, sixteen of sixteen "
             "neighbouring cells saturated as everyone calls at once.",
    ),
    Segment(
        "07-triage", frames=[("quake", 6), ("quake", 7)],
        text="Only now does the agent touch a personal device. Thirteen registered people live inside "
             "the footprint; six are unreachable, ranked by need, each with a last-seen position. Every "
             "pass of the evidence states whether that personal path was open and how many calls it "
             "made. On an ordinary morning, that number is zero on every line.",
    ),
    Segment(
        "08-update", frames=[("quake", 14), ("quake", 16)],
        text="The picture keeps moving. Four minutes on, two people answer again and the list shrinks "
             "from six to four, without anyone touching it.",
    ),
    Segment(
        "09-lookalikes", frames=[("noise", 2), ("noise", 6), ("noise", 10)],
        text="A detector is only useful if it stays quiet on look-alikes. One cell silent with normal "
             "neighbours: a cell fault. Four contiguous cells silent, matching a maintenance ticket on "
             "the operator's calendar: expected. Nine cells saturated while every sentinel answers: a "
             "stadium crowd. Three abstentions, three written reasons, no false alarm.",
    ),
    Segment(
        "10-degraded", frames=[("degraded", 11), ("degraded", 21)],
        text="Then the hardest one. Four cells on a failing backhaul reproduce every signal an impact "
             "has, and no calendar explains them. The agent measures them instead: these cells were "
             "already unreachable in three of the last eleven passes. Silence here is the local normal, "
             "so it is not news. And in the same run, a real earthquake in the city centre is still "
             "declared. The refusal is measured, and it is not blindness.",
    ),
    Segment(
        "11-real", frames=[("maras", 6), ("maras", 15), ("maras", 23)],
        text="Then we stopped drawing the disaster. The geometry and the intensity of shaking in every "
             "cell here come from the USGS ShakeMap for the magnitude seven point eight Pazarcık "
             "earthquake of the sixth of February, 2023 — constrained by two hundred and sixty-two "
             "seismic stations. Fifty-five seconds after onset: twenty-one contiguous cells, twenty-one "
             "hundred square kilometres. Every cell it names is one the measured shaking places above "
             "the collapse threshold; it invents no damage. Two more, an isolated pocket below the size "
             "floor, it deliberately does not claim. Then the footprint grows to six thousand three "
             "hundred square kilometres as the surviving masts lose power and drain their batteries — "
             "which is exactly what the field reports describe.",
    ),
    Segment(
        "12-hood", card="c10-hood",
        text="Under the hood the agent is a LangGraph graph, and the conditional edge is the privacy "
             "claim made literal: the node that queries a personal device is reachable only from a "
             "verdict with an active footprint. Detection is deterministic and replayable; the language "
             "model writes the duty officer's brief and nothing else. The plain loop and the LangGraph "
             "runner agree byte for byte, under eighty-three tests.",
    ),
    Segment(
        "13-parity", card="c11-parity",
        text="The sandbox cannot stage a disaster, so the two claims are separated: the live platform "
             "proves the integration, the simulator proves the scenario. The risk was never the "
             "simulator — it was a suspected discontinuity between the two paths. So that is what gets "
             "measured. Every scene is recorded and replayed through the same three parsing functions "
             "the live gateway uses, and the evidence has to come out identical line for line.",
    ),
    Segment(
        "14-close", card="c12-close",
        text="Nabd is disaster-agnostic: earthquake, flood, storm or mass outage — an area goes dark. "
             "Buyers are civil-defence agencies and municipalities, through the operator's Open Gateway. "
             "The network already knows. Nabd makes it say so, in the first minute. By Kadir's Team, for "
             "MENA Ignite 2026.",
    ),
]


# ---------------------------------------------------------------- narration


async def _tts(text: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out))


def narrate(segments: list[Segment], skip: bool) -> None:
    for seg in segments:
        if seg.audio.exists() and skip:
            continue
        print(f"  tts   {seg.id}")
        asyncio.run(_tts(seg.text, seg.audio))


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ------------------------------------------------------------------ frames


def shoot(segments: list[Segment]) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # Cards are authored at 1920x1080 and shot at scale 1; the console is a
        # 1600x900 layout scaled 1.2 to fill the same frame.
        cards = [s for s in segments if s.card]
        if cards:
            page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            page.goto(CARDS.as_uri())
            page.wait_for_timeout(400)
            for seg in cards:
                print(f"  card  {seg.id}")
                page.locator(f"#{seg.card}").screenshot(path=str(seg.stills()[0]))
            page.close()

        shots = [s for s in segments if not s.card]
        if shots:
            page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
            page.goto(CONSOLE.as_uri())
            page.wait_for_timeout(600)
            page.add_style_tag(content=CONSOLE_CSS)
            for seg in shots:
                for i, (scene, index) in enumerate(seg.frames):
                    print(f"  frame {seg.id}-{i:02d}  #{scene}/{index}")
                    page.evaluate(f"location.hash = '#{scene}/{index}'")
                    page.wait_for_timeout(450)
                    page.screenshot(path=str(seg.stills()[i]), clip={"x": 0, "y": 0, "width": 1600, "height": 900})
        browser.close()


# ---------------------------------------------------------------- assembly


def quantise(seconds: float) -> float:
    return round(seconds * FPS) / FPS


def assemble(segments: list[Segment]) -> None:
    concat = BUILD / "frames.txt"
    silence = BUILD / "pad.mp3"
    if not silence.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(TAIL_PAD), "-q:a", "9", str(silence), "-y"], check=True,
        )

    lines: list[str] = []
    audio_parts: list[Path] = []
    timeline: list[tuple[str, float, float, list[str]]] = []
    total = 0.0
    for seg in segments:
        span = quantise(max(seg.min_s, duration(seg.audio) + TAIL_PAD))
        stills = seg.stills()
        each = quantise(span / len(stills))
        for i, still in enumerate(stills):
            hold = each if i < len(stills) - 1 else quantise(span - each * (len(stills) - 1))
            lines.append(f"file '{still.as_posix()}'")
            lines.append(f"duration {hold:.4f}")
        audio_parts += [seg.audio, silence]
        shown = [seg.card] if seg.card else [f"{scene} - pass {i}" for scene, i in seg.frames]
        timeline.append((seg.id, total, span, shown))
        total += span
        print(f"  {seg.id:<14} {span:6.2f}s  {len(stills)} frame(s)")
    lines.append(f"file '{segments[-1].stills()[-1].as_posix()}'")  # concat demuxer needs the last file twice
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    alist = BUILD / "audio.txt"
    alist.write_text("\n".join(f"file '{p.as_posix()}'" for p in audio_parts) + "\n", encoding="utf-8")
    voice = BUILD / "voice.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alist),
         "-c:a", "aac", "-b:a", "160k", str(voice), "-y"], check=True,
    )

    write_timeline(timeline, total)
    print(f"\n  muxing {total:.1f}s → {OUT.name}")
    subprocess.run(
        ["ffmpeg", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(voice),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "20",
         "-preset", "medium", "-movflags", "+faststart",
         "-c:a", "copy", "-shortest", str(OUT), "-y"], check=True,
    )


def write_timeline(rows: list[tuple[str, float, float, list[str]]], total: float) -> None:
    """The shot list, regenerated from the build so it cannot drift from the film."""
    by_id = {s.id: s for s in SEGMENTS}
    out = [
        "# Nabd — demo video shot list",
        "",
        f"*Generated by `python docs/video/build.py`. {OUT.name} · 1920×1080 · "
        f"{int(total // 60)}:{int(total % 60):02d} · English narration "
        f"({VOICE} via edge-tts, rate {RATE}).*",
        "",
        "Every console frame below is `nabd/replay.html` — the real command-centre console —",
        "opened at the named pass. The console draws only from `nac/evidence/nabd-scene-*.jsonl`,",
        "so nothing on screen is mocked: change the agent, re-run the scenes, re-run the build,",
        "and the film follows. Card frames are `docs/video/cards.html`.",
        "",
        "| Start | Segment | Length | On screen | Narration |",
        "|---|---|---|---|---|",
    ]
    for seg_id, start, span, shown in rows:
        text = by_id[seg_id].text.replace("|", "/")
        out.append(
            f"| {int(start // 60)}:{start % 60:04.1f} | `{seg_id}` | {span:.1f}s | "
            f"{' → '.join(shown)} | {text} |"
        )
    out += [
        "",
        "## Rebuilding",
        "",
        "```bash",
        "pip install playwright edge-tts && playwright install chromium",
        "python -m nabd.scene --console      # refresh the evidence and the console first",
        "python docs/video/build.py          # narration, frames, mux — resumable",
        "```",
        "",
        "`--only <segment>` rebuilds one segment's assets; `--no-tts` / `--no-shoot` reuse what is",
        "already rendered. Durations are quantised to whole frames at "
        f"{FPS} fps so picture and voice never drift, and each narration segment is padded with "
        f"{TAIL_PAD}s of silence so a cut never clips a word.",
        "",
    ]
    (HERE / "shot-list.md").write_text("\n".join(out), encoding="utf-8")
    print("\n  shot list    docs/video/shot-list.md")


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="rebuild assets for one segment id")
    parser.add_argument("--no-tts", action="store_true", help="reuse the narration already rendered")
    parser.add_argument("--no-shoot", action="store_true", help="reuse the frames already rendered")
    args = parser.parse_args(argv[1:])

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} is not on PATH", file=sys.stderr)
            return 2
    if not CONSOLE.exists():
        print("nabd/replay.html is missing — run `python -m nabd.scene --console` first", file=sys.stderr)
        return 2
    BUILD.mkdir(parents=True, exist_ok=True)

    todo = [s for s in SEGMENTS if not args.only or s.id == args.only]
    if not todo:
        print(f"no segment matches {args.only}", file=sys.stderr)
        return 2

    print(f"\n  narration ({len(todo)} segment(s))")
    narrate(todo, skip=args.no_tts)
    if not args.no_shoot:
        print(f"\n  frames")
        shoot(todo)
    if args.only:
        print("\n  assets rebuilt; run without --only to assemble\n")
        return 0
    print(f"\n  timeline")
    assemble(SEGMENTS)
    print(f"\n  {OUT.name}: {OUT.stat().st_size // 1024} KB\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
