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

Pipeline: narration → one mp3 per segment (Chatterbox by default; `--engine edge`
falls back to edge-tts and needs no account) → Playwright/Chromium screenshots at
1920×1080 → ffmpeg concat demuxer, durations quantised to whole frames so picture
and voice never drift.

Narration is resumable. The Chatterbox Space runs on a shared GPU with a daily
allowance that does not cover both cuts in one sitting, so running out is treated
as a pause rather than a failure: finished segments are kept, the rest are named,
and the same command continues when the window resets.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
CONSOLE = ROOT / "nabd" / "replay.html"

FPS = 30
DISSOLVE = 0.5  # every join in the picture, so the map changes rather than jumps
FADE_IN, FADE_OUT = 0.8, 1.6   # a film opens out of black and closes back into it
TAIL_PAD = 0.6  # silence after each narration segment: a cut never clips a word, and
                # the script is written in short sentences that want a beat to land

# Two cuts of the same film. The console frames are shared — the product's
# interface is English, and dubbing a screenshot would be a lie — so a language
# changes the narration and the cards, and nothing else.
LANGS = {
    "en": {
        "voice": "en-US-AndrewNeural",
        "rate": "+10%",
        "cards": "cards.html",
        "out": "Nabd-Demo.mp4",
        "shots": "shot-list.md",
        "title": "Nabd \u2014 demo video shot list",
        "language_id": "en",
        "kokoro_voice": "am_onyx",
        "kokoro_lang": "en-us",
        "kokoro_speed": 1.0,
    },
    # The submission's virtual demo: the same film in under three minutes.
    "short": {
        "voice": "en-US-AndrewNeural",
        "rate": "+10%",
        "cards": "cards.html",
        "out": "Nabd-Demo-3min.mp4",
        "shots": "shot-list-3min.md",
        "title": "Nabd \u2014 three-minute demo, shot list",
        "language_id": "en",
        "kokoro_voice": "am_onyx",
        "kokoro_lang": "en-us",
        # Six percent faster than the long cut: inaudible, and it keeps the
        # film a clear ten seconds inside the three-minute limit.
        "kokoro_speed": 1.06,
    },
    "tr": {
        "voice": "tr-TR-AhmetNeural",
        "rate": "+8%",
        "cards": "cards-tr.html",
        "out": "Nabd-Demo-TR.mp4",
        "shots": "shot-list-tr.md",
        "title": "Nabd \u2014 demo videosu \u00e7ekim listesi (T\u00fcrk\u00e7e)",
        "language_id": "tr",
        # Kokoro has no Turkish voice. Reading Turkish phonemes with an English
        # one gave a narrator who could not say Kahramanmaraş, so the Turkish
        # cut uses edge's own Turkish voice: not as warm as the English one,
        # but it pronounces the language it is speaking.
        "engine": "edge",
        "kokoro_voice": "am_onyx",
        "kokoro_lang": "tr",
        "kokoro_speed": 1.0,
    },
}

# Kokoro (hexgrad, Apache-2.0) as ONNX: 82M parameters, 330 MB, a second to load
# and no account, no quota and no network. The weights are not in the repository
# — they are fetched once into build/tts by `python docs/video/build.py --fetch-tts`
# — because a video build's model is not source.
KOKORO = {
    "model": "kokoro-v1.0.onnx",
    "voices": "voices-v1.0.bin",
    "release": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0",
    #: What the voice actually speaks, used only to catch a truncated render.
    "wps": 2.6,
}


def kokoro_files() -> tuple[Path, Path]:
    home = BUILD / "tts"
    return home / KOKORO["model"], home / KOKORO["voices"]


def fetch_tts() -> None:
    """Download the Kokoro weights once, into the build directory."""
    import urllib.request

    home = BUILD / "tts"
    home.mkdir(parents=True, exist_ok=True)
    for name in (KOKORO["model"], KOKORO["voices"]):
        target = home / name
        if target.exists():
            print(f"  have  {name}  ({target.stat().st_size // 1_000_000} MB)")
            continue
        print(f"  fetch {name} …")
        urllib.request.urlretrieve(f"{KOKORO['release']}/{name}", target)
        print(f"        {target.stat().st_size // 1_000_000} MB")


_KOKORO = None


def _kokoro(text: str, out: Path) -> None:
    """One segment, spoken locally, and checked against the words it was given."""
    global _KOKORO
    import soundfile as sf

    model, voices = kokoro_files()
    if not model.exists():
        raise RuntimeError(
            f"{model} is missing — run `python docs/video/build.py --fetch-tts` once "
            f"(330 MB), or build with `--engine edge`."
        )
    if _KOKORO is None:
        from kokoro_onnx import Kokoro

        _KOKORO = Kokoro(str(model), str(voices))
    samples, rate = _KOKORO.create(
        text, voice=cfg("kokoro_voice"), speed=cfg("kokoro_speed"), lang=cfg("kokoro_lang"),
    )
    wav = out.with_suffix(".wav")
    sf.write(wav, samples, rate)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-b:a", "160k", str(out), "-y"], check=True)
    wav.unlink()
    spoken, expected = duration(out), len(text.split()) / KOKORO["wps"]
    if spoken < expected * 0.6:
        raise RuntimeError(
            f"{spoken:.1f}s for {len(text.split())} words (expected about {expected:.1f}s) — truncated"
        )

