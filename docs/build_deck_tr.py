# -*- coding: utf-8 -*-
"""docs/nabd-deck-tr.html — the Turkish cut of the deck.

    python docs/build_deck_tr.py
    chrome --headless=new --disable-gpu --no-pdf-header-footer \\
        --print-to-pdf=Nabd-Pitch-Deck-TR.pdf docs/nabd-deck-tr.html

Same sixteen slides, same evidence, same stylesheet — the prose is written in
Turkish rather than translated fragment by fragment, because English and Turkish
put their words in different orders and a phrase-level swap produces neither.

What stays in English is the command-centre console on slide 9: that is the
product's own screen, and its verdict lines come out of the evidence file. Dubbing
a screenshot would be the one dishonest thing in a deck whose whole argument is
that nothing on screen is mocked.

Everything shared — the stylesheet, the grid renderer, the evidence handles — is
imported from `build_deck.py`, so a change to the English deck's chrome reaches
this one too.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "nabd-deck-tr.html"

_spec = importlib.util.spec_from_file_location("build_deck", Path(__file__).resolve().parent / "build_deck.py")
_en = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_en)

grid_svg, legend, person_row = _en.grid_svg, _en.legend, _en.person_row
CSS, SCRIPT = _en.CSS, _en.SCRIPT
GRID_DECL, GRID_CROWD, GRID_MAINT, GRID_FAULT = _en.GRID_DECL, _en.GRID_CROWD, _en.GRID_MAINT, _en.GRID_FAULT
GRID_HELD, GRID_BOTH = _en.GRID_HELD, _en.GRID_BOTH
GRID_MARAS_1, GRID_MARAS_2 = _en.GRID_MARAS_1, _en.GRID_MARAS_2
DECL, top3 = _en.DECL, _en.top3

slides = []

# ---------- 1 kapak
slides.append(f"""
<section class="slide cover" id="slide-1">
  <div class="kicker">GSMA MENA Ignite Open Gateway Hackathon 2026 &nbsp;·&nbsp; Prototip Aşaması</div>
  <h1>Nabd <span class="ar">· نبض</span></h1>
  <p class="tag">Ağın sustuğu yeri okuyun.</p>
  <p class="cover-sub">Eşzamanlı ağ sessizliğini komuta merkezleri için canlı bir afet etki haritasına
  çeviren yapay zekâ ajanı — ilk dakikada etki haritası, ilk 72 saatte önceliklendirme.</p>
  <div class="chips">
    <span>Tema 6 — İklim Dayanıklılığı ve Çevresel İzleme</span>
    <span>Nokia Network-as-Code</span>
    <span>Ajan katmanı: LangGraph</span>
    <span>Kadir'in Ekibi</span>
  </div>
  <div class="cover-grid">{grid_svg(GRID_DECL, 300, labels=False, ring=True)}</div>
</section>""")

# ---------- 2 yara
slides.append("""
<section class="slide" id="slide-2">
  <div class="kicker">Yara</div>
  <h2>Kimin sağ bulunacağına ilk saatler karar verir.</h2>
  <div class="stats3">
    <div><b>53.000+</b><span>Kahramanmaraş, Türkiye<br>depremler, Şubat 2023</span></div>
    <div><b>~3.000</b><span>El Haouz, Fas<br>deprem, Eylül 2023</span></div>
    <div><b>11.000+</b><span>Derna, Libya<br>baraj çöküşü ve sel, Eylül 2023</span></div>
  </div>
  <p class="lead" style="font-size:30px;max-width:1080px">Hepsinde sensörler <em>bir şey</em> olduğunu saniyeler
  içinde doğruladı. Hangi mahallelerin insanını kaybettiğini gösteren harita ise saatler sonra geldi.</p>
  <p class="note" style="font-size:20px;margin-top:22px">2024: Dubai ve Umman selleri. Aynı bölge, farklı bir tehlike, aynı eksik harita.</p>
