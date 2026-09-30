# Sky Radar

En LED-ring på bordet som visar alla flygplan runt Uppsala just nu, och som
kan peka mot rymdstationen ISS. Byggd för Byte Me:s hackathon
[Build 4 Cyberdeck](https://luma.com/6ylas0ll) i Uppsala 2026-10-03, där
utmaningen är att bygga ett program som ryms i 4 MB (lika mycket flash som
Pico 2 W och ESP32-C3 har).

**Status 2026-09-30:** idé och plan. Ingen kod än.

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
- Knappen är zoom: 15, 40 och 80 nm, som räckviddsväljaren på en riktig
  radar. Då finns alltid ett läge där det händer något.
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
  nm) räknat från punkten vi frågar om, så Picon behöver ingen trigonometri.
  Riktning delat med 360 gånger antal lysdioder ger vilken lysdiod som tänds.
- ISS: API:et ger bara latitud och longitud, så Picon räknar ut bäringen
  från Uppsala till punkten under ISS (storcirkelformeln, `math` räcker).
- MicroPythons inbyggda `neopixel` sköter lysdioderna. Timingen görs i C och
  PIO, inte i Python.

## Plats

Lampan vet inte själv var den står. Koordinaterna ställs in en gång, precis
som norr riktas en gång. Standard är eventlokalen, ABF på S:t Persgatan 22B
i Uppsala (59.862, 17.642). Trafikmätningarna nedan gjordes från Uppsala
centrum (59.858, 17.639), ca 500 m därifrån.

- **Ingen automatisk positionering.** IP-baserad plats är för grov och blir
  fel via mobilens hotspot (operatörens IP kan ligga i en annan stad). GPS
  via mobilen är onödigt krångel för något som står still.
- **Två decimaler räcker** (ca 1 km). Radarn visar plan på mil avstånd.
- **Hemadressens koordinater hör inte hemma i repot.** När lampan flyttar
  hem: lägg platsen i en lokal konfigfil som git ignorerar och checka bara in
  ett exempel.

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
inom parentes hur många av dem som var under 10 000 fot):

| Radie | 16:08 | 16:31 |
|---|---|---|
| 15 nm (ca 28 km) | - | 4 (4) |
| 25 nm (ca 46 km) | 4 (3) | 7 (7) |
| 40 nm (ca 74 km) | 7 (3) | 15 (10) |
| 60 nm (ca 110 km) | 10 (3) | 18 (11) |

Trafiken svänger mycket på en halvtimme. Vid rusning klumpar sig planen i
sektorn mot Arlanda (ca 100-190 grader), så då är 15 nm rätt zoom. När det
är lugnt (lördag, kväll) är 40-80 nm bättre. Därav zoomknappen. Svaret är
5-10 KB beroende på antal plan.

**Fällor i riktig data** (sett 2026-09-30), som Pico-koden måste hantera:

- **Plan på marken** har `alt_baro: "ground"` (till exempel parkerade plan
  på Bromma). Visa inte, eller visa mycket svagt.
- **`alt_baro` kan vara negativ** för plan i luften. Det är tryckhöjd, som
  blir fel vid högtryck (ett plan på inflygning till Arlanda visade -250 fot
  men `alt_geom` 450 fot och 128 knop). Använd `alt_geom` först.
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
LAT=59.86 LON=17.64 RADIE_NM=15 ./scripts/kolla-api.sh
```

## Hårdvara

Grundplanen kräver ingen lödning.

- **Pico 2 W med förlödda stift.** Arrangörerna tar med 12 stycken.
- **Adresserbara RGB-lysdioder** (WS2812), arrangörernas. Är det en slinga:
  tejpa den i en cirkel på en kartong, den blir större och tydligare än en
  ring.
- **En knapp** för zoom och lägesbyte (valfri).
- **Mobilen som hotspot** om lokalens WiFi är eduroam eller har
  inloggningssida. Pico 2 W klarar bara 2,4 GHz: Settings > Network &
  internet > Hotspot & tethering > Wi-Fi hotspot > Speed & compatibility >
  2.4 GHz, säkerhet WPA2-Personal.

**Koppling:** tre sladdar. 5V (VBUS), GND och data till valfri GPIO.

**Ström:** 24 lysdioder på fullt vitt drar ca 1,4 A, USB ger ca 0,5 A.
Begränsa ljusstyrkan till ca 20 % i koden.

**Egen ring (valfritt):** WS2812 5050 med 24 lysdioder och 66 mm diameter
kostar runt 128 kr. Den kommer med lödpunkter utan sladdar, så den kräver
lödning. Texten "endast för AVR" i sådana annonser är kopierad från
Adafruit och gäller inte Pico.

**Presentation:**

- Bakplåtspapper eller ett frostat plastlock över lysdioderna gör att de
  glöder mjukt i stället för att blända.
- En utskriven kompassros under ringen med N/Ö/S/V samt Arlanda, Stockholm
  och Gävle utmärkta gör att folk förstår prickarna direkt.
- Rikta norr en gång med mobilens kompass.

## Robusthet

- Hämta radardata var 3-5 sekund och ISS var 10:e sekund, långt under
  gränserna.
- Reserv-URL:er i koden. Svarar inte förstavalet byter Picon källa.
- **Inspelat läge:** spara några minuter riktig trafik i flash (några tiotals
  kB). Dör nätet i lokalen spelar lampan upp inspelningen, så demon lever.
- Reserv om all hårdvara strular: terminalprototypen på laptopskärmen är i
  sig en demo.

## Plan

1. **Terminalprototyp** på laptopen: Python som ritar en ASCII-ring live,
   med radarläge, ISS-läge, zoom, reserv-URL:er och inspelat läge. Skriven
   så att logiken kan flyttas rakt in i MicroPython.
2. **Före lördag, om hårdvara finns:** testa WiFi, HTTPS och LED på en Pico.
   Mät hur lång tid TLS-handskakningen tar på Picon.
3. **Lördag:** flytta logiken till Picon, koppla in lysdioderna, bygg
   kompassrosen, visa upp.

## Öppna frågor

Skickade till arrangörerna 2026-09-30:

- Är lysdioderna slingor eller ringar, och har de sladdar eller kontakter?
- Har Picorna förlödda stift?
- Vilket WiFi finns i lokalen, vanligt lösenord eller eduroam?
- Räknas det i 4 MB-utmaningen om programmet hämtar data från nätet?

Om svaren inte kommer i tid: bygg med det som finns på plats.

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