# Narration is Chatterbox (Resemble AI, MIT) running on its public Space, because
# nothing that installs locally for free comes close and the alternatives all cost
# something: credits, five gigabytes, or an afternoon in front of a microphone.
#
# One model and one reference clip serve both cuts, so the Turkish and English
# films are narrated by the same voice — a consequence of the multilingual Space
# demanding a reference, not a plan.
#
# The Space runs on ZeroGPU. A free account's daily allowance does not cover
# twenty-eight segments in one sitting, so `narrate` treats running out as an
# ordinary outcome: it writes what it got, says what is left, and exits. Run it
# again when the window resets and it picks up where it stopped.
CHATTERBOX = {
    "space": "https://resembleai-chatterbox-multilingual-tts.hf.space/",
    "reference": "voice-reference.wav",
    "seed": 42,
    # Softer emotion, slower delivery, less variance between words. Lower cfg is
    # what slows Chatterbox down; lower exaggeration is what stops it acting.
    "exaggeration": 0.3,
    "temperature": 0.7,
    "cfg_weight": 0.6,
    "timeout_s": 400,
}

LANG = "en"  # set by main()
ENGINE = "chatterbox"  # set by main(); "edge" is the offline fallback


def cfg(key: str):
    return LANGS[LANG][key]


def outdir() -> Path:
    return BUILD / LANG


def narration(seg: "Segment") -> str:
    return TURKISH[seg.id] if LANG == "tr" else seg.text


def cut() -> list["Segment"]:
    """The segments of the cut being built."""
    return SHORT if LANG == "short" else SEGMENTS

# The console is built for a browser window, not a 16:9 frame. This makes the
# map big enough to read at 1080p and lays the side panels out in two columns
# so a whole pass fits one frame without scrolling.
CONSOLE_CSS = """
  /* The console now fits a viewport on its own, so the film only has to take the
     transport controls out of shot. One tab is open at a time, exactly as an
     operator would see it; `Segment.tab` says which one each segment opens. */
  .controls { visibility: hidden !important; }
"""


@dataclass
class Segment:
    id: str
    text: str
    card: str | None = None
    frames: list[tuple[str, int]] = field(default_factory=list)  # (scene, pass)
    tab: str = "zones"  # which side panel the narration is describing
    min_s: float = 0.0
    steps: int = 1      # a card shot in stages, so it builds under the voice

    @property
    def audio(self) -> Path:
        return outdir() / f"{self.id}.mp3"

    def stills(self) -> list[Path]:
        # Card frames carry text, so they are rendered per language; console
        # frames are the product's own interface and are shared between cuts.
        home = outdir() if self.card else BUILD / "console"
        if self.card:
            if self.steps == 1:
                return [home / f"{self.id}.png"]
            return [home / f"{self.id}-{i:02d}.png" for i in range(self.steps)]
        return [home / f"{self.id}-{i:02d}.png" for i in range(len(self.frames))]