</section>""")

# ---------- 3 boşluk
slides.append("""
<section class="slide" id="slide-3">
  <div class="kicker">Boşluk</div>
  <h2>Tespit çözüldü. Etki çözülmedi.</h2>
  <div class="two">
    <div class="card">
      <div class="lbl">Saniyeler</div>
      <p>Sismometreler, uydular ve telefon tabanlı sistemler <b>“oldu”</b> der, neredeyse anında.</p>
    </div>
    <div class="card">
      <div class="lbl">Saatler</div>
      <p><b>“Önce hangi ilçe?”</b> sorusu dağınık aramalardan, sosyal medyadan ve saha raporlarından
      parça parça kurulur — hem de tam o anda çökmüş bir ağ üzerinde.</p>
    </div>
  </div>
  <div class="two claims">
    <div class="no"><div class="lbl">Nabd şu değildir</div><p>erken uyarı. Deprem tespiti sismometrelerin ve mevcut uyarı sistemlerinin işidir; onlarla yarışmıyoruz.</p></div>
    <div class="yes"><div class="lbl">Nabd şudur</div><p><b>ilk dakikada etki haritası</b> ve <b>ilk 72 saatte önceliklendirme</b> — kim dışarıda kaldı, nerede.</p></div>
  </div>
</section>""")

# ---------- 4 fikir
slides.append("""
<section class="slide" id="slide-4">
  <div class="kicker">Fikir</div>
  <h2 class="huge">Sessizlik bir sensördür.</h2>
  <p class="lead wide">Koca bir hücre bloğu aynı anda karardığında, ağ afetin nereye vurduğunu zaten
  biliyordur — daha tek bir acil çağrı bile geçmeden önce.</p>
  <div class="steps">
    <div><i>1</i><p>Bir alan <b>kararır</b>: hücreleri cevap vermeyi keser.</p></div>
    <div><i>2</i><p>Etrafındaki halka <b>ısınır</b>: herkes aynı anda arar.</p></div>
    <div><i>3</i><p>Bu ikisi, aynı anda, <b>başka hiçbir olayın üretmediği</b> bir imzadır.</p></div>
  </div>
  <p class="note">Afetten bağımsız: deprem, sel, fırtına, kitlesel elektrik kesintisi — ağ için hepsi aynı şeydir, susan bir alan.</p>
</section>""")

# ---------- 5 iki katman (şema)
slides.append("""
<section class="slide" id="slide-5">
  <div class="kicker">Mimari</div>
  <h2>İki katman. Tespit toplu düzeyde; önceliklendirme rızaya dayalı.</h2>
  <svg class="diagram" viewBox="0 0 1152 470" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#41504a"/></marker>
    </defs>
    <rect x="0" y="0" width="540" height="470" rx="14" fill="#f2f6f4"/>
    <text x="24" y="38" class="h">TESPİT — toplu düzeyde, halka ait hiçbir cihaz yok</text>
    <rect x="24" y="60" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="40" y="90" class="t">Nöbetçi ızgarası — hücre başına bir belediye/operatör SIM'i</text>
    <text x="40" y="118" class="s">30 sn'de bir okunur · prototipte Kahramanmaraş üzerinde 10×10 hücre</text>
    <rect x="24" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="142" y="200" class="api" text-anchor="middle">Congestion Insights</text>
    <text x="142" y="226" class="s" text-anchor="middle">hücre başına yük</text>
    <rect x="280" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="398" y="200" class="api" text-anchor="middle">Device Reachability</text>
    <text x="398" y="226" class="s" text-anchor="middle">nöbetçi cevap veriyor mu?</text>
    <rect x="24" y="268" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="40" y="298" class="t">Bitişik susan blok + sıcak halka + süreklilik</text>
    <text x="40" y="326" class="s">önce bakım takvimi ayıklanır · tek sinyal asla tek başına ilan ettirmez</text>
    <rect x="24" y="378" width="492" height="70" rx="10" fill="#17211D"/>
    <text x="270" y="408" class="w" text-anchor="middle">Etki alanı ilan edildi — YÜKSEK / ORTA</text>
    <text x="270" y="434" class="ws" text-anchor="middle">ya da gerekçesi yazılmış bir çekimser karar</text>
    <line x1="270" y1="146" x2="270" y2="168" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="270" y1="244" x2="270" y2="266" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="270" y1="354" x2="270" y2="376" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <rect x="612" y="0" width="540" height="470" rx="14" fill="#f2f6f4"/>
    <text x="636" y="38" class="h">ÖNCELİKLENDİRME — kişi bazında, yalnızca kayıt olanlar</text>
    <rect x="636" y="60" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="652" y="90" class="t">Korunmak isteyen kişilerin kayıt defteri</text>
    <text x="652" y="118" class="s">yaşlı · engelli · hac grubu · yalnız çalışan — takma kimliklerle</text>
    <rect x="636" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="754" y="200" class="api" text-anchor="middle">Device Reachability</text>
    <text x="754" y="226" class="s" text-anchor="middle">kime ulaşılamıyor</text>
    <rect x="892" y="170" width="236" height="74" rx="10" fill="#fff" stroke="#0E6E52"/>
    <text x="1010" y="200" class="api" text-anchor="middle">Location Retrieval</text>
    <text x="1010" y="226" class="s" text-anchor="middle">en son nerede görüldü</text>
    <rect x="636" y="268" width="492" height="86" rx="10" fill="#fff" stroke="#d7ded9"/>
    <text x="652" y="298" class="t">Sıralı liste: öncelikli bölgeler ve önce ulaşılacak kişiler</text>
    <text x="652" y="326" class="s">insanlar yeniden cevap verdikçe her geçişte güncellenir</text>
    <rect x="636" y="378" width="492" height="70" rx="10" fill="#0E6E52"/>
    <text x="882" y="408" class="w" text-anchor="middle">Komuta merkezi brifingi</text>
    <text x="882" y="434" class="ws" text-anchor="middle">harita · karar · sinyaller · liste — kanıt kaydından tekrar oynatılabilir</text>
    <line x1="882" y1="146" x2="882" y2="168" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="882" y1="244" x2="882" y2="266" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="882" y1="354" x2="882" y2="376" stroke="#41504a" stroke-width="2" marker-end="url(#arr)"/>
    <line x1="516" y1="413" x2="634" y2="413" stroke="#0E6E52" stroke-width="3" marker-end="url(#arr)"/>
    <rect x="546" y="356" width="60" height="42" rx="8" fill="#fff" stroke="#0E6E52"/>
    <text x="576" y="383" class="gate" text-anchor="middle">kapı</text>
    <text x="576" y="446" class="gs" text-anchor="middle">yalnızca ilan edilmiş</text>
    <text x="576" y="464" class="gs" text-anchor="middle">bir etki alanı içinde</text>
  </svg>
