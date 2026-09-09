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
        text="Nabd. In Arabic it means pulse, and that is close to what it does, because when a "
             "disaster hits, a whole neighbourhood of the mobile network stops answering in the "
             "same second. Nabd reads that silence, and turns it into a map of where the damage is.",
    ),
    Segment(
        "02-problem", card="c02-problem",
        text="On the sixth of February, twenty twenty-three, a seismometer confirmed within seconds "
             "that an earthquake had struck Kahramanmaraş. It was hours before anyone knew which "
             "streets to dig in, and more than fifty-three thousand people died. The rescue was held "
             "back not by machines or by people, but by not knowing where to send them — and the "
             "picture that would have answered that was being assembled from emergency calls, at "
             "the moment the network was too overloaded to carry them.",
    ),
    Segment(
        "03-insight", card="c03-insight",
        text="But there was something nobody was reading. When the ground moves, the network does "
             "something a disaster cannot hide: a connected block of cells stops answering in the "
             "same second, while the ring around it saturates, because everyone still standing is "
             "calling at once. Nabd reads that shape through standard CAMARA APIs, in two layers: "
             "detection is aggregate, one sentinel SIM to a cell, never a member of the public, and "
             "triage is consented, only ever inside an area the agent has already declared.",
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
             "synchronised and all sixteen cells around it are saturated.",
    ),
    Segment(
        "07-triage", frames=[("quake", 6), ("quake", 7)], tab="registry",
        text="Only now does the agent touch a personal device. Thirteen people inside that footprint "
             "are on the opt-in registry, and six are not answering, ranked by need, with the last "
             "place the network saw them. Every line of the evidence records how many personal calls "
             "were made, and on an ordinary morning that number is zero.",
    ),
    Segment(
        "08-update", frames=[("quake", 14), ("quake", 16)], tab="registry",
        text="The map is not a snapshot either. Four minutes later, two of those six answer again, "
             "and the list corrects itself from six to four, with nobody touching it.",
    ),
    Segment(
        "09-lookalikes", frames=[("noise", 2), ("noise", 6), ("noise", 10)], tab="log",
        text="Anything can be built to fire. The work is in what it refuses. One cell silent while "
             "its neighbours are normal is a base station fault. Four silent together, matching a "
             "ticket on the operator's maintenance calendar, is expected work. Nine saturated while "
             "every sentinel answers is a football crowd. Three abstentions, three written reasons, "
             "no alarm.",
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
             "square kilometres, as the surviving masts run their batteries flat.",
    ),
    Segment(
        "11b-atlas", frames=[("atlas", 5), ("atlas", 12), ("atlas", 22)],
        text="A detector tested on the one event it was tuned for has not really been tested. So "
             "we ran it again over the magnitude six point eight Al Haouz earthquake in Morocco, and "
             "changed nothing: the same thresholds, the same code. An earthquake that size, nineteen "
             "kilometres down, does not flatten a block, so the first verdict here is a refusal. It "
             "declares almost four minutes later, at medium confidence, and it says why: the onset "
             "genuinely was staggered, because the footprint arrived as mountain villages drained "
             "their batteries. And Marrakesh, shaken hard enough to lead the news everywhere, "
             "answered throughout, and is never named. A map of what was shaken would have claimed "
             "Marrakesh. A map of what went silent does not. That ShakeMap had three seismic "
             "stations behind it, against two hundred and sixty-two for Kahramanmaraş. Where the "
             "instruments are thinnest, the network is still talking.",
    ),
    Segment(
        "12-hood", card="c10-hood",
        text="Under the hood the agent is a LangGraph graph, and the privacy claim lives in the "
             "topology rather than in a promise, because the node that queries a personal device can "
             "only be reached from a verdict with an active footprint. Detection stays deterministic "
             "and replayable, while the language model writes the duty officer's brief and nothing "
             "else. Both runners produce byte-identical evidence, under ninety-three tests.",
    ),
    Segment(
        "13-parity", card="c11-parity",
        text="The sandbox cannot stage a disaster, so we separated the two claims: the live platform "
             "proves the integration, and the simulator proves the scenario. The risk was a gap "
             "between them, so the gap is what we measure. Every scene is recorded and replayed "
             "through the same parsing functions the live gateway uses, and the evidence has to "
             "come out identical, line for line. One check needs a live key, and until it runs it "
             "reports pending. It never reports pass.",
    ),
    Segment(
        "14-close", card="c12-close",
        text="To the network, an earthquake, a flood, a storm and a mass outage are the same thing: "
             "an area going dark. Watching the whole of Türkiye takes seven thousand eight hundred "
             "sentinel SIMs, not eighty-five million subscribers, so the bill scales with land area "
             "rather than population, and the operator sells it through Open Gateway to the agency "
             "that already carries the duty of care. The network already knows. Nabd only "
             "makes it say so, in the first minute. Kadir's Team, Türkiye, for MENA Ignite twenty "
             "twenty-six.",
    ),
]