SEGMENTS = [
    Segment(
        "01-title", card="c01-title", steps=2,
        text="Nabd. In Arabic it means pulse, and that is close to what it does, because when a "
             "disaster hits, a whole neighbourhood of the mobile network stops answering in the "
             "same second. Nabd reads that silence, and turns it into a map of where the damage is.",
    ),
    Segment(
        "02-problem", card="c02-problem", steps=3,
        text="On the sixth of February, twenty twenty-three, at seventeen minutes past four in the "
             "morning, the seismometers knew. Within seconds they had the magnitude, the depth and "
             "the epicentre. What they could not say was which street. That answer took hours — and "
             "under the rubble a clock had already started, because after seventy-two hours almost "
             "nobody is pulled out alive. More than fifty-three thousand people died. What held the "
             "rescue back was not machines and not people; it was not knowing where to send them, "
             "and the picture that would have answered that was being assembled from emergency "
             "calls, at the exact moment the network was too overloaded to carry them.",
    ),
    Segment(
        "03-insight", card="c03-insight", steps=3,
        text="But there was something nobody was reading. When the ground moves, the network does "
             "something a disaster cannot hide: a connected block of cells stops answering in the "
             "same second, while the ring around it saturates, because everyone still standing is "
             "calling at once. Nabd reads that shape through standard CAMARA APIs, in two layers — "
             "detection is aggregate and never touches the public, and triage is consented, only "
             "ever inside an area already declared.",
    ),
    Segment(
        "04-quiet", frames=[("quiet", 2), ("quiet", 6), ("quiet", 9)],
        text="This is the command centre, where every square is a cell with a single sentinel device "
             "inside it. On an ordinary morning they all answer, so the agent has nothing to report, "
             "and it does not pretend otherwise.",
    ),
    Segment(
        "05-onset", frames=[("quake", 4), ("quake", 5)],
        text="Nine oh two, and an earthquake. Nine cells go silent in the same second, and the agent "
             "still does not declare, because one signal never declares alone. It marks a candidate, "
             "and waits one more pass.",
    ),
    Segment(
        "06-declare", frames=[("quake", 6)],
        text="Fifty-five seconds after the shaking, it declares nine cells, about four square "
             "kilometres, at high confidence. Two gates have passed, because the block is connected "
             "and this silence is abnormal here, and two corroborations agree, because the onset was "
             "synchronised and all sixteen cells around it are saturated. That ring is everyone who "
             "survived, calling at once. Fifty-five seconds — against the hours it took in twenty "
             "twenty-three.",
    ),
    Segment(
        "07-triage", frames=[("quake", 6), ("quake", 7)], tab="registry",
        text="Only now does the agent touch a personal device. Thirteen people inside that footprint "
             "are on the opt-in registry, and six of them are not answering. The list is ranked by "
             "need, so the first line is not a cell, it is a person: R zero one zero, elderly, in "
             "F five, last seen within thirteen hundred metres. That is something a command centre "
             "can act on. And every line of the evidence records how many personal calls were made, "
             "which on an ordinary morning is zero.",
    ),
    Segment(
        "08-update", frames=[("quake", 14), ("quake", 16)], tab="registry",
        text="The map is not a snapshot either. Four minutes later, two of those six answer again, "
             "and the list corrects itself from six to four, with nobody touching it.",
    ),
    Segment(
        "09-lookalikes", frames=[("noise", 2), ("noise", 6), ("noise", 10)], tab="log",
        text="Anything can be built to fire. But a map that cries wolf is a map nobody moves for, "
             "and the one time it is real, they hesitate. So the work is in what it refuses. One "
             "cell silent while its neighbours are normal is a base station fault. Four silent "
             "together, matching a ticket on the operator's maintenance calendar, is expected work. "
             "Nine saturated while every sentinel answers is a football crowd. Three abstentions, "
             "three written reasons, no alarm.",
    ),
    Segment(
        "10-degraded", frames=[("degraded", 11), ("degraded", 21)], tab="log",
        text="Then the hard one, where four cells on a failing backhaul produce every signal a "
             "disaster produces, and nothing on the calendar explains them. So the agent stops "
             "arguing and measures: these cells were already unreachable in three of the last eleven "
             "passes, so silence here is normal, and normal is not news. And in the same run, a real "
             "earthquake is still declared in the city centre.",
    ),
    Segment(
        "11-real", frames=[("maras", 6), ("maras", 15), ("maras", 23)],
        text="Then we stopped drawing the disaster altogether. The geometry, and the shaking in "
             "every cell, come from the published USGS ShakeMap for the magnitude seven point eight "
             "Pazarcık earthquake, constrained by two hundred and sixty-two seismic stations. Only "
             "the rule that turns shaking into silence is ours. Fifty-five seconds after onset it "
             "declares twenty-one cells, every one of them above the collapse threshold in the "
             "measured field, so it invents no damage. Then it grows to six thousand three hundred "
             "square kilometres as the surviving masts run their batteries flat, with twenty-two "
             "registered people unreachable at the peak, medical-dependent first.",
    ),
    Segment(
        "11b-atlas", frames=[("atlas", 5), ("atlas", 12), ("atlas", 22)],
        text="A detector tested on the one event it was tuned for has not been tested. So we ran it "
             "again over the magnitude six point eight Al Haouz earthquake in Morocco, and changed "
             "nothing: the same thresholds, the same code. An earthquake that size, nineteen "
             "kilometres down, does not flatten a block, so the first verdict is a refusal. It "
             "declares almost four minutes later, at medium confidence, and it says why: the onset "
             "genuinely was staggered, because the footprint arrived as mountain villages drained "
             "their batteries. And Marrakesh, shaken hard enough to lead the news everywhere, "
             "answered throughout, and is never named. A map of what was shaken would have claimed "
             "Marrakesh. A map of what went silent does not. That ShakeMap had three seismic "
             "stations behind it, against two hundred and sixty-two for Kahramanmaraş — where the "
             "instruments are thinnest, the network is still talking.",
    ),
    Segment(
        "12-hood", card="c10-hood", steps=3,
        text="Under the hood the agent is a LangGraph graph, and the privacy claim lives in the "
             "topology rather than in a promise: the node that queries a personal device can only be "
             "reached from a verdict with an active footprint. Detection stays deterministic and "
             "replayable, and the language model writes the duty officer's brief and nothing else.",
    ),
    Segment(
        "13-parity", card="c11-parity", steps=3,
        text="The sandbox cannot stage a disaster, so we separated the two claims: the live platform "
             "proves the integration, the simulator proves the scenario. The risk was the gap "
             "between them, so the gap is what we measure — every scene recorded and replayed "
             "through the same parsing functions the live gateway uses, and the evidence has to "
             "come out identical, line for line. And the last check is no longer a promise: the "
             "contract run happened, eighteen calls out of eighteen answered by the real "
             "platform, and the same agent replays that recording with no credentials at all.",
    ),
    Segment(
        "14-close", card="c12-close", steps=3,
        text="To the network, an earthquake, a flood, a storm and a mass outage are the same thing: "
             "an area going dark. Watching the whole of Türkiye takes seven thousand eight hundred "
             "sentinel SIMs, not eighty-five million people — the bill scales with land area, "
             "not population, and the operator sells it through Open Gateway to the agency that "
             "already carries the duty of care. Kadir's Team, Türkiye, for MENA Ignite twenty "
             "twenty-six. The network already knew where the damage was, the whole time. Nabd is "
             "what makes it say so — in the first minute, while it still matters.",
    ),
]