</section>""")

# ---------- 6 ilk dakika imzası
slides.append(f"""
<section class="slide" id="slide-6">
  <div class="kicker">İlk dakikanın imzası</div>
  <h2>Bir blok susar. Etrafındaki halka ısınır.</h2>
  <div class="sig">
    <div class="sig-grid">{grid_svg(GRID_DECL, 400, ring=True)}{legend()}</div>
    <div class="sig-text">
      <div class="sigrow"><b class="red">9 hücre sustu</b><p>E4 → G6, yaklaşık 4,0 km². Nöbetçileri cevap vermeyi kesti — <em>Device Reachability</em>.</p></div>
      <div class="sigrow"><b class="amber">Halkanın 16 / 16 hücresi Yüksek</b><p>Bloğun etrafındaki herkes aynı anda arıyor — <em>Congestion Insights</em>.</p></div>
      <div class="sigrow"><b>Başlangıç eşzamanlı</b><p>Dokuzu da tek bir 30 saniyelik pencere içinde karardı. Bir baz istasyonu arızası bunu yapmaz.</p></div>
      <div class="sigrow"><b>İkinci geçişte de sürdü</b><p>09:02:30'da aday, 09:03:00'te ilan — sarsıntıdan <b>55 saniye sonra</b>, güven <b>YÜKSEK</b>.</p></div>
    </div>
  </div>
  <p class="note" style="margin-top:8px">Izgara, ilan geçişinin kanıt kaydından çiziliyor; çizim değil.</p>
