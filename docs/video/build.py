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
import json
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
    },
    "tr": {
        "voice": "tr-TR-AhmetNeural",
        "rate": "+8%",
        "cards": "cards-tr.html",
        "out": "Nabd-Demo-TR.mp4",
        "shots": "shot-list-tr.md",
        "title": "Nabd \u2014 demo videosu \u00e7ekim listesi (T\u00fcrk\u00e7e)",
        "language_id": "tr",
    },
}

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
    return seg.text if LANG == "en" else TURKISH[seg.id]

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
        return outdir() / f"{self.id}.mp3"

    def stills(self) -> list[Path]:
        # Card frames carry text, so they are rendered per language; console
        # frames are the product's own interface and are shared between cuts.
        home = outdir() if self.card else BUILD / "console"
        if self.card:
            return [home / f"{self.id}.png"]
        return [home / f"{self.id}-{i:02d}.png" for i in range(len(self.frames))]


SEGMENTS = [
    Segment(
        "01-title", card="c01-title",
        text="Nabd. Read where the network goes silent. It's an AI agent that maps where a "
             "disaster hit, built on Nokia Network-as-Code and LangGraph.",
    ),
    Segment(
        "02-problem", card="c02-problem",
        text="A seismometer will tell you within seconds that an earthquake happened, but that "
             "isn't the question that costs lives. The question is which district to reach first "
             "and who has been cut off, and that answer takes hours to arrive. In Kahramanmaraş, "
             "in twenty twenty-three, more than fifty-three thousand people died. Nabd is not "
             "early warning; it is the impact map in the first minute.",
    ),
    Segment(
        "03-insight", card="c03-insight",
        text="Coordinated silence is a sensor, and Nabd reads it in two layers. The first is "
             "aggregate: a grid of sentinel devices, one per cell, municipal or operator SIMs "
             "rather than anyone's phone, read every thirty seconds. The second is consented, "
             "and it only ever looks at people who asked to be found, inside an area the agent "
             "has already declared.",
    ),
    Segment(
        "04-quiet", frames=[("quiet", 2), ("quiet", 6), ("quiet", 9)],
        text="This is the command centre, where every square is a cell with a single sentinel in "
             "it. On an ordinary morning they all answer, so the agent has nothing to report and "
             "doesn't pretend otherwise.",
    ),
    Segment(
        "05-onset", frames=[("quake", 4), ("quake", 5)],
        text="Nine oh two, and an earthquake. Nobody knows yet which neighbourhoods were hit, and "
             "nine cells go silent at once, but instead of declaring, the agent marks a candidate "
             "and waits one more pass, because one signal never declares alone.",
    ),
    Segment(
        "06-declare", frames=[("quake", 6)],
        text="Fifty-five seconds after the shaking it declares: nine cells, about four square "
             "kilometres, at high confidence. Two gates have passed, since the block is contiguous "
             "and this silence is abnormal here, and two corroborations back it up, because the "
             "onset was synchronised and the ring around it is hot, with sixteen of sixteen "
             "neighbouring cells saturated as everyone calls at the same moment.",
    ),
    Segment(
        "07-triage", frames=[("quake", 6), ("quake", 7)],
        text="Only now does the agent touch a personal device. Thirteen registered people live "
             "inside the footprint and six of them are unreachable, ranked by need, each with a "
             "last-seen position. And every pass of the evidence records whether that personal "
             "path was open and how many calls it made, which on an ordinary morning is zero, on "
             "every single line.",
    ),
    Segment(
        "08-update", frames=[("quake", 14), ("quake", 16)],
        text="The picture keeps moving. Four minutes later two people answer again, and the list "
             "drops from six to four without anyone touching it.",
    ),
    Segment(
        "09-lookalikes", frames=[("noise", 2), ("noise", 6), ("noise", 10)],
        text="A detector is only useful if it stays quiet on the things that merely look like "
             "disasters. When one cell goes silent while its neighbours stay normal, that is a "
             "base station fault. When four go silent together but match a maintenance ticket on "
             "the operator's calendar, that is expected. And when nine saturate while every "
             "sentinel still answers, that is a stadium. Three abstentions, three written reasons, "
             "and no false alarm.",
    ),
    Segment(
        "10-degraded", frames=[("degraded", 11), ("degraded", 21)],
        text="Then the hard one. Four cells on a failing backhaul produce every signal a disaster "
             "has, and nothing on the calendar explains them, so the agent measures them instead: "
             "these cells were already unreachable in three of the last eleven passes, which means "
             "silence here is normal, and normal isn't news. And in the same run, a real earthquake "
             "in the city centre is still declared, so the refusal is measured rather than blind.",
    ),
    Segment(
        "11-real", frames=[("maras", 6), ("maras", 15), ("maras", 23)],
        text="Then we stopped drawing the disaster altogether. The geometry here, and the shaking "
             "in every cell, come from the USGS ShakeMap for the magnitude seven point eight "
             "Pazarcık earthquake of the sixth of February, twenty twenty-three, constrained by "
             "two hundred and sixty-two seismic stations. Fifty-five seconds after onset it "
             "declares twenty-one contiguous cells, twenty-one hundred square kilometres, and "
             "every cell it names is one the measured shaking puts above the collapse threshold, "
             "so it invents no damage. Two more, an isolated pocket below the size floor, it "
             "deliberately leaves unclaimed. Then the footprint grows to six thousand three "
             "hundred square kilometres as the surviving masts lose power and drain their "
             "batteries, which is exactly what the field reports describe.",
    ),
    Segment(
        "12-hood", card="c10-hood",
        text="Under the hood the agent is a LangGraph graph, and the conditional edge is the "
             "privacy claim written into code, because the node that queries a personal device can "
             "only be reached from a verdict with an active footprint. Detection stays "
             "deterministic and replayable, while the language model writes the duty officer's "
             "brief and nothing else. The plain loop and the LangGraph runner produce "
             "byte-identical evidence, under eighty-three tests.",
    ),
    Segment(
        "13-parity", card="c11-parity",
        text="The sandbox can't stage a disaster, so we separated the two claims: the live "
             "platform proves the integration, and the simulator proves the scenario. The risk was "
             "never the simulator itself, it was a suspected gap between the two paths, so that "
             "gap is what we measure. Every scene is recorded and replayed through the same three "
             "parsing functions the live gateway uses, and the evidence has to come out identical, "
             "line for line.",
    ),
    Segment(
        "14-close", card="c12-close",
        text="Nabd doesn't care which disaster it is, because to the network an earthquake, a "
             "flood, a storm and a mass outage are all the same thing: an area going dark. The "
             "buyers are civil-defence agencies and municipalities, reached through the operator's "
             "Open Gateway. The network already knows, and Nabd just makes it say so, in the first "
             "minute. By Kadir's Team, for MENA Ignite twenty twenty-six.",
    ),
]