#: The Turkish cut. Not a translation of the English line by line — the same
#: point, said the way it would be said in Turkish, at a length that fits the
#: same frames.
# The three-minute cut: nine segments, the same argument. Distinct ids, so its
# console frames are shot on their own and never mistaken for the long cut's.
SHORT = [
    Segment(
        "s1-title", card="c01-title", steps=2,
        text="Nabd. In Arabic it means pulse. When a disaster hits, a whole neighbourhood of the "
             "mobile network stops answering in the same second. Nabd reads that silence, and turns "
             "it into a map of where the damage is.",
    ),
    Segment(
        "s2-problem", card="c02-problem", steps=3,
        text="On the sixth of February, twenty twenty-three, the seismometers knew within seconds. "
             "What they could not say was which street, or who was cut off. That took hours, while "
             "a seventy-two hour clock was already running under the rubble. The network already "
             "knew. Nobody was reading it.",
    ),
    Segment(
        "s3-insight", card="c03-insight", steps=3,
        text="A connected block of cells goes silent in the same second, while the ring around it "
             "saturates, because everyone still standing is calling at once. Nabd reads that shape "
             "through three CAMARA APIs on Nokia Network-as-Code, in two layers: detection is "
             "aggregate and never touches the public; triage is consented, and only ever inside a "
             "declared footprint.",
    ),
    Segment(
        "s4-quake", frames=[("quake", 4), ("quake", 6)],
        text="The command centre. Every square is a cell with one sentinel device inside. Nine oh "
             "two: nine cells go silent at once, and the agent does not declare, because one signal "
             "never declares alone. One more pass. Fifty-five seconds after the shaking it declares "
             "nine cells, about four square kilometres, at high confidence: two gates passed, two "
             "corroborations agree, and the saturated ring is everyone who survived, calling at once.",
    ),
    Segment(
        "s5-triage", frames=[("quake", 7), ("quake", 16)], tab="registry",
        text="Only now does it touch a personal device. Thirteen people inside are on the opt-in "
             "registry, and six are not answering: ranked by need, with a last-seen position. Four "
             "minutes later two of them answer again, and the list corrects itself, six to four. "
             "Every line of the evidence counts the personal calls it made.",
    ),
    Segment(
        "s6-refusals", frames=[("noise", 10), ("degraded", 21)], tab="log",
        text="The work is in what it refuses. One silent cell is a base-station fault. Four silent "
             "inside a maintenance ticket is expected work. Nine saturated while every sentinel "
             "answers is a football crowd. A block where silence is normal is measured against its "
             "own history and refused, while a real impact in the same run is still declared. Every "
             "refusal is written down.",
    ),
    Segment(
        "s7-real", frames=[("maras", 6), ("maras", 23), ("atlas", 22)],
        text="Then we stopped drawing the disaster. The shaking in every cell comes from the USGS "
             "ShakeMap of the magnitude seven point eight Pazarc\u0131k earthquake; only the rule that "
             "turns shaking into silence is ours. Fifty-five seconds after onset it declares, and the "
             "footprint grows as the network keeps dying. Then Al Haouz, in Morocco, magnitude six "
             "point eight, on the same thresholds untouched: the first verdict is a refusal, it "
             "declares later at medium confidence, and it says why. Marrakesh, shaken, is never named.",
    ),
    Segment(
        "s8-live", card="c11-parity", steps=3,
        text="The sandbox cannot stage a disaster, so the two claims are separated. The live "
             "platform proves the integration: eighteen of eighteen calls answered on "
             "Network-as-Code, the raw exchanges on file. The simulator proves the scenario, and a "
             "replay of every recorded response through the live parsers reproduces the evidence "
             "line for line.",
    ),
    Segment(
        "s9-close", card="c12-close", steps=3,
        text="Under the hood, a LangGraph graph over a deterministic core, where the node that "
             "queries a personal device can only be reached from a verdict with an active footprint. "
             "Watching the whole of T\u00fcrkiye takes seven thousand eight hundred sentinel SIMs, not "
             "eighty-five million people, sold through Open Gateway to the agency that carries the "
             "duty of care. Nabd. Kadir's Team, T\u00fcrkiye.",
    ),
]