</section>""")

# ---------- 7 ajan
slides.append("""
<section class="slide" id="slide-7">
  <div class="kicker">Ajan — zorunlu bileşen, LangGraph üzerinde</div>
  <h2>Tek bir sinyal asla tek başına ilan ettirmez.</h2>
  <div class="agent">
    <svg class="topo" viewBox="0 0 600 440" xmlns="http://www.w3.org/2000/svg">
      <defs><marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#41504a"/></marker></defs>
      <g class="node"><rect x="200" y="10" width="160" height="46" rx="23"/><text x="280" y="39">algıla</text></g>
      <g class="node"><rect x="200" y="86" width="160" height="46" rx="23"/><text x="280" y="115">ilişkilendir</text></g>
      <g class="node"><rect x="200" y="162" width="160" height="46" rx="23"/><text x="280" y="191">ayıkla</text></g>
      <g class="node key"><rect x="200" y="238" width="160" height="46" rx="23"/><text x="280" y="267">ilan et</text></g>
      <g class="node"><rect x="40" y="326" width="160" height="46" rx="23"/><text x="120" y="355">bekle</text></g>
      <g class="node key2"><rect x="360" y="326" width="160" height="46" rx="23"/><text x="440" y="355">önceliklendir</text></g>
      <g class="node"><rect x="200" y="394" width="160" height="46" rx="23"/><text x="280" y="423">brifing → kayıt</text></g>
      <line x1="280" y1="56" x2="280" y2="84" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <line x1="280" y1="132" x2="280" y2="160" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <line x1="280" y1="208" x2="280" y2="236" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <path d="M230,284 C200,310 160,300 130,324" fill="none" stroke="#41504a" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#a2)"/>
      <path d="M330,284 C360,310 400,300 430,324" fill="none" stroke="#0E6E52" stroke-width="2.5" stroke-dasharray="6 5" marker-end="url(#a2)"/>
      <path d="M150,372 C180,392 210,392 245,393" fill="none" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <path d="M410,372 C380,392 350,392 315,393" fill="none" stroke="#41504a" stroke-width="2" marker-end="url(#a2)"/>
      <text x="96" y="306" class="edge">etki alanı yok</text>
      <text x="392" y="306" class="edge green">etki alanı ilan edildi</text>
      <text x="478" y="258" class="side">koşullu kenar</text>
      <text x="478" y="276" class="side">önceliklendirmeyi kapatır</text>
    </svg>
    <div class="agent-text">
      <p><b>İki kapı, sonra destek.</b> Bir etki alanı için bitişik bir susan blok <i>ve</i> o hücrelerin kendi geçmişine göre <i>burada</i> anormal olan bir sessizlik gerekir. Bir kapı ilanı veto edebilir; asla ilana sebep olamaz.</p>
      <p><b>Güveni derecelendir.</b> Destekleyiciler — eşzamanlı başlangıç, sıcak halka — sabit bir çift değil, aritmetiğin saydığı bir listedir. İki → YÜKSEK. Bir → ORTA. Hiçbiri → çekimser, gerekçesi kayda yazılarak. Yeni bir ağ yüzeyi bu listeye bir satır eklemektir, yeniden tasarım değil.</p>
      <p><b>Kişisel katmanı kapıya bağla.</b> Koşullu kenar, ilan edilmiş bir etki alanının dışında hiçbir kayıtlı cihazın sorgulanmadığı anlamına gelir — söz değil, fuzz testiyle doğrulanmış bir değişmez.</p>
      <p><b>Dil modelini kontrol yolundan uzak tut.</b> Tespit deterministik ve tekrar oynatılabilirdir; dil modeli yalnızca komuta merkezi cümlesini yazar.</p>
    </div>
  </div>