#: The Turkish cut. Not a translation of the English line by line — the same
#: point, said the way it would be said in Turkish, at a length that fits the
#: same frames.
TURKISH = {
    "01-title":
        "Nabd. Ağın sustuğu yeri okuyun. Afetin nereye vurduğunu haritalayan bir yapay zekâ "
        "ajanı; Nokia Network-as-Code ve LangGraph üzerine kurulu.",
    "02-problem":
        "Bir sismometre depremin olduğunu saniyeler içinde söyler, ama hayat pahasına olan soru "
        "bu değildir: önce hangi mahalleye gidilecek ve kim dışarıda kaldı. O cevap saatler sonra "
        "gelir. Kahramanmaraş'ta, iki bin yirmi üçte, elli üç binden fazla insan hayatını "
        "kaybetti. Nabd bir erken uyarı sistemi değil; ilk dakikada çıkan etki haritası.",
    "03-insight":
        "Eşzamanlı sessizlik bir sensördür ve Nabd bunu iki katmanda okur. Birincisi toplu "
        "düzeydedir: hücre başına bir nöbetçi cihaz, yani halkın telefonu değil belediyenin ya da "
        "operatörün SIM'i, otuz saniyede bir okunur. İkincisi rızaya dayalıdır ve yalnızca "
        "bulunmak isteyen insanlara, üstelik yalnızca ajanın önceden ilan ettiği bir alanın "
        "içinde bakar.",
    "04-quiet":
        "Karşınızdaki komuta merkezi; her kare, içinde tek bir nöbetçi bulunan bir hücre. Sıradan "
        "bir sabahta hepsi cevap verir, dolayısıyla ajanın bildirecek bir şeyi olmaz ve varmış "
        "gibi de yapmaz.",
    "05-onset":
        "Saat dokuz sıfır iki ve bir deprem. Hangi mahallelerin vurulduğunu henüz kimse bilmiyor, "
        "dokuz hücre aynı anda susuyor, ama ajan hemen ilan etmek yerine bunu aday olarak "
        "işaretliyor ve bir geçiş daha bekliyor, çünkü tek bir sinyal asla tek başına ilan "
        "ettirmez.",
    "06-declare":
        "Sarsıntıdan elli beş saniye sonra ilan ediyor: dokuz hücre, yaklaşık dört kilometrekare, "
        "yüksek güvenle. İki kapı geçilmiş durumda, çünkü blok bitişik ve bu sessizlik burada "
        "anormal; ayrıca iki destekleyici kanıt var, zira başlangıç eşzamanlıydı ve etrafındaki "
        "halka sıcak, yani komşu on altı hücrenin on altısı doygun, çünkü herkes aynı anda "
        "arıyor.",
    "07-triage":
        "Ajan kişisel bir cihaza ancak şimdi dokunuyor. Etki alanının içinde on üç kayıtlı kişi "
        "yaşıyor ve bunların altısına ulaşılamıyor; ihtiyaca göre sıralanmış, her biri son "
        "görüldüğü konumla birlikte. Kanıt dosyasının her geçişi de o kişisel yolun açık olup "
        "olmadığını ve kaç çağrı yapıldığını kaydediyor, ki sıradan bir sabahta bu sayı her "
        "satırda sıfırdır.",
    "08-update":
        "Tablo değişmeye devam ediyor. Dört dakika sonra iki kişi yeniden cevap veriyor ve liste, "
        "kimse hiçbir şeye dokunmadan altıdan dörde iniyor.",
    "09-lookalikes":
        "Bir dedektör, ancak afete yalnızca benzeyen şeylerde sessiz kalabildiği ölçüde işe yarar. "
        "Bir hücre susup komşuları normal kalıyorsa bu bir baz istasyonu arızasıdır; dört hücre "
        "birlikte susuyor ama operatörün takvimindeki bir bakım kaydıyla eşleşiyorsa bu beklenen "
        "bir şeydir; dokuz hücre doyuyor ama her nöbetçi hâlâ cevap veriyorsa bu bir stadyumdur. "
        "Üç çekimser karar, üç yazılı gerekçe ve sıfır yanlış alarm.",
    "10-degraded":
        "Sonra zor olanı geliyor. Arızalı bir aktarım hattındaki dört hücre, bir afetin sahip "
        "olduğu her sinyali üretiyor ve hiçbir takvim bunu açıklamıyor; ajan da açıklamak yerine "
        "onları ölçüyor: bu hücreler son on bir geçişin üçünde zaten erişilemezdi, yani buradaki "
        "sessizlik normaldir ve normal olan haber değildir. Üstelik aynı koşuda, şehir "
        "merkezindeki gerçek bir deprem yine ilan ediliyor, dolayısıyla ret ölçülmüş bir karardır, "
        "körlük değil.",
    "11-real":
        "Sonra afeti çizmeyi tamamen bıraktık. Buradaki coğrafya ve her hücredeki sarsıntı, altı "
        "Şubat iki bin yirmi üç tarihli, yedi virgül sekiz büyüklüğündeki Pazarcık depreminin "
        "USGS ShakeMap verisinden geliyor; iki yüz altmış iki sismik istasyonla kısıtlanmış bir "
        "alan. Sarsıntıdan elli beş saniye sonra yirmi bir bitişik hücre, iki bin yüz "
        "kilometrekare ilan ediliyor ve isimlendirdiği her hücre, ölçülen sarsıntının çökme "
        "eşiğinin üstüne koyduğu bir hücre; yani hasar uydurmuyor. Boyut tabanının altında kalan "
        "izole bir cebi, iki hücreyi, bilerek iddia etmiyor. Sonra ayakta kalan direkler "
        "elektriğini kaybedip akülerini tüketirken etki alanı altı bin üç yüz kilometrekareye "
        "büyüyor, ki saha raporlarının anlattığı da tam olarak budur.",
    "12-hood":
        "Kaputun altında ajan bir LangGraph grafiği ve koşullu kenar, gizlilik iddiasının koda "
        "yazılmış hali; çünkü kişisel cihaz sorgulayan düğüme yalnızca aktif etki alanı olan bir "
        "karardan ulaşılabiliyor. Tespit deterministik ve tekrar oynatılabilir kalırken, dil "
        "modeli nöbetçi subayın brifingini yazıyor ve başka hiçbir şey yapmıyor. Düz döngü ile "
        "LangGraph koşucusu ise seksen üç testin altında bayt bayt aynı kanıtı üretiyor.",
    "13-parity":
        "Kum havuzu bir afeti sahneleyemez, o yüzden iki iddiayı ayırdık: canlı platform "
        "entegrasyonu kanıtlıyor, simülatör ise senaryoyu. Risk hiçbir zaman simülatörün kendisi "
        "değildi, iki yol arasında sezilen bir boşluktu; ölçtüğümüz de tam olarak o boşluk. Her "
        "sahne kaydediliyor ve canlı ağ geçidinin kullandığı aynı üç ayrıştırma fonksiyonundan "
        "geri oynatılıyor, kanıtın da satır satır aynı çıkması gerekiyor.",
    "14-close":
        "Nabd hangi afet olduğuna bakmıyor, çünkü ağ açısından deprem de sel de fırtına da "
        "kitlesel kesinti de aynı şeydir: kararan bir alan. Alıcılar sivil savunma kurumları ve "
        "belediyeler, operatörün Open Gateway'i üzerinden. Ağ zaten biliyor; Nabd sadece ona bunu "
        "söyletiyor, ilk dakikada. Kadir'in Ekibi'nden, MENA Ignite iki bin yirmi altı için.",
}