TURKISH = {
    "01-title":
        "Nabd. Arapçada nabız demek, ki yaptığı işe de yakın; çünkü bir afet vurduğunda mobil "
        "ağın koca bir mahallesi aynı saniyede cevap vermeyi kesiyor. Nabd bu sessizliği okuyor "
        "ve onu, hasarın nerede olduğunun haritasına çeviriyor.",
    "02-problem":
        "Altı Şubat iki bin yirmi üçte, sabaha karşı dördü on yedi geçe, sismometreler biliyordu. "
        "Saniyeler içinde büyüklüğü, derinliği ve merkez üssünü çıkardılar. Söyleyemedikleri şey "
        "hangi sokak olduğuydu. O cevap saatler aldı — ve enkazın altında bir saat çoktan işlemeye "
        "başlamıştı, çünkü yetmiş iki saatten sonra neredeyse kimse canlı çıkarılamıyor. Elli üç "
        "binden fazla insan hayatını kaybetti. Kurtarmayı geciktiren makine ya da insan değildi; "
        "nereye gönderileceğinin bilinmemesiydi. O soruyu cevaplayacak tablo ise acil çağrılardan "
        "toplanıyordu, tam da ağın o çağrıları taşıyamayacak kadar tıkalı olduğu anda.",
    "03-insight":
        "Ama kimsenin okumadığı bir şey vardı. Yer sarsıldığında ağ, bir afetin saklayamayacağı "
        "bir şey yapar: bitişik bir hücre bloğu aynı saniyede susar, etrafındaki halka ise doyar, "
        "çünkü ayakta kalan herkes aynı anda arıyordur. Nabd bu deseni standart CAMARA API'leri "
        "üzerinden iki katmanda okuyor: tespit toplu düzeydedir ve halka asla dokunmaz; triyaj "
        "ise rızaya dayalıdır ve yalnızca önceden ilan edilmiş bir alanın içinde çalışır.",
    "04-quiet":
        "Karşınızdaki komuta merkezi; her kare, içinde tek bir nöbetçi cihaz bulunan bir hücre. "
        "Sıradan bir sabahta hepsi cevap verir, dolayısıyla ajanın bildirecek bir şeyi olmaz ve "
        "varmış gibi de yapmaz.",
    "05-onset":
        "Saat dokuz sıfır iki ve bir deprem. Dokuz hücre aynı saniyede susuyor, ama ajan yine de "
        "ilan etmiyor; çünkü tek bir sinyal asla tek başına ilan ettirmez. Aday olarak "
        "işaretliyor ve bir geçiş daha bekliyor.",
    "06-declare":
        "Sarsıntıdan elli beş saniye sonra ilan ediyor: dokuz hücre, yaklaşık dört kilometrekare, "
        "yüksek güvenle. İki kapı geçildi, çünkü blok bitişik ve bu sessizlik burada anormal; iki "
        "destekleyici kanıt da hemfikir, çünkü başlangıç eşzamanlıydı ve çevresindeki on altı "
        "hücrenin on altısı doygun. O halka, ayakta kalan herkesin aynı anda araması. Elli beş "
        "saniye — iki bin yirmi üçte saatler süren şeyin karşısında.",
    "07-triage":
        "Ajan kişisel bir cihaza ancak şimdi dokunuyor. O etki alanının içinde on üç kişi gönüllü "
        "kayıt listesinde ve altısına ulaşılamıyor. Liste ihtiyaca göre sıralı, dolayısıyla ilk "
        "satır bir hücre değil, bir insan: R sıfır bir sıfır, yaşlı, F beşte, en son bin üç yüz "
        "metre yarıçapı içinde görülmüş. Bir komuta merkezinin üzerine hareket edebileceği şey "
        "budur. Kanıt dosyasının her satırı da kaç kişisel çağrı yapıldığını yazıyor; sıradan bir "
        "sabahta bu sayı sıfır.",
    "08-update":
        "Harita bir anlık görüntü de değil. Dört dakika sonra o altı kişiden ikisi yeniden cevap "
        "veriyor ve liste, kimse hiçbir şeye dokunmadan altıdan dörde iniyor.",
    "09-lookalikes":
        "Ateş eden bir şeyi herkes yapabilir. Ama kurt masalı anlatan bir harita, kimsenin "
        "kalkmadığı bir haritadır; gerçek olduğu tek seferde de tereddüt edilir. Asıl iş, neyi "
        "reddettiğindedir. Komşuları normalken "
        "susan tek bir hücre, baz istasyonu arızasıdır. Birlikte susan ve operatörün bakım "
        "takvimindeki bir kayıtla eşleşen dört hücre, beklenen bir iştir. Her nöbetçi cevap "
        "verirken doyan dokuz hücre ise bir stadyumdur. Üç çekimser karar, üç yazılı gerekçe, "
        "sıfır alarm.",
    "10-degraded":
        "Sonra zor olanı. Arızalı bir aktarım hattındaki dört hücre, bir afetin ürettiği her "
        "sinyali üretiyor ve hiçbir takvim bunu açıklamıyor. Ajan da tartışmayı bırakıp ölçüyor: "
        "bu hücreler son on bir geçişin üçünde zaten erişilemezdi, yani buradaki sessizlik "
        "normaldir ve normal olan haber değildir. Üstelik aynı koşuda, şehir merkezindeki gerçek "
        "bir deprem yine ilan ediliyor.",
    "11-real":
        "Sonra afeti çizmeyi tamamen bıraktık. Buradaki coğrafya ve her hücredeki sarsıntı, yedi "
        "virgül sekiz büyüklüğündeki Pazarcık depreminin yayımlanmış USGS ShakeMap verisinden "
        "geliyor; iki yüz altmış iki sismik istasyonla kısıtlanmış bir alan. Bize ait olan tek "
        "şey, sarsıntıyı sessizliğe çeviren kural. Sarsıntıdan elli beş saniye sonra yirmi bir "
        "hücre ilan ediyor ve hepsi, ölçülen alanda çökme eşiğinin üstünde; yani hasar "
        "uydurmuyor. Sonra ayakta kalan direkler akülerini tüketirken etki alanı altı bin üç yüz "
        "kilometrekareye büyüyor; zirvede yirmi iki kayıtlı kişiye ulaşılamıyor, önce tıbbi "
        "bağımlılar.",
    "11b-atlas":
        "Ama yalnızca kendisine göre ayarlandığı olayda sınanan bir dedektör, gerçekte "
        "sınanmamıştır. Bu yüzden aynı ajanı bir kez de Fas'taki altı virgül sekiz büyüklüğündeki "
        "Al Haouz depremi üzerinde koşturduk ve hiçbir şeyi değiştirmedik: aynı eşikler, aynı "
        "kod. Bu büyüklükte ve on dokuz kilometre derinlikte bir deprem koca bir bloğu birden "
        "yıkmaz; dolayısıyla buradaki ilk karar bir ret. Yaklaşık dört dakika sonra, orta güvenle "
        "ilan ediyor ve nedenini de söylüyor: başlangıç gerçekten kademeliydi, çünkü etki alanı "
        "dağ köyleri akülerini tükettikçe oluştu. Marrakeş ise, dünyanın her yerinde haberlere "
        "çıkacak kadar sarsılmasına rağmen baştan sona cevap verdi ve hiç adlandırılmadı. Neyin "
        "sarsıldığını gösteren bir harita Marrakeş'i sahiplenirdi; neyin sustuğunu gösteren bir "
        "harita sahiplenmiyor. O ShakeMap'in arkasında üç sismik istasyon vardı, Kahramanmaraş'ta "
        "iki yüz altmış iki. Cihazların en seyrek olduğu yerde, konuşmaya devam eden şey ağdır.",
    "12-hood":
        "Kaputun altında ajan bir LangGraph grafiği ve gizlilik iddiası bir sözde değil, "
        "topolojide duruyor; çünkü kişisel cihaz sorgulayan düğüme yalnızca aktif etki alanı olan "
        "bir karardan ulaşılabiliyor. Tespit deterministik ve tekrar oynatılabilir kalırken, dil "
        "modeli yalnızca nöbetçi subayın brifingini yazıyor.",
    "13-parity":
        "Kum havuzu bir afeti sahneleyemez, o yüzden iki iddiayı ayırdık: canlı platform "
        "entegrasyonu kanıtlıyor, simülatör ise senaryoyu. Risk, bu iki yol arasındaki boşluktu; "
        "ölçtüğümüz de tam olarak o boşluk. Her sahne kaydediliyor ve canlı ağ geçidinin "
        "kullandığı aynı ayrıştırma fonksiyonlarından geri oynatılıyor, kanıtın da satır satır "
        "aynı çıkması gerekiyor. Son kontrol de artık bir söz değil: sözleşme koşusu yapıldı, "
        "on sekiz çağrının on sekizi gerçek platform tarafından cevaplandı ve aynı ajan o kaydı "
        "hiçbir kimlik bilgisi olmadan geri oynatıyor.",
    "14-close":
        "Ağ açısından deprem de sel de fırtına da kitlesel kesinti de aynı şeydir: kararan bir "
        "alan. Türkiye'nin tamamını izlemek yedi bin sekiz yüz nöbetçi SIM istiyor, seksen beş "
        "milyon abone değil; yani fatura nüfusa göre değil, yüzölçümüne göre büyüyor ve operatör "
        "bunu Open Gateway üzerinden, sorumluluğu zaten taşıyan kuruma satıyor. Kadir'in "
        "Ekibi'nden, Türkiye'den, MENA Ignite iki bin yirmi altı için. Ağ, hasarın nerede olduğunu "
        "en başından beri biliyordu. Nabd, ona bunu söyleten şey — ilk dakikada, hâlâ anlamı "
        "varken.",
}