</section>""")

# ---------- 8 ne inşa ettik
slides.append("""
<section class="slide" id="slide-8">
  <div class="kicker">Ne inşa ettik — prototip durumu</div>
  <h2>Çalışan bir ajan; tek bir yüzey üzerinden çevrimdışı ve canlı.</h2>
  <div class="built">
    <table class="mods">
      <tr><td class="mono">world · model</td><td>10×10 ızgara, 48 kişilik isteğe bağlı kayıt defteri, deprem / hücre arızası / zirve / kronik dalgalanma olayları, bakım takvimi</td></tr>
      <tr><td class="mono">gateway</td><td>tek bir CAMARA yüzeyi, üç arka uç — simülatör, Nokia SDK üzerinden canlı, ve kaydedilmiş dökümün geri oynatımı</td></tr>
      <tr><td class="mono">detector</td><td>ilişkilendir → ayıkla → ilan et; adlandırılmış sinyaller olarak kapılar ve destekleyiciler, saf fonksiyonlar, framework import'u yok</td></tr>
      <tr><td class="mono">triage · brief</td><td>yalnızca etki alanı içinde erişilebilirlik ve son görülme; komuta merkezi cümlesi</td></tr>
      <tr><td class="mono">graph · loop</td><td>LangGraph koşucusu ve düz koşucu — aynı kanıt, bayt bayt</td></tr>
      <tr><td class="mono">shakemap · data</td><td>6 Şubat 2023 için USGS şiddet alanı, indirgenmiş ve künyesiyle commit edilmiş</td></tr>
      <tr><td class="mono">scene · console · parity</td><td>beş sahne; kanıttan üretilen kendi kendine yeten konsol; arka uç parite düzeneği</td></tr>
    </table>
    <div class="status">
      <div><b>Çıplak Python ile çalışır</b><span>hesap yok, sunucu yok, CDN yok — demo odada çökemez</span></div>
      <div><b>Aynı ajan, canlıda</b><span><code>--backend live</code> aynı üç çağrıyı Nokia SDK üzerinden yapar ve ham alışverişleri kaydeder</span></div>
      <div><b>Tek ajan, kanıtlanmış</b><span><code>python -m nabd.parity</code> — ajan yığını SDK import etmiyor, ağı tek fonksiyon seçiyor, her sahne canlı ayrıştırıcılardan birebir geri oynatılıyor</span></div>
      <div><b>Gerçek olaya karşı denetlendi</b><span>6 Şubat 2023 ShakeMap verisi bir sahneyi sürüyor; ilan edilen etki alanı, ölçülen sarsıntının tanımladığı çökme bandının içinde kalmak zorunda</span></div>
      <div><b>83 / 83 test, 10 paket</b><span>fuzz değişmezleri dahil: bitişik blok olmadan etki alanı yok; etki alanı dışında kişisel cihaz çağrısı yok</span></div>
    </div>
  </div>
</section>""")

# ---------- 9 kanıt: deprem konsolu
sig = DECL["signals"]
slides.append(f"""
<section class="slide" id="slide-9">
  <div class="kicker">Kanıt — deprem sahnesi</div>
  <h2>Sarsıntıdan 55 saniye sonra ilan. Önce ulaşılacak altı kişi.</h2>
  <div class="console">
    <div class="c-head"><span class="c-title">NABD · COMMAND CENTRE</span><span class="c-scene">scene: earthquake · pass 7 / 21 · 30 s cadence</span><span class="c-clock">09:03:00</span></div>
    <div class="c-body">
      <div class="c-map">{grid_svg(GRID_DECL, 250, labels=False, dark=True, ring=True)}</div>
      <div class="c-verdict">
        <div class="c-kind"><span class="badge">DECLARE</span><span class="conf">HIGH</span> 9 cells · ~4.0 km² · centred 37.5828N 36.9333E</div>
        <ul class="c-signals">{''.join(f'<li>{s}</li>' for s in sig)}</ul>
        <div class="c-triage"><span class="c-lbl">registry</span> 13 opted-in people inside · <b>6 unreachable</b></div>
        <table class="c-list">{''.join(person_row(p) for p in top3)}</table>
      </div>
    </div>
    <div class="c-foot"><span>declared 09:03:00 — 55 s after onset</span><span>13 inside · peak 6 unreachable</span><span>21 passes · 4,405 CAMARA calls</span><span>evidence: nabd-scene-quake.jsonl</span></div>
  </div>
  <p class="note">Ekran ürünün kendi arayüzüdür ve İngilizcedir; üzerindeki her satır kanıt kaydından yeniden çizilir.
  Sonraki geçişler: etki alanı korunur, insanlar yeniden cevap verdikçe liste 6 → 4 olur. Ekran kaydın bir görünümüdür, asla ikinci bir doğruluk kaynağı değil.</p>
