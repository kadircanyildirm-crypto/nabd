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
    "exaggeration": 0.25,
    "temperature": 0.60,
    "cfg_weight": 0.35,
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
        text="Nabd. Read where the network goes silent. "
             "An AI agent that maps where a disaster hit, "
             "on Nokia Network-as-Code and LangGraph.",
    ),
    Segment(
        "02-problem", card="c02-problem",
        text="A seismometer knows in seconds. It happened. "
             "But the question that costs lives is a different one. "
             "Which district first? Who is cut off? "
             "That answer takes hours. "
             "In Kahramanmaraş, in twenty twenty-three, more than fifty-three thousand people died. "
             "Nabd is not early warning. "
             "It's the impact map. In the first minute.",
    ),
    Segment(
        "03-insight", card="c03-insight",
        text="Coordinated silence is a sensor. So Nabd has two layers. "
             "The first one is aggregate. A grid of sentinel devices, one per cell. "
             "Municipal or operator SIMs. Never the public. Read every thirty seconds. "
             "The second layer is consented. It only looks at people who asked to be found. "
             "And only inside an area the agent has already declared.",
    ),
    Segment(
        "04-quiet", frames=[("quiet", 2), ("quiet", 6), ("quiet", 9)],
        text="This is the command centre. Every square is a cell, with one sentinel in it. "
             "On an ordinary morning they all answer. "
             "The agent has nothing to say, so it says nothing.",
    ),
    Segment(
        "05-onset", frames=[("quake", 4), ("quake", 5)],
        text="Nine oh two. An earthquake. "
             "Nobody knows yet which neighbourhoods were hit. "
             "Nine cells go silent at once. "
             "But watch what the agent does. It marks a candidate, and it waits one more pass. "
             "One signal never declares alone.",
    ),
    Segment(
        "06-declare", frames=[("quake", 6)],
        text="Fifty-five seconds after the shaking. It declares. "
             "Nine cells. About four square kilometres. Confidence high. "
             "Two gates passed: the block is contiguous, and this silence is abnormal here. "
             "And two corroborations. The onset was synchronised. "
             "And the ring is hot. Sixteen of sixteen neighbouring cells saturated, "
             "because everyone is calling at the same moment.",
    ),
    Segment(
        "07-triage", frames=[("quake", 6), ("quake", 7)],
        text="Only now does the agent touch a personal device. "
             "Thirteen registered people live inside the footprint. Six are unreachable. "
             "Ranked by need. Each with a last-seen position. "
             "And every pass of the evidence says whether that personal path was open, "
             "and how many calls it made. "
             "On an ordinary morning, that number is zero. On every line.",
    ),
    Segment(
        "08-update", frames=[("quake", 14), ("quake", 16)],
        text="The picture keeps moving. Four minutes later, two people answer again. "
             "The list goes from six to four. Nobody touched it.",
    ),
    Segment(
        "09-lookalikes", frames=[("noise", 2), ("noise", 6), ("noise", 10)],
        text="A detector is only useful if it stays quiet on the things that look like disasters. "
             "One cell goes silent, neighbours normal. That's a base station fault. "
             "Four cells go silent together, but they match a maintenance ticket "
             "on the operator's calendar. That's expected. "
             "Nine cells saturate, and every sentinel still answers. That's a stadium. "
             "Three abstentions. Three written reasons. No false alarm.",
    ),
    Segment(
        "10-degraded", frames=[("degraded", 11), ("degraded", 21)],
        text="Then the hard one. Four cells on a failing backhaul. "
             "They produce every signal a disaster has. "
             "And nothing on the calendar explains them. "
             "So the agent measures them instead. "
             "These cells were already unreachable in three of the last eleven passes. "
             "Silence here is normal. And normal isn't news. "
             "Then, in the same run, a real earthquake in the city centre is still declared. "
             "The refusal is measured. It isn't blindness.",
    ),
    Segment(
        "11-real", frames=[("maras", 6), ("maras", 15), ("maras", 23)],
        text="Then we stopped drawing the disaster. "
             "The geometry here, and the shaking in every cell, come from the USGS ShakeMap "
             "for the Pazarcık earthquake. Magnitude seven point eight. "
             "Sixth of February, twenty twenty-three. Two hundred and sixty-two seismic stations. "
             "Fifty-five seconds after onset: twenty-one contiguous cells. "
             "Twenty-one hundred square kilometres. "
             "And every cell it names is one the measured shaking puts above the collapse threshold. "
             "It invents no damage. "
             "Two more cells, an isolated pocket below the size floor, it deliberately does not claim. "
             "Then the footprint grows. Six thousand three hundred square kilometres, "
             "as the surviving masts lose power and drain their batteries. "
             "Which is exactly what the field reports describe.",
    ),
    Segment(
        "12-hood", card="c10-hood",
        text="Under the hood, the agent is a LangGraph graph. "
             "And the conditional edge is the privacy claim, written in code: "
             "the node that queries a personal device can only be reached "
             "from a verdict with an active footprint. "
             "Detection is deterministic and replayable. "
             "The language model writes the duty officer's brief, and nothing else. "
             "The plain loop and the LangGraph runner produce byte-identical evidence, "
             "under eighty-three tests.",
    ),
    Segment(
        "13-parity", card="c11-parity",
        text="The sandbox can't stage a disaster. So we separated the two claims. "
             "The live platform proves the integration. The simulator proves the scenario. "
             "The risk was never the simulator. It was a suspected gap between the two paths. "
             "So that gap is what we measure. "
             "Every scene is recorded, and replayed through the same three parsing functions "
             "the live gateway uses. "
             "The evidence has to come out identical. Line for line.",
    ),
    Segment(
        "14-close", card="c12-close",
        text="Nabd doesn't care which disaster. "
             "Earthquake, flood, storm, mass outage. An area goes dark. "
             "The buyers are civil-defence agencies and municipalities, "
             "through the operator's Open Gateway. "
             "The network already knows. Nabd makes it say so. In the first minute. "
             "By Kadir's Team, for MENA Ignite twenty twenty-six.",
    ),
]