# ---------------------------------------------------------------- narration


class QuotaSpent(RuntimeError):
    """The Space's shared GPU allowance ran out. Not a failure — a pause."""


async def _edge(text: str, out: Path) -> None:
    """One segment through edge-tts — and checked, like the other two engines.

    It occasionally returns a second of audio for a whole paragraph and reports
    no error at all, which is how a title card once went out with a heartbeat
    of narration under it. Anything far short of the words it was given is a
    failed render, and a failed render raises.
    """
    import edge_tts

    for attempt in range(3):
        await edge_tts.Communicate(text, cfg("voice"), rate=cfg("rate")).save(str(out))
        spoken, expected = duration(out), len(text.split()) / 3.2
        if spoken >= expected * 0.7:
            return
        print(f"        {spoken:.1f}s for {len(text.split())} words — retrying")
    raise RuntimeError(
        f"edge-tts kept returning {duration(out):.1f}s for {len(text.split())} words "
        f"(expected about {len(text.split()) / 3.2:.1f}s)"
    )


#: The Space returns about fifteen seconds of speech and truncates the rest
#: without a word, so a segment is spoken in pieces no longer than this.
CHUNK_WORDS = 40
#: What the voice actually speaks, measured over the pieces that came back
#: whole. Used to catch a truncation rather than to schedule anything.
CHATTERBOX_WPS = 3.5


def _pieces(text: str, max_words: int = CHUNK_WORDS) -> list[str]:
    """Split a segment where a reader would breathe, into speakable lengths."""
    import re

    def split(unit: str, seps: list[str]) -> list[str]:
        if len(unit.split()) <= max_words or not seps:
            return [unit]
        parts, sep = [], seps[0]
        buf = ""
        for bit in unit.split(sep):
            bit = bit.strip()
            if not bit:
                continue
            candidate = f"{buf}{sep}{bit}" if buf else bit
            if buf and len(candidate.split()) > max_words:
                parts.append(buf)
                buf = bit
            else:
                buf = candidate
        if buf:
            parts.append(buf)
        return [p for part in parts for p in split(part, seps[1:])]

    sentences = [x.strip() for x in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text) if x.strip()]
    out: list[str] = []
    for sentence in sentences:
        # Long sentences break at the marks that already carry a pause.
        for piece in split(sentence, [" \u2014 ", "; ", ", "]):
            piece = piece.strip()
            if not piece:
                continue
            if out and len((out[-1] + " " + piece).split()) <= max_words:
                out[-1] = out[-1] + " " + piece
            else:
                out.append(piece)
    return out or [text]


def _speak(client, handle_file, text: str, out: Path) -> None:
    """One piece, spoken and written as mp3 — and checked for truncation."""
    try:
        wav = client.predict(
            text_input=text,
            language_id=cfg("language_id"),
            audio_prompt_path_input=handle_file(str(HERE / CHATTERBOX["reference"])),
            exaggeration_input=CHATTERBOX["exaggeration"],
            temperature_input=CHATTERBOX["temperature"],
            seed_num_input=CHATTERBOX["seed"],
            cfgw_input=CHATTERBOX["cfg_weight"],
            api_name="/generate_tts_audio",
        )
    except Exception as exc:
        if "ZeroGPU" in str(exc) or "quota" in str(exc).lower():
            raise QuotaSpent(str(exc)) from exc
        raise
    subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-b:a", "160k", str(out), "-y"], check=True)
    spoken, expected = duration(out), len(text.split()) / CHATTERBOX_WPS
    if spoken < expected * 0.78:
        raise RuntimeError(
            f"the Space returned {spoken:.1f}s for {len(text.split())} words "
            f"(expected about {expected:.1f}s) — it truncated the text"
        )