</section>""")

# ---------- 10 kurt masalı anlatmaz
slides.append(f"""
<section class="slide" id="slide-10">
  <div class="kicker">Kanıt — benzer vakalar</div>
  <h2>Ajan boşa alarm vermez.</h2>
  <div class="three">
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_FAULT, 150, labels=False)}</div><div class="lbl">09:01:00 · tek hücre</div><p>“C3'te tek hücre sessizliği: bir nöbetçiye ulaşılamıyor, komşuları normal — bir hücre arızasıyla tutarlı, etkiyle değil”</p><b>ÇEKİMSER</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_MAINT, 150, labels=False)}</div><div class="lbl">09:03:00 · bakım</div><p>“4 bitişik hücre sustu, ama blok MNT-2214 bakım kaydıyla eşleşiyor — beklenen sessizlik, alarm yok”</p><b>ÇEKİMSER</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_CROWD, 150, labels=False)}</div><div class="lbl">09:05:00 · stadyum</div><p>“sessizlik olmadan tıkanıklık: 9 bitişik hücre Yüksek ama her nöbetçi cevap veriyor — kalabalık, etki değil”</p><b>ÇEKİMSER</b></div>
  </div>
  <p class="lead">Gürültü sahnesi: 21 geçiş, üç çekimser karar, <b>sıfır ilan</b> — her ret gerekçesiyle birlikte kayıtta.
  Sessiz sahne sessiz kalıyor. Yazılı gerekçeler, yanlış alarmı denetlenebilir ve doğru alarmı güvenilir kılan şeydir.</p>
</section>""")

# ---------- 11 en zor benzer vaka
slides.append(f"""
<section class="slide" id="slide-11">
  <div class="kicker">Kanıt — en zor benzer vaka</div>
  <h2>Sessizliğin normal olduğu yerde, sessizlik haber değildir.</h2>
  <div class="two">
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_HELD, 165, labels=False)}</div>
      <div class="lbl">09:05:30 · arızalı aktarım hattındaki blok</div>
      <p>Dört bitişik hücre, birlikte karanlık, bakım kaydı yok — <b>bir afetin sahip olduğu her sinyal.</b> İlk üç dalgalanma teyide alınıyor ve teyit vakti gelmeden geri dönüyorlar. Dördüncüde ajan onları ölçmüş oluyor:</p>
      <p class="quote">“sessizlik yerel taban çizgisidir: bu 4 hücre son 11 geçişin 3'ünde zaten erişilemezdi (%27) — alarm yok”</p>
      <b>ÇEKİMSER</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_BOTH, 165, labels=False, ring=True)}</div>
      <div class="lbl">09:10:30 · aynı koşu, aynı ızgara</div>
      <p>Kuzeydoğudaki blok <b>hâlâ karanlıkken</b> merkeze bir deprem vuruyor. Tek ekranda iki susan blok. Bir alarm.</p>
      <p class="quote">“etki alanı ilan edildi: 9 bitişik hücre, ~4,0 km²” — YÜKSEK, sarsıntıdan 30 sn sonra, içeride 13 kayıtlı kişi</p>
      <b>İLAN</b></div>
  </div>
  <p class="lead">Asıl soru bir kesintinin görülüp görülemeyeceği değil — bir <b>afet izinin, hücrelerin susmasının
  diğer bütün nedenlerinden ayırt edilip edilemeyeceğidir.</b> Ret varsayılmıyor, ölçülüyor; aynı koşudaki ilan da onun körlük olmadığını gösteriyor.</p>
</section>""")

# ---------- 12 gerçek olay
slides.append(f"""
<section class="slide" id="slide-12">
  <div class="kicker">Kanıt — olayın kendisi</div>
  <h2>Sonra afeti çizmeyi bıraktık.</h2>
  <div class="two">
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_MARAS_1, 165, labels=False)}</div>
      <div class="lbl">+55 sn · ilk harita</div>
      <p><b>21 bitişik hücre, ~2.100 km², YÜKSEK.</b> İsimlendirdiği her hücre, ölçülen sarsıntının çökme eşiğinin üstüne koyduğu bir hücre — uydurulmuş hasar yok. İki tanesi daha, üç hücre tabanının altındaki izole bir cep, <b>bilerek iddia edilmiyor</b>.</p>
      <b>İLAN</b></div>
    <div class="wolf"><div class="wgrid">{grid_svg(GRID_MARAS_2, 165, labels=False)}</div>
      <div class="lbl">+9 dk · ağ ölmeye devam ediyor</div>
      <p><b>63 hücre, ~6.300 km², hâlâ YÜKSEK.</b> Sarsıntıdan kurtulan direkler şebeke elektriğini kaybedip akülerini tüketti, en sert sarsılan önce. Cep de katıldı. 22 kayıtlı kişiye ulaşılamıyor, önce tıbbi bağımlılar.</p>
      <b>GÜNCELLEME ×12</b></div>
  </div>
  <p class="lead">Coğrafya ve her hücredeki şiddet, 6 Şubat 2023 tarihli <b>M7.8 Pazarcık depreminin USGS ShakeMap
  verisidir</b> — 262 sismik istasyon, 1.459 şiddet gözlemi. Bize ait olan yalnızca sarsıntıyı sessizliğe çeviren kural; iki mekanizma da saha raporlarından. Eşikler Turkcell'in <b>“yerel baz istasyonlarının yarısından fazlası devre dışı”</b> beyanına kalibre edildi — pencerimiz %63 karanlıkta bitiyor.</p>