# ---------------------------------------------------------------- narration


class QuotaSpent(RuntimeError):
    """The Space's shared GPU allowance ran out. Not a failure — a pause."""


async def _edge(text: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, cfg("voice"), rate=cfg("rate")).save(str(out))


def _chatterbox(text: str, out: Path) -> None:
    """One segment through the Chatterbox Space, converted to mp3 like the rest."""
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
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", wav, "-b:a", "160k", str(out), "-y"], check=True,
    )


def narrate(segments: list[Segment], skip: bool) -> None:
    todo = [s for s in segments if not (skip and s.audio.exists())]
    todo = [s for s in todo if not s.audio.exists()] if ENGINE == "chatterbox" else todo
    done = 0
    for seg in todo:
        try:
            if ENGINE == "edge":
                print(f"  tts   {seg.id}")
                asyncio.run(_edge(narration(seg), seg.audio))
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


def shoot(segments: list[Segment]) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # Cards are authored at 1920x1080 and shot at scale 1; the console is a
        # 1600x900 layout scaled 1.2 to fill the same frame.
        cards = [s for s in segments if s.card]
        if cards:
            page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            page.goto((HERE / cfg("cards")).as_uri())
            page.wait_for_timeout(400)
            for seg in cards:
                print(f"  card  {seg.id}")
                page.locator(f"#{seg.card}").screenshot(path=str(seg.stills()[0]))
            page.close()

        shots = [s for s in segments if not s.card and not all(p.exists() for p in s.stills())]
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
    concat = outdir() / "frames.txt"
    out_file = ROOT / cfg("out")
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

    alist = outdir() / "audio.txt"
    alist.write_text("\n".join(f"file '{p.as_posix()}'" for p in audio_parts) + "\n", encoding="utf-8")
    voice = outdir() / "voice.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alist),
         "-c:a", "aac", "-b:a", "160k", str(voice), "-y"], check=True,
    )

    write_timeline(timeline, total)
    print(f"\n  muxing {total:.1f}s → {out_file.name}")
    subprocess.run(
        ["ffmpeg", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(voice),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "20",
         "-preset", "medium", "-movflags", "+faststart",
         "-c:a", "copy", "-shortest", str(out_file), "-y"], check=True,
    )