def _chatterbox(text: str, out: Path) -> None:
    """One segment through the Chatterbox Space, converted to mp3 like the rest.

    Long segments are spoken in pieces and joined, because the Space cuts the
    text off at about fifteen seconds without saying so.
    """
    from gradio_client import Client, handle_file

    token_file = Path(os.path.expanduser("~/.cache/huggingface/token"))
    if not token_file.exists():
        raise RuntimeError(
            "No Hugging Face token at ~/.cache/huggingface/token. A free account's "
            "read token lifts the Space's anonymous GPU allowance; without one, "
            "re-run with --engine edge."
        )
    client = Client(
        CHATTERBOX["space"], token=token_file.read_text().strip(), verbose=False,
        httpx_kwargs={"timeout": CHATTERBOX["timeout_s"]},
    )
    pieces = _pieces(text)
    if len(pieces) == 1:
        _speak(client, handle_file, pieces[0], out)
        return
    # Pieces are kept beside the segment, so a run that runs out of GPU part of
    # the way through a segment resumes at the piece it stopped on.
    parts = []
    for i, piece in enumerate(pieces):
        part = out.with_name(f"{out.stem}.part{i:02d}.mp3")
        if not part.exists():
            print(f"        piece {i + 1}/{len(pieces)}  {len(piece.split())}w")
            _speak(client, handle_file, piece, part)
        parts.append(part)
    listing = out.with_suffix(".parts.txt")
    listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts) + "\n", encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-b:a", "160k", str(out), "-y"], check=True,
    )
    listing.unlink()
    for part in parts:
        part.unlink()


def narrate(segments: list[Segment], skip: bool) -> None:
    todo = [s for s in segments if not (skip and s.audio.exists())]
    # Only Chatterbox is precious about re-rendering: its allowance is finite.
    todo = [s for s in todo if not s.audio.exists()] if ENGINE == "chatterbox" else todo
    done = 0
    for seg in todo:
        try:
            if ENGINE == "edge":
                print(f"  tts   {seg.id}")
                asyncio.run(_edge(narration(seg), seg.audio))
            elif ENGINE == "kokoro":
                print(f"  say   {seg.id}")
                _kokoro(narration(seg), seg.audio)
            else:
                print(f"  say   {seg.id}")
                _chatterbox(narration(seg), seg.audio)
            done += 1
        except QuotaSpent:
            left = [s.id for s in todo[todo.index(seg):]]
            print(f"\n  GPU allowance spent after {done} segment(s).")
            print(f"  {len(left)} still to render: {', '.join(left)}")
            print("  Re-run the same command when the window resets; finished segments are kept.\n")
            raise SystemExit(3)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ------------------------------------------------------------------ frames


#: Reveal the card's blocks up to `step` of `steps`. A block that is itself a
#: row — panels, statistics, checks — hands its children over as the units, so
#: a three-column card arrives a column at a time. Hidden units keep their
#: space, so nothing on the card ever moves between steps.
REVEAL = """({card, step, steps}) => {
  const el = document.getElementById(card);
  const rows = ['cols', 'big', 'checks', 'flow', 'chips', 'next', 'three'];
  const units = [];
  for (const child of el.children) {
    const isRow = rows.some(c => child.classList.contains(c));
    if (isRow && child.children.length > 1) units.push(...child.children);
    else units.push(child);
  }
  const shown = steps <= 1 ? units.length : Math.ceil(units.length * step / steps);
  units.forEach((u, i) => { u.style.opacity = i < shown ? '' : '0'; });
}"""


def shoot(segments: list[Segment]) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        shots = [s for s in segments if not s.card and not all(p.exists() for p in s.stills())]
        if shots:
            page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
            page.goto(CONSOLE.as_uri())
            page.wait_for_timeout(600)
            page.add_style_tag(content=CONSOLE_CSS)
            for seg in shots:
                for i, (scene, index) in enumerate(seg.frames):
                    print(f"  frame {seg.id}-{i:02d}  #{scene}/{index}  [{seg.tab}]")
                    page.evaluate(f"location.hash = '#{scene}/{index}'")
                    # The cells ease into their colour over 550 ms; shoot after it lands.
                    page.wait_for_timeout(750)
                    page.evaluate(
                        "t => document.querySelector(`#tabs button[data-pane=${t}]`)?.click()", seg.tab
                    )
                    page.wait_for_timeout(180)
                    page.screenshot(path=str(seg.stills()[i]), clip={"x": 0, "y": 0, "width": 1600, "height": 900})

        # Cards are authored at 1920x1080 and shot at scale 1; the console is a
        # 1600x900 layout scaled 1.2 to fill the same frame. Cards come last
        # because each sits on a console frame as its background.
        cards = [s for s in segments if s.card]
        if cards:
            page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            page.goto((HERE / cfg("cards")).as_uri())
            page.wait_for_timeout(900)
            for seg in cards:
                print(f"  card  {seg.id}" + (f"  ({seg.steps} steps)" if seg.steps > 1 else ""))
                for i, still in enumerate(seg.stills()):
                    page.evaluate(REVEAL, {"card": seg.card, "step": i + 1, "steps": seg.steps})
                    page.locator(f"#{seg.card}").screenshot(path=str(still))
                page.evaluate(REVEAL, {"card": seg.card, "step": 1, "steps": 1})
            page.close()
        browser.close()


# ---------------------------------------------------------------- assembly


def quantise(seconds: float) -> float:
    return round(seconds * FPS) / FPS