</section>""")

# ---------- 13 CAMARA
slides.append("""
<section class="slide" id="slide-13">
  <div class="kicker">Nokia Network-as-Code üzerinde CAMARA</div>
  <h2>Ağ API'lerini çıkarın, hiçbir şey çalışmaz. Sensör ağın kendisidir.</h2>
  <div class="two apis">
    <table class="apit">
      <tr><th>API</th><th>Rolü</th><th>Prototip</th></tr>
      <tr><td class="api">Congestion Insights</td><td>tespit — nöbetçi hücre başına yük, sıcak halka</td><td class="live">canlı yol</td></tr>
      <tr><td class="api">Device Reachability Status</td><td>tespit (nöbetçiler) ve önceliklendirme (kayıt defteri)</td><td class="live">canlı yol</td></tr>
      <tr><td class="api">Location Retrieval</td><td>önceliklendirme — ulaşılamayanların son konumu</td><td class="live">canlı yol</td></tr>
      <tr><td class="api">Geofencing Subscriptions</td><td>etki alanı büyürken veya küçülürken sınır olayları</td><td class="road">yol haritası</td></tr>
      <tr><td class="api">Quality on Demand</td><td>etki alanı içindeki ekipler için öncelikli kanal</td><td class="road">yol haritası</td></tr>
    </table>
    <div class="why">
      <div class="lbl">Neden CAMARA, neden kontrol odası değil</div>
      <p>Bir operatörün NOC'u kendi hücrelerinin düştüğünü görür — tek bir operatörün içinden.</p>
      <p>Müdahale edenler — sivil savunma, Kızılay, belediyeler, hastaneler — <b>dışarıdadır</b> ve bir afetin ortasında üç ayrı operatöre giriş yapamazlar.</p>
      <p>Open Gateway <b>tek standart kapıdır</b>: operatörden bağımsızdır ve bütün ulusal operatörleri tek bir arayüz arkasında birleştirir. 2025'ten beri kararlı, bugün Network-as-Code üzerinde kullanılabilir.</p>
    </div>
  </div>
</section>""")

# ---------- 14 dürüst sınırlar
slides.append("""
<section class="slide" id="slide-14">
  <div class="kicker">Dürüst sınırlar</div>
  <h2>Olabildiği yerde canlı. Olması gerektiği yerde simüle. Tasarımdan gizli.</h2>
  <div class="three cols">
    <div class="col"><div class="lbl">Canlı ve simüle — ve aradaki dikiş</div>
      <p>Kum havuzu bir afeti sahneleyemez. Bu yüzden iki iddia ayrıldı: <b>canlı platform entegrasyonu kanıtlar</b>, gerçek kaydedilmiş çağrılarla; <b>simülatör senaryoyu kanıtlar</b>, 2023 Kahramanmaraş kesintisinin kamuya açık kaydına göre şekillenmiş.</p>
      <p>Risk simülatör değil — iki yol arasında sezilen bir kopukluktur. O yüzden <code>nabd.parity</code> bunu ölçer: ajan yığını SDK import etmez ve arka uç adı geçirmez; ağı <b>tek bir fonksiyon</b> seçer; ve her sahne <b>canlı yanıt ayrıştırıcılarından kaydedilip geri oynatılır</b>, kanıt satır satır aynı.</p></div>
    <div class="col"><div class="lbl">Gizlilik</div>
      <p>Tespit yalnızca <b>şehrin veya operatörün sahip olduğu nöbetçi cihazları</b> okur — asla halkı.</p>
      <p>Çıktısı <b>alan seviyesindedir</b>: hücreler ve bir etki alanı, insanlar değil. Kamera yok, mesaj içeriği yok, takip yok.</p></div>
    <div class="col"><div class="lbl">Rıza</div>
      <p>Önceliklendirme bir bireye ancak o kişi korunmayı <b>kendi seçmişse</b> dokunur.</p>
      <p>Kayıt defterini kurum tutar; operatör buna uyar. Kimlikler takma adlıdır ve <b>ilan edilmiş bir etki alanının dışında asla konum çağrısı yapılmaz</b>.</p></div>
  </div>
