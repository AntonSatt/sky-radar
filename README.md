# Sky Radar

En LED-ring på bordet som visar alla flygplan runt Uppsala just nu, och som
kan peka mot rymdstationen ISS. Byggd för Byte Me:s hackathon
[Build 4 Cyberdeck](https://luma.com/6ylas0ll) i Uppsala 2026-10-03, där
utmaningen är att bygga ett program som ryms i 4 MB (lika mycket flash som
Pico 2 W och ESP32-C3 har).

**Status 2026-10-03:** radarn går på en ESP32-C3-Zero med en 24-ring på
hackathonet: WiFi, hämtning i egen tråd, ringen och BOOT-knappen för zoom
och läge. Kärnan och terminalprototypen är testade på både CPython och
MicroPython.

## Idén

Picon är hjärnan i något fysiskt som är kopplat till något mycket större:
all flygtrafik runt Arlanda. Den som aldrig har programmerat ska fatta
grejen på fem sekunder.

**Radarläge**

- Ringen är en kompass. Varje plan inom räckvidd blir en prick i den
  riktning planet faktiskt är.
- Färgen visar höjd: rött är lågt (på väg in till eller ut från Arlanda),
  blått är marschhöjd.
- Ett svep går runt ringen som på en riktig radar.
- Knappen är zoom: 25, 50 och 75 km, som räckviddsväljaren på en riktig
  radar. Då finns alltid ett läge där det händer något. 150 km fick inte
  plats i minnet på ESP32-C3 när skärmen också används.
- Allt visas i km och meter. Flyget räknar i nautiska mil och fot, men det
  säger inte publiken något.
- Publiken kan kontrollera själv med Flightradar24 på mobilen.

**ISS-läge**

- Ringen pekar mot rymdstationen, som varvar jorden på ca 90 minuter. Under
  en eftermiddag syns den vandra runt ringen.
- När den passerar över Sverige blinkar hela ringen.

## Så funkar det

```
adsb.fi (flygplan)  --HTTPS-->  Pico 2 W      --data-->  LED-ring
wheretheiss.at (ISS) --HTTPS--> (MicroPython)
                                    ^
                                knapp: zoom / läge
```

- Radarn: API:et svarar med riktning (`dir`, grader) och avstånd (`dst`,
  nautiska mil) räknat från punkten vi frågar om, så Picon behöver ingen
  trigonometri. Riktning delat med 360 gånger antal lysdioder ger vilken
  lysdiod som tänds.
- Enheter: nautiska mil och fot från API:et blir km och meter direkt när
  datan kommer in (`slim_aircraft`). Bara radien i själva anropet är kvar i
  nautiska mil (1 nm = 1,852 km), eftersom API:et kräver det.
- ISS: API:et ger bara latitud och longitud, så Picon räknar ut bäringen
  från Uppsala till punkten under ISS (storcirkelformeln, `math` räcker).
- MicroPythons inbyggda `neopixel` sköter lysdioderna. Timingen görs i C och
  PIO, inte i Python.

## Kod

```
pico/core.py          all logik, körs oförändrad på laptop och mikrokontroller
pico/config.py        plats, stift, antal lysdioder, zoom, datakällor
pico/main.py          skalet på kortet: WiFi, hämtning, lysdioder, skärm, ratt
pico/oled.py          drivrutin för 128x64-skärmen (SSD1306 eller SH1106)
pico/boards/          en profil per kort: ring.py (ring + skärm), matris.py
terminal/radar.py     prototyp: ringen och 8x8-matrisen ritade i terminalen
tests/test_core.py    tester, körs med både python3 och micropython
scripts/kolla-api.sh  kollar att datakällorna svarar
scripts/till-kortet.sh  lägger koden på kortet och kör den (profil som argument)
scripts/wifi.sh       lägger till ett WiFi-nät, korten tar det första som syns
```

Det som ska till mikrokontrollern är `pico/`. Terminalen är ett testverktyg
och en reservdemo.

Till kortet (MicroPython måste finnas på det, se nedan):

```bash
./scripts/till-kortet.sh   # frågar efter WiFi första gången, Ctrl-C stoppar
```

WiFi-uppgifterna hamnar i `pico/secrets.py`, som git ignorerar. `main.py`
ligger kvar på kortet och startar själv när kortet får ström. Hämtningen går
i en egen tråd, eftersom TLS tar ca 2 s per anrop på C3:an och ringen annars
står still under tiden.

MicroPython på en ESP32-C3 (firmware från micropython.org/download,
`ESP32_GENERIC_C3`, testat med 1.29.0):

```bash
FIRMWARE=~/Downloads/ESP32_GENERIC_C3-20260824-v1.29.0.bin
esptool --chip esp32c3 erase-flash
esptool --chip esp32c3 write-flash 0 "$FIRMWARE"
```

Koppling på ESP32-C3-Zero: ringens DI till GPIO3, 5V till 5V, GND till GND.
OLED-modulen med ratt: VCC till 3V3 (inte 5V), GND, SDA till GPIO4, SCL till
GPIO5, PSH till GPIO6, TRA till GPIO7, TRB till GPIO0, BAK till GPIO1 och
CON till GPIO2. Skärmen är en SH1106.

Matrisenheten är en egen ESP32-C3 SuperMini som sitter fastlödd på en
8x8-matris (DIN på GPIO4) och kör samma kod: `./scripts/till-kortet.sh matris`.
Korten klarar bara 2,4 GHz, så en mobil-hotspot måste stå på 2,4 GHz.

Kör prototypen (bara Pythons standardbibliotek behövs):

```bash
./terminal/radar.py                                     # live: z = zoom, m = läge, q = avsluta
./terminal/radar.py --record inspelningar/lordag.jsonl  # spela in samtidigt
./terminal/radar.py --replay inspelningar/lordag.jsonl  # spela upp utan nät
./terminal/radar.py --once --mode iss                   # en bild, sedan avsluta
```

Kör testerna:

```bash
python3 tests/test_core.py
micropython tests/test_core.py
```

Kärnan är testad på MicroPython 1.30 (unix-porten): alla tester går igenom,
och ett riktigt API-svar för 150 km (15,5 KB, 23 plan) går att tolka med bara
128 KB heap. Pico 2 W har 520 KB RAM.

Inspelningar är JSON-rader med `t`, `km`, `ac` och `iss`, och git ignorerar
dem. Samma format kan läggas i flash som reserv.

## Plats

Lampan vet inte själv var den står. Koordinaterna ställs in en gång, precis
som norr riktas en gång. Standard är eventlokalen, ABF på S:t Persgatan 22B
i Uppsala (59.8621567, 17.6421569). Trafikmätningarna nedan gjordes från
Uppsala centrum (59.858, 17.639), ca 500 m därifrån.

Byt plats utan att räkna fram koordinater själv:

```bash
./terminal/radar.py --plats                                # frågar var du är
./terminal/radar.py --plats "Stockholms centralstation"
./terminal/plats.py "Uppsala domkyrka"                     # bara koordinaterna
```

`plats.py` slår upp adressen hos OpenStreetMap (Nominatim) och skriver ut
en rad som `LAT=59.8603 LON=17.6337`, som går att klistra in framför andra
kommandon, till exempel `./scripts/kolla-api.sh`. Utan terminal: högerklicka
på platsen i Google Maps, så står koordinaterna överst i menyn och kopieras
med ett klick.

- **Ingen automatisk positionering.** IP-baserad plats är för grov och blir
  fel via mobilens hotspot (operatörens IP kan ligga i en annan stad). GPS
  via mobilen är onödigt krångel för något som står still.
- **Full precision** (7 decimaler, ca 1 cm) från OpenStreetMap, ingen
  avrundning.
- **Hemadressens koordinater hör inte hemma i repot.** När lampan flyttar
  hem: lägg `LAT` och `LON` i `pico/config_local.py`, som git ignorerar och
  som skriver över `config.py`.

## Datakällor

Gratis, ingen API-nyckel. Alla testade 2026-09-30 och alla tar TLS 1.2 (det
Picons TLS klarar).

| Tjänst | Används till | Svar vid test | Villkor |
|---|---|---|---|
| [adsb.fi opendata](https://github.com/adsbfi/opendata) | Radar, förstaval | 5-10 KB, 0,13 s | Personligt och icke-kommersiellt, max 1 anrop/s, kreditera adsb.fi med länk |
| api.adsb.lol | Radar, reserv | 5-10 KB, 0,2-4 s | Samma format (`ac`, `dir`, `dst`), byt bara URL |
| [wheretheiss.at](https://wheretheiss.at/w/developer) | ISS, förstaval | 308 byte, 1,6 s | Max 350 anrop per 5 min |
| open-notify | ISS, reserv | 0,4 s | Vanlig http |

Villkoret om kreditering löses med en lapp bredvid lampan: "Flygdata: adsb.fi".

**Hur mycket trafik?** Mätt runt Uppsala centrum en onsdag (antal plan,
inom parentes hur många av dem som var under 3 000 m). Radierna är de
nautiska mil vi frågade API:et om:

| Radie | 16:08 | 16:31 |
|---|---|---|
| 28 km (15 nm) | - | 4 (4) |
| 46 km (25 nm) | 4 (3) | 7 (7) |
| 74 km (40 nm) | 7 (3) | 15 (10) |
| 111 km (60 nm) | 10 (3) | 18 (11) |

Trafiken svänger mycket på en halvtimme. Vid rusning klumpar sig planen i
sektorn mot Arlanda (ca 100-190 grader), så då är 25 km rätt zoom. När det
är lugnt (lördag, kväll) är 75-150 km bättre. Därav zoomknappen. Svaret är
5-10 KB beroende på antal plan.

**Fällor i riktig data** (sett 2026-09-30), som Pico-koden måste hantera:

- **Plan på marken** har `alt_baro: "ground"` (till exempel parkerade plan
  på Bromma). Visa inte, eller visa mycket svagt.
- **`alt_baro` kan vara negativ** för plan i luften. Det är tryckhöjd, som
  blir fel vid högtryck (ett plan på inflygning till Arlanda visade -250 fot
  men `alt_geom` 450 fot, ca 140 m, och 128 knop). Använd `alt_geom` först.
- **Anropssignalen kan saknas** eller vara `@@@@@@@@`.
- **Reserven kan också ligga nere.** adsb.lol gav timeout i 10 s en gång och
  svarade igen några minuter senare. Picon ska ha kort timeout (ca 5 s) och
  fortsätta visa senast kända plan, som bleknar om datan blir gammal, i
  stället för att frysa.

Kolla att allt svarar (till exempel på lördag morgon innan avfärd):

```bash
./scripts/kolla-api.sh
```

Plats och radie går att ändra per körning:

```bash
LAT=59.8603 LON=17.6337 RADIE_KM=25 ./scripts/kolla-api.sh
```

## Hårdvara

Svar från arrangörerna 2026-09-30:

- **Lysdioder:** en slinga, många stora ringar, några små och en 8x8-matris.
  Antalet ställs in med `N_LEDS` i `pico/config.py`. Matrisen kan visa en
  riktig 2D-radar (`radar_grid` i kärnan).
- **Picorna har inte förlödda stift,** men det finns korta stiftlister som
  passar ESP32-C3. Kärnan är ren Python och fungerar på båda korten.
- **WiFi:** en ABF-lokal, troligen inte eduroam. De tar kanske med mobilt
  WiFi.
- **Molndata är ok:** "Man får nog göra vad man vill så länge man gör något!"

Lödning blir alltså troligen aktuellt på plats: stiftlist på kortet och tre
sladdar på ringen. Det är ett klassiskt första lödjobb.

**WiFi-reserv:** mobilen som hotspot om lokalens WiFi har inloggningssida.
Korten klarar bara 2,4 GHz: Settings > Network & internet > Hotspot &
tethering > Wi-Fi hotspot > Speed & compatibility > 2.4 GHz, säkerhet
WPA2-Personal.

**Koppling:** tre sladdar. 5V (VBUS), GND och data till valfri GPIO. En knapp
för zoom och lägesbyte är valfri.

**Inställningar på plats** (`pico/config.py`): `N_LEDS` efter ringens storlek,
`LED_NORTH` för lysdioden som pekar mot norr och `CLOCKWISE` för vilket håll
numren går. För matrisen `GRID_SERPENTINE` om den är kopplad i sicksack.

**Ström:** 24 lysdioder på fullt vitt drar ca 1,4 A, USB ger ca 0,5 A.
Begränsa ljusstyrkan med `MAX_BRIGHTNESS` (0,2 som standard).

**Presentation:**

- Bakplåtspapper eller ett frostat plastlock över lysdioderna gör att de
  glöder mjukt i stället för att blända.
- En utskriven kompassros under ringen med N/Ö/S/V samt Arlanda, Stockholm
  och Gävle utmärkta gör att folk förstår prickarna direkt.
- Rikta norr en gång med mobilens kompass.

## Robusthet

- Hämta radardata var 4:e sekund och ISS var 10:e sekund, långt under
  gränserna.
- Reserv-URL:er. Svarar inte förstavalet byter kortet källa.
- Hämtningen får aldrig frysa animationen. Gammal data bleknar och svepet
  blir rött, så det syns när nätet strular.
- **Inspelat läge:** spela in några minuter riktig trafik (`--record`). Dör
  nätet i lokalen spelar lampan upp inspelningen, så demon lever.
- Reserv om all hårdvara strular: terminalprototypen på laptopskärmen är i
  sig en demo.

## Plan

1. **Klart 2026-09-30:** kärnan, konfigurationen, tester och
   terminalprototypen.
2. **Före lördag (valfritt):** spela in lite trafik som reserv.
3. **Lördag:** löd stiftlist och sladdar, skriv skalet på kortet (WiFi,
   hämtning, `neopixel`, knapp), ställ in ringen i `config.py`, bygg
   kompassrosen och visa upp.

## Fler rymdlägen (idéer)

Alla gratis och kontrollerade 2026-09-30:

- **ISS i sol eller skugga:** redan med. Ringen är vit när ISS är i solljus
  och blå i jordens skugga (`visibility` från wheretheiss.at).
- **Hur många som är i rymden just nu:** `http://api.open-notify.org/astros.json`
  (12 personer på ISS och Tiangong). En lysdiod per person.
- **Norrskensläge:** NOAA:s Kp-index,
  `https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json`
  (4,6 KB). Grön glöd när det finns chans till norrsken över Uppsala, grovt
  från Kp 4-5.

## Parkerade idéer

Idéer som vägdes mot varandra innan Sky Radar valdes.

- **Hemliga regeln (Jev):** maskinen har en hemlig regel ("handlar om något
  man kan äta"). Man skriver vad som helst, ringen lyser grönt eller rött med
  ljusstyrka efter sannolikhet, och man ska lista ut regeln. Bästa idén för
  TypeSafes Jev (typade beslut på ca 100 ms, sannolikheter, max 255 val per
  fråga). Parkerad för att den är mindre fysisk och bygger på en molnmodell.
- **Gissa ordet (Jev):** beskriv ett hemligt ord, Jev gissar bland 255 ord,
  ringen visar hur varmt det är.
- **Pong mot Jev:** nej. En perfekt pong-AI är en if-sats, Jev är dålig på
  siffror och har 70-500 ms latens.
- **Chaos-knappen:** fysisk chaos engineering mot ett Kubernetes-kluster.
  För nördig för publiken.
- **Världens minsta AI:** llama2.c med stories260K (ca 1 MB) på en Pico 2,
  det finns en port för RP2040. Mest ett partytrick.
- **LED-pong, Smittan (ESP-NOW-svärm med lysdioder), stämningslampa:**
  roliga men antingen tunna eller logistiskt tunga.