def write_timeline(rows: list[tuple[str, float, float, list[str]]], total: float) -> None:
    """The shot list, regenerated from the build so it cannot drift from the film."""
    by_id = {s.id: s for s in SEGMENTS}
    out = [
        f"# {cfg('title')}",
        "",
        f"*Generated by `python docs/video/build.py --lang {LANG}`. {cfg('out')} · 1920×1080 · "
        f"{int(total // 60)}:{int(total % 60):02d} · {LANG} narration "
        f"({cfg('voice')} via edge-tts, rate {cfg('rate')}).*",
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
    parser.add_argument("--engine", choices=("chatterbox", "edge"), default="chatterbox",
                        help="narration engine; edge needs no account and sounds it")
    parser.add_argument("--only", help="rebuild assets for one segment id")
    parser.add_argument("--no-tts", action="store_true", help="reuse the narration already rendered")
    parser.add_argument("--no-shoot", action="store_true", help="reuse the frames already rendered")
    args = parser.parse_args(argv[1:])

    global LANG, ENGINE
    LANG = args.lang
    ENGINE = args.engine

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

    todo = [s for s in SEGMENTS if not args.only or s.id == args.only]
    if not todo:
        print(f"no segment matches {args.only}", file=sys.stderr)
        return 2

    print(f"\n  {LANG} cut \u2014 narration via {ENGINE} ({len(todo)} segment(s))")
    narrate(todo, skip=args.no_tts)
    if not args.no_shoot:
        print(f"\n  frames")
        shoot(todo)
    if args.only:
        print("\n  assets rebuilt; run without --only to assemble\n")
        return 0
    print(f"\n  timeline")
    assemble(SEGMENTS)
    out_file = ROOT / cfg("out")
    print(f"\n  {out_file.name}: {out_file.stat().st_size // 1024} KB\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