</section>""")

# ---------- 15 etki, ölçek, iş modeli
slides.append("""
<section class="slide" id="slide-15">
  <div class="kicker">Etki · ölçek · iş modeli</div>
  <h2>Tek motor, çok tehlike. Saatler değil, dakikalar.</h2>
  <div class="three cols">
    <div class="col"><div class="lbl">Etki</div>
      <p>Deprem, sel, fırtına, kitlesel kesinti — ağ için her biri kararan bir alandır, dolayısıyla tek motor hepsini kapsar.</p>
      <p>İlk sevk kararı <b>saatlerden dakikalara</b> iner ve en kırılgan olanlara önce ulaşılır.</p></div>
    <div class="col"><div class="lbl">Ölçek</div>
      <p>Nöbetçi ızgarası <b>hücre sayısıyla</b> ölçeklenir; SIM'ler belediyeye veya operatöre aittir, dolayısıyla ulusal yaygınlaştırma bir davranış değişikliği değil, bir tedarik meselesidir.</p>
      <p>Open Gateway aynı ajanı bölgedeki operatörler ve ülkeler arasında taşınabilir kılar.</p></div>
    <div class="col"><div class="lbl">İş modeli</div>
      <p><b>Alıcılar:</b> sivil savunma kurumları (AFAD), Kızılay teşkilatları, belediyeler, hastane ağları.</p>
      <p><b>Satıcı:</b> operatör, bir Open Gateway <b>etki akışı ürünü</b> olarak — ızgara için sürekli abonelik, üstüne olay başına önceliklendirme.</p></div>
  </div>
  <div class="roadmap"><span class="lbl">Yol haritası</span> NaC üzerinde yayınlandığında tespit yükseltmesi olarak Population Density Data &nbsp;·&nbsp; sınır olayları için Geofencing &nbsp;·&nbsp; etki alanı içindeki ekiplere QoD önceliği &nbsp;·&nbsp; çoklu operatör füzyonu</div>
</section>""")

# ---------- 16 kapanış
slides.append(f"""
<section class="slide cover close" id="slide-16">
  <div class="kicker">Nabd · نبض &nbsp;·&nbsp; Tema 6 &nbsp;·&nbsp; Prototip Aşaması</div>
  <h2 class="huge2">Ağ zaten biliyor.<br>Nabd ona bunu söyletiyor — ilk dakikada.</h2>
  <div class="next">
    <div><div class="lbl">Sırada</div><p>Network-as-Code cihazlarında canlı sözleşme koşusu · bir sivil savunma kurumuyla, bir şehrin nöbetçi ızgarası üzerinde pilot · yayınlandığında Population Density yükseltmesi</p></div>
    <div><div class="lbl">Ekip</div><p>Kadir Can Yıldırım — Kadir'in Ekibi, tek kişilik, Türkiye. Kod, kanıt kayıtları ve komuta merkezi konsolu gönderim bağlantılarında.</p></div>
  </div>
  <p class="doha">Doha'da görüşmek üzere — MWC Doha, Kasım 2026.</p>
  <div class="cover-grid small">{grid_svg(GRID_DECL, 220, labels=False, ring=True)}</div>
</section>""")


html = f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Nabd — Prototip Aşaması sunumu</title>
<style>{CSS}</style>
</head>
<body>
{''.join(s.replace('<section class="slide', f'<section data-n="{i+1} / {len(slides)}" class="slide', 1) for i, s in enumerate(slides))}
{SCRIPT.replace("Math.min(14,", f"Math.min({len(slides)},")}
</body>
</html>
"""

if __name__ == "__main__":
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT, len(html), "bytes", len(slides), "slides")