#: The Turkish cut. Not a translation of the English line by line — the same
#: point, said the way it would be said in Turkish, at a length that fits the
#: same frames.
TURKISH = {
    "01-title":
        "Nabd. Arapçada nabız demek, ki yaptığı işe de yakın; çünkü bir afet vurduğunda mobil "
        "ağın koca bir mahallesi aynı saniyede cevap vermeyi kesiyor. Nabd bu sessizliği okuyor "
        "ve onu, hasarın nerede olduğunun haritasına çeviriyor.",
    "02-problem":
        "Altı Şubat iki bin yirmi üçte bir sismometre, Kahramanmaraş'ta depremin olduğunu "
        "saniyeler içinde doğruladı. Hangi sokakta kazılacağını öğrenmek ise saatler aldı ve elli "
        "üç binden fazla insan hayatını kaybetti. Kurtarmayı geciktiren makine ya da insan "
        "değildi; nereye gönderileceğinin bilinmemesiydi. O soruyu cevaplayacak tablo ise acil "
        "çağrılardan toplanıyordu, tam da ağın o çağrıları taşıyamayacak kadar tıkalı olduğu anda.",
    "03-insight":
        "Ama kimsenin okumadığı bir şey vardı. Yer sarsıldığında ağ, bir afetin saklayamayacağı "
        "bir şey yapar: bitişik bir hücre bloğu aynı saniyede susar, etrafındaki halka ise doyar, "
        "çünkü ayakta kalan herkes aynı anda arıyordur. Nabd bu deseni standart CAMARA API'leri "
        "üzerinden iki katmanda okuyor: tespit toplu düzeydedir, hücre başına bir nöbetçi SIM, "
        "asla halktan biri değil; triyaj ise rızaya dayalıdır ve yalnızca ajanın önceden ilan "
        "ettiği bir alanın içinde çalışır.",
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
        "hücrenin on altısı doygun.",
    "07-triage":
        "Ajan kişisel bir cihaza ancak şimdi dokunuyor. O etki alanının içinde on üç kişi gönüllü "
        "kayıt listesinde ve altısına ulaşılamıyor; ihtiyaca göre sıralanmış, her biri ağın onu en "
        "son gördüğü konumla birlikte. Kanıt dosyasının her satırı kaç kişisel çağrı yapıldığını "
        "da yazıyor ve sıradan bir sabahta bu sayı sıfır.",
    "08-update":
        "Harita bir anlık görüntü de değil. Dört dakika sonra o altı kişiden ikisi yeniden cevap "
        "veriyor ve liste, kimse hiçbir şeye dokunmadan altıdan dörde iniyor.",
    "09-lookalikes":
        "Ateş eden bir şeyi herkes yapabilir; asıl iş, neyi reddettiğindedir. Komşuları normalken "
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
        "kilometrekareye büyüyor.",
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
        "modeli yalnızca nöbetçi subayın brifingini yazıyor. İki koşucu da doksan üç testin "
        "altında bayt bayt aynı kanıtı üretiyor.",
    "13-parity":
        "Kum havuzu bir afeti sahneleyemez, o yüzden iki iddiayı ayırdık: canlı platform "
        "entegrasyonu kanıtlıyor, simülatör ise senaryoyu. Risk, bu iki yol arasındaki boşluktu; "
        "ölçtüğümüz de tam olarak o boşluk. Her sahne kaydediliyor ve canlı ağ geçidinin "
        "kullandığı aynı ayrıştırma fonksiyonlarından geri oynatılıyor, kanıtın da satır satır "
        "aynı çıkması gerekiyor. Bir kontrol canlı anahtar istiyor ve o koşana kadar beklemede "
        "yazıyor. Asla geçti yazmıyor.",
    "14-close":
        "Ağ açısından deprem de sel de fırtına da kitlesel kesinti de aynı şeydir: kararan bir "
        "alan. Türkiye'nin tamamını izlemek yedi bin sekiz yüz nöbetçi SIM istiyor, seksen beş "
        "milyon abone değil; yani fatura nüfusa göre değil, yüzölçümüne göre büyüyor ve operatör "
        "bunu Open Gateway üzerinden, sorumluluğu zaten taşıyan kuruma satıyor. Ağ zaten biliyor. "
        "Nabd sadece ona bunu söyletiyor, ilk dakikada. Kadir'in Ekibi'nden, Türkiye'den, MENA "
        "Ignite iki bin yirmi altı için.",
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
                print(f"  card  {seg.id}")
                page.locator(f"#{seg.card}").screenshot(path=str(seg.stills()[0]))
            page.close()
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