def assemble(segments: list[Segment]) -> None:
    out_file = ROOT / cfg("out")
    silence = BUILD / "pad.mp3"
    if not silence.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", str(TAIL_PAD), "-q:a", "9", str(silence), "-y"], check=True,
        )

    shots: list[tuple[Path, float]] = []      # (still, how long it is on screen)
    audio_parts: list[Path] = []
    timeline: list[tuple[str, float, float, list[str]]] = []
    total = 0.0
    for seg in segments:
        span = quantise(max(seg.min_s, duration(seg.audio) + TAIL_PAD))
        stills = seg.stills()
        each = quantise(span / len(stills))
        for i, still in enumerate(stills):
            hold = each if i < len(stills) - 1 else quantise(span - each * (len(stills) - 1))
            shots.append((still, hold))
        audio_parts += [seg.audio, silence]
        shown = [seg.card] if seg.card else [f"{scene} - pass {i}" for scene, i in seg.frames]
        timeline.append((seg.id, total, span, shown))
        total += span
        print(f"  {seg.id:<14} {span:6.2f}s  {len(stills)} frame(s)")

    alist = outdir() / "audio.txt"
    alist.write_text("\n".join(f"file '{p.as_posix()}'" for p in audio_parts) + "\n", encoding="utf-8")
    voice = outdir() / "voice.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alist),
         "-c:a", "aac", "-b:a", "160k", str(voice), "-y"], check=True,
    )

    # The picture is cut to the narration by -shortest, so the closing fade is
    # placed against the voice's own length rather than the sum of the spans.
    film = duration(voice)
    write_timeline(timeline, total)
    print(f"\n  dissolving {len(shots)} shots over {film:.1f}s → {out_file.name}")

    # Each shot is cut a dissolve longer than it is on screen, because the chain
    # gives that length back at the join. The last one is not, so the film ends
    # exactly where the narration does.
    cmd: list[str] = ["ffmpeg", "-v", "error"]
    for i, (still, hold) in enumerate(shots):
        clip = hold + (DISSOLVE if i < len(shots) - 1 else 0.0)
        cmd += ["-loop", "1", "-t", f"{clip:.4f}", "-i", str(still)]
    cmd += ["-i", str(voice)]

    graph, offset = [], 0.0
    for i in range(len(shots)):
        graph.append(f"[{i}:v]format=yuv420p,fps={FPS},setsar=1[c{i}]")
    prev = "c0"
    for i in range(1, len(shots)):
        offset += shots[i - 1][1]
        label = f"x{i}" if i < len(shots) - 1 else "vout"
        graph.append(f"[{prev}][c{i}]xfade=transition=fade:duration={DISSOLVE}:offset={offset:.4f}[{label}]")
        prev = label
    if len(shots) == 1:
        graph.append("[c0]null[vout]")
    # Out of black, and back into it.
    graph[-1] = graph[-1].replace("[vout]", "[vfade]")
    graph.append(f"[vfade]fade=t=in:st=0:d={FADE_IN},"
                 f"fade=t=out:st={film - FADE_OUT:.3f}:d={FADE_OUT}[vout]")

    script = outdir() / "dissolve.txt"
    script.write_text(";\n".join(graph) + "\n", encoding="utf-8")
    cmd += ["-filter_complex_script", str(script),
            "-map", "[vout]", "-map", f"{len(shots)}:a",
            "-af", f"afade=t=out:st={film - FADE_OUT:.3f}:d={FADE_OUT}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "20",
            "-preset", "medium", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_file), "-y"]
    subprocess.run(cmd, check=True)


def write_timeline(rows: list[tuple[str, float, float, list[str]]], total: float) -> None:
    """The shot list, regenerated from the build so it cannot drift from the film."""
    by_id = {s.id: s for s in cut()}
    out = [
        f"# {cfg('title')}",
        "",
        f"*Generated by `python docs/video/build.py --lang {LANG}`. {cfg('out')} · 1920×1080 · "
        f"{int(total // 60)}:{int(total % 60):02d} · {LANG} narration "
        f"({cfg('kokoro_voice')} via Kokoro).*",
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
        text = narration(by_id[seg_id]).replace("|", "/")
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
    (HERE / cfg("shots")).write_text("\n".join(out), encoding="utf-8")
    print(f"\n  shot list    docs/video/{cfg('shots')}")


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=sorted(LANGS), default="en", help="which cut to build")
    parser.add_argument("--engine", choices=("kokoro", "chatterbox", "edge"), default="kokoro",
                        help="narration engine; kokoro runs locally with no account and no quota")
    parser.add_argument("--fetch-tts", action="store_true",
                        help="download the Kokoro weights into docs/video/build/tts (330 MB, once)")
    parser.add_argument("--only", help="rebuild assets for one segment id")
    parser.add_argument("--no-tts", action="store_true", help="reuse the narration already rendered")
    parser.add_argument("--no-shoot", action="store_true", help="reuse the frames already rendered")
    args = parser.parse_args(argv[1:])

    global LANG, ENGINE
    LANG = args.lang
    # A cut may pin its own engine — the Turkish one does, because Kokoro has no
    # Turkish voice. An explicit --engine still wins.
    ENGINE = args.engine if "--engine" in argv else LANGS[LANG].get("engine", args.engine)

    if args.fetch_tts:
        fetch_tts()
        return 0

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} is not on PATH", file=sys.stderr)
            return 2
    if not CONSOLE.exists():
        print("nabd/replay.html is missing — run `python -m nabd.scene --console` first", file=sys.stderr)
        return 2
    BUILD.mkdir(parents=True, exist_ok=True)
    outdir().mkdir(parents=True, exist_ok=True)
    (BUILD / "console").mkdir(parents=True, exist_ok=True)

    todo = [s for s in cut() if not args.only or s.id == args.only]
    if not todo:
        print(f"no segment matches {args.only}", file=sys.stderr)
        return 2

    print(f"\n  {LANG} cut \u2014 narration via {ENGINE} ({len(todo)} segment(s))")
    narrate(todo, skip=args.no_tts)
    if not args.no_shoot:
        print("\n  frames")
        shoot(todo)
    if args.only:
        print("\n  assets rebuilt; run without --only to assemble\n")
        return 0
    print("\n  timeline")
    assemble(cut())
    out_file = ROOT / cfg("out")
    print(f"\n  {out_file.name}: {out_file.stat().st_size // 1024} KB\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