#: The Turkish cut. Not a translation of the English line by line — the same
#: point, said the way it would be said in Turkish, at a length that fits the
#: same frames.
TURKISH = {
    "01-title":
        "Nabd. Ağın sustuğu yeri okuyun. "
        "Afetin nereye vurduğunu haritalayan bir yapay zekâ ajanı. "
        "Nokia Network-as-Code ve LangGraph üzerinde.",
    "02-problem":
        "Bir sismometre saniyeler içinde biliyor. Oldu. "
        "Ama hayat pahasına olan soru başka. "
        "Önce hangi mahalle? Kim dışarıda kaldı? "
        "O cevap saatler sürüyor. "
        "Kahramanmaraş'ta, iki bin yirmi üçte, elli üç binden fazla insan öldü. "
        "Nabd erken uyarı değil. "
        "İlk dakikadaki etki haritası.",
    "03-insight":
        "Eşzamanlı sessizlik bir sensördür. Nabd'nin iki katmanı var. "
        "Birincisi toplu düzeyde. Hücre başına bir nöbetçi cihaz. "
        "Belediye ya da operatör SIM'i. Asla halkın telefonu. Otuz saniyede bir okunuyor. "
        "İkinci katman rızaya dayalı. Sadece bulunmak isteyen insanlara bakıyor. "
        "Ve sadece ajanın önceden ilan ettiği bir alanın içinde.",
    "04-quiet":
        "Karşınızdaki komuta merkezi. Her kare bir hücre, içinde bir nöbetçi. "
        "Sıradan bir sabahta hepsi cevap veriyor. "
        "Ajanın söyleyecek bir şeyi yok, o yüzden bir şey söylemiyor.",
    "05-onset":
        "Dokuz sıfır iki. Deprem. "
        "Hangi mahallelerin vurulduğunu henüz kimse bilmiyor. "
        "Dokuz hücre aynı anda susuyor. "
        "Ama ajanın ne yaptığına bakın. Aday olarak işaretliyor, ve bir geçiş daha bekliyor. "
        "Tek sinyal asla tek başına ilan ettirmez.",
    "06-declare":
        "Sarsıntıdan elli beş saniye sonra. İlan ediyor. "
        "Dokuz hücre. Yaklaşık dört kilometrekare. Güven yüksek. "
        "İki kapı geçildi: blok bitişik, ve bu sessizlik burada anormal. "
        "Ve iki destekleyici kanıt. Başlangıç eşzamanlıydı. "
        "Ve halka sıcak. Komşu on altı hücrenin on altısı doygun, "
        "çünkü herkes aynı anda arıyor.",
    "07-triage":
        "Ajan kişisel bir cihaza ancak şimdi dokunuyor. "
        "Etki alanının içinde on üç kayıtlı kişi yaşıyor. Altısına ulaşılamıyor. "
        "İhtiyaca göre sıralı. Her biri son görüldüğü konumla. "
        "Ve kanıt dosyasının her geçişi, o kişisel yolun açık olup olmadığını "
        "ve kaç çağrı yapıldığını yazıyor. "
        "Sıradan bir sabahta bu sayı sıfır. Her satırda.",
    "08-update":
        "Tablo değişmeye devam ediyor. Dört dakika sonra iki kişi yeniden cevap veriyor. "
        "Liste altıdan dörde iniyor. Kimse dokunmadı.",
    "09-lookalikes":
        "Bir dedektör, ancak afete benzeyen şeylerde sessiz kalabildiği ölçüde işe yarar. "
        "Bir hücre susuyor, komşuları normal. Bu bir baz istasyonu arızası. "
        "Dört hücre birlikte susuyor, ama operatörün takvimindeki bir bakım kaydıyla eşleşiyor. "
        "Bu beklenen. "
        "Dokuz hücre doyuyor, ve her nöbetçi hâlâ cevap veriyor. Bu bir stadyum. "
        "Üç çekimser karar. Üç yazılı gerekçe. Sıfır yanlış alarm.",
    "10-degraded":
        "Sonra zor olanı. Arızalı bir aktarım hattındaki dört hücre. "
        "Bir afetin sahip olduğu her sinyali üretiyorlar. "
        "Ve hiçbir takvim bunu açıklamıyor. "
        "Ajan da onları açıklamak yerine ölçüyor. "
        "Bu hücreler son on bir geçişin üçünde zaten erişilemezdi. "
        "Buradaki sessizlik normal. Ve normal, haber değildir. "
        "Sonra, aynı koşuda, şehir merkezindeki gerçek bir deprem yine ilan ediliyor. "
        "Ret ölçülmüştür. Körlük değildir.",
    "11-real":
        "Sonra afeti çizmeyi bıraktık. "
        "Buradaki coğrafya ve her hücredeki sarsıntı, Pazarcık depreminin "
        "USGS ShakeMap verisinden geliyor. Büyüklük yedi virgül sekiz. "
        "Altı Şubat, iki bin yirmi üç. İki yüz altmış iki sismik istasyon. "
        "Sarsıntıdan elli beş saniye sonra: yirmi bir bitişik hücre. "
        "İki bin yüz kilometrekare. "
        "Ve isimlendirdiği her hücre, ölçülen sarsıntının çökme eşiğinin üstüne koyduğu bir hücre. "
        "Hasar uydurmuyor. "
        "İki hücreyi daha, boyut tabanının altında kalan izole bir cebi, bilerek iddia etmiyor. "
        "Sonra etki alanı büyüyor. Altı bin üç yüz kilometrekare. "
        "Ayakta kalan direkler elektriğini kaybedip akülerini tüketirken. "
        "Ki saha raporlarının anlattığı tam olarak bu.",
    "12-hood":
        "Kaputun altında ajan bir LangGraph grafiği. "
        "Ve koşullu kenar, gizlilik iddiasının koda yazılmış hali: "
        "kişisel cihaz sorgulayan düğüme, sadece aktif etki alanı olan bir karardan ulaşılabiliyor. "
        "Tespit deterministik ve tekrar oynatılabilir. "
        "Dil modeli nöbetçi subayın brifingini yazıyor, başka bir şey yapmıyor. "
        "Düz döngü ve LangGraph koşucusu bayt bayt aynı kanıtı üretiyor. "
        "Seksen üç testin altında.",
    "13-parity":
        "Kum havuzu bir afeti sahneleyemez. Biz de iki iddiayı ayırdık. "
        "Canlı platform entegrasyonu kanıtlıyor. Simülatör senaryoyu kanıtlıyor. "
        "Risk hiçbir zaman simülatör değildi. İki yol arasında sezilen bir boşluktu. "
        "Ölçtüğümüz de o boşluk. "
        "Her sahne kaydediliyor, ve canlı ağ geçidinin kullandığı aynı üç ayrıştırma "
        "fonksiyonundan geri oynatılıyor. "
        "Kanıtın birebir aynı çıkması gerekiyor. Satır satır.",
    "14-close":
        "Nabd hangi afet olduğuna bakmıyor. "
        "Deprem, sel, fırtına, kitlesel kesinti. Bir alan kararıyor. "
        "Alıcılar sivil savunma kurumları ve belediyeler, operatörün Open Gateway'i üzerinden. "
        "Ağ zaten biliyor. Nabd ona bunu söyletiyor. İlk dakikada. "
        "Kadir'in Ekibi'nden, MENA Ignite iki bin yirmi altı için.",
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
