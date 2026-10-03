"""Skalet på kortet: WiFi, hämtning, lysdioder och knapp.

All logik bor i core.py. Den här filen är det enda som rör hårdvaran och
körs bara på mikrokontrollern (MicroPython). WiFi-uppgifterna ligger i
secrets.py bredvid, som git ignorerar:

    WIFI_NETWORKS = [("namn", "lösenord"), ...]   # i prioritetsordning

Lägg till ett nät med ./scripts/wifi.sh.

Till kortet och kör: ./scripts/till-kortet.sh
"""

import gc
import time

import machine
import neopixel
import network

try:
    import requests
except ImportError:
    import urequests as requests

import config
import core

try:
    import secrets
except ImportError:
    secrets = None

try:
    import _thread
except ImportError:
    _thread = None

USER_AGENT = "sky-radar/0.1 (hackathon)"
FRAME_MS = 33
LONG_PRESS_MS = 700
WIFI_RETRY_MS = 10000
MIN_RADAR_GAP_MS = 1100   # adsb.fi tillåter max 1 anrop per sekund
# TLS-handskakningen tar 1,5-2 s på C3:an och behöver mer stack än en tråds
# standard (ca 4 KB). Huvudtrådens stack på ESP32 är 16 KB.
FETCH_STACK = 16 * 1024

STATUS_FRESH = (0, 20, 0)
STATUS_STALE = (30, 0, 0)
STATUS_WIFI = (0, 0, 30)


# --- Lysdioder -------------------------------------------------------------

class Ring:
    """Kortets lysdioder: ringen, matrisen och statuslysdioden. Alla tre är
    valfria, kortets profil i pico/boards/ säger vilka som finns."""

    def __init__(self):
        self.np = None
        if config.LED_PIN is not None:
            self.np = neopixel.NeoPixel(machine.Pin(config.LED_PIN), config.N_LEDS)
        self.status = None
        if config.STATUS_LED_PIN is not None:
            self.status = neopixel.NeoPixel(machine.Pin(config.STATUS_LED_PIN), 1)
        self.grid = None
        if config.GRID_PIN is not None:
            self.grid = neopixel.NeoPixel(machine.Pin(config.GRID_PIN),
                                          config.GRID_W * config.GRID_H)

    def show(self, frame):
        if self.np is None:
            return
        for i, color in enumerate(frame):
            self.np[i] = core.scale(color, config.MAX_BRIGHTNESS)
        self.np.write()

    def show_grid(self, pixels):
        if self.grid is None:
            return
        for i, color in enumerate(pixels):
            self.grid[i] = core.scale(color, config.MAX_BRIGHTNESS)
        self.grid.write()

    def set_status(self, color):
        if self.status is not None:
            self.status[0] = color
            self.status.write()

    def boot(self):
        """Ringen: en prick går ett varv från norr och visar vilken lysdiod
        som är LED_NORTH och åt vilket håll numren går. Matrisen: en prick går
        igenom alla pixlar i kopplingsordning från pixel 0 (vit), så att det
        syns var hörnet sitter och om raderna går i sicksack."""
        if self.np is not None:
            n = config.N_LEDS
            for step in range(n + 1):
                frame = [core.BLACK] * n
                i = core.led_index(step * 360 / n, n, config.LED_NORTH, config.CLOCKWISE)
                frame[i] = (0, 255, 120)
                frame[config.LED_NORTH] = (255, 255, 255)
                self.show(frame)
                time.sleep_ms(40)
            self.show([core.BLACK] * n)
        if self.grid is not None:
            size = config.GRID_W * config.GRID_H
            for i in range(1, size):
                pixels = [core.BLACK] * size
                pixels[0] = (255, 255, 255)
                pixels[i] = (0, 255, 120)
                self.show_grid(pixels)
                time.sleep_ms(30)
            self.show_grid([core.BLACK] * size)

    def waiting(self, step):
        """Blått som snurrar medan WiFi ansluter."""
        if self.np is not None:
            n = config.N_LEDS
            frame = [core.BLACK] * n
            frame[step % n] = (0, 60, 255)
            self.show(frame)
        if self.grid is not None:
            sweep = (step * 30) % 360
            pixels = core.radar_grid([], config.GRID_W, config.GRID_H, 1, 0,
                                     config.GRID_SERPENTINE, sweep)
            self.show_grid([(0, c[1] // 2, c[1] * 4) for c in pixels])


# --- Nät -------------------------------------------------------------------

def known_networks():
    """Kända nät i prioritetsordning ur secrets.py: WIFI_NETWORKS först,
    sedan det äldre formatet med ett enda nät."""
    if secrets is None:
        return []
    nets = list(getattr(secrets, "WIFI_NETWORKS", ()))
    if hasattr(secrets, "WIFI_SSID"):
        nets.append((secrets.WIFI_SSID, secrets.WIFI_PASSWORD))
    return nets


class Wifi:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        # WiFi-drivern överlever en mjuk omstart. Har en avbruten körning
        # lämnat den mitt i en anslutning ger connect() "Wifi Internal State
        # Error", så börja alltid från avslaget läge.
        self.wlan.active(False)
        time.sleep_ms(100)
        self.wlan.active(True)
        if config.WIFI_TXPOWER:
            self.wlan.config(txpower=config.WIFI_TXPOWER)
        self.tried_at = None
        self.net = None

    def pick(self):
        """Det första kända nätet som syns just nu, annars det första i listan."""
        nets = known_networks()
        if len(nets) > 1:
            try:
                seen = set(r[0].decode() for r in self.wlan.scan())
            except OSError:
                seen = set()
            for net in nets:
                if net[0] in seen:
                    return net
        return nets[0] if nets else None

    def connected(self):
        return self.wlan.isconnected()

    def connect(self, ring, wait_ms=20000):
        """Försök ansluta och snurra blått på ringen medan vi väntar."""
        self.net = self.pick()
        if self.net is None:
            print("secrets.py saknas eller är tom på kortet, kör utan nät")
            return False
        print("WiFi: ansluter till", self.net[0])
        self.wlan.connect(self.net[0], self.net[1])
        self.tried_at = time.ticks_ms()
        ring.set_status(STATUS_WIFI)
        step = 0
        while not self.wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), self.tried_at) > wait_ms:
                print("WiFi: ingen anslutning, status", self.wlan.status())
                return False
            ring.waiting(step)
            step += 1
            time.sleep_ms(60)
        print("WiFi: ansluten,", self.wlan.ifconfig()[0])
        return True

    def retry_if_needed(self):
        """Ny anslutning i bakgrunden om nätet har gått ner. Blockerar inte."""
        if self.connected() or not known_networks():
            return
        now = time.ticks_ms()
        if self.tried_at is None or time.ticks_diff(now, self.tried_at) > WIFI_RETRY_MS:
            self.tried_at = now
            try:
                self.wlan.disconnect()
                self.net = self.pick()
                print("WiFi: nere, försöker med", self.net[0])
                self.wlan.connect(self.net[0], self.net[1])
            except OSError as exc:
                print("WiFi:", exc)


def fetch_json(url):
    gc.collect()
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.TIMEOUT_S)
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        return r.json()
    finally:
        r.close()


class Feed:
    """Senast kända data. Källan som svarade sist provas först nästa gång,
    så att en död förstakälla inte kostar en timeout varje varv."""

    def __init__(self, mode, zoom_km):
        # Skrivs av huvudslingan (knappen), läses av hämtningen
        self.mode = mode
        self.zoom_km = zoom_km
        self.wake = True
        # Skrivs av hämtningen, läses av huvudslingan. Hela listor byts ut,
        # så huvudslingan ser aldrig en halvfärdig.
        self.planes = []
        self.radar_at = None
        self.radar_called = None
        self.radar_first = 0
        self.iss = None
        self.iss_at = None
        self.iss_first = 0
        self.next_radar = self.next_iss = time.ticks_ms()

    def _first(self, urls, start):
        error = None
        for k in range(len(urls)):
            i = (start + k) % len(urls)
            try:
                return fetch_json(urls[i]), i
            except Exception as exc:  # noqa: BLE001
                print("  fel från", urls[i].split("/")[2], repr(exc))
                error = exc
        raise error

    def fetch_radar(self, zoom_km):
        now = time.ticks_ms()
        if self.radar_called is not None and time.ticks_diff(now, self.radar_called) < MIN_RADAR_GAP_MS:
            return
        self.radar_called = now
        nm = core.api_radius_nm(zoom_km)
        urls = [u.format(lat=config.LAT, lon=config.LON, nm=nm) for u in config.RADAR_URLS]
        try:
            data, self.radar_first = self._first(urls, self.radar_first)
        except Exception:  # noqa: BLE001
            return
        self.planes = core.slim_response(data)
        del data
        gc.collect()
        self.radar_at = time.ticks_ms()
        took = time.ticks_diff(self.radar_at, now)
        print("radar {} km: {} plan, {} ms, {} byte ledigt".format(
            zoom_km, len(self.planes), took, gc.mem_free()))

    def fetch_iss(self):
        try:
            data, self.iss_first = self._first(config.ISS_URLS, self.iss_first)
        except Exception:  # noqa: BLE001
            return
        self.iss = core.parse_iss(data)
        self.iss_at = time.ticks_ms()
        print("ISS:", self.iss)

    def step(self, wifi):
        """Hämta det som är dags för nuvarande läge. Blockerar under hämtningen."""
        wifi.retry_if_needed()
        if not wifi.connected():
            return
        now = time.ticks_ms()
        if self.wake:
            self.wake = False
            self.next_radar = self.next_iss = now
        if self.mode == "radar" and time.ticks_diff(now, self.next_radar) >= 0:
            self.fetch_radar(self.zoom_km)
            self.next_radar = time.ticks_add(time.ticks_ms(), config.RADAR_EVERY_S * 1000)
        elif self.mode == "iss" and time.ticks_diff(now, self.next_iss) >= 0:
            self.fetch_iss()
            self.next_iss = time.ticks_add(time.ticks_ms(), config.ISS_EVERY_S * 1000)

    def run_forever(self, wifi):
        while True:
            try:
                self.step(wifi)
            except Exception as exc:  # noqa: BLE001
                print("hämtning:", repr(exc))
            time.sleep_ms(100)

    def start_thread(self, wifi):
        """Hämta i en egen tråd så att svepet aldrig stannar. False om det
        inte gick, då hämtar huvudslingan själv mellan bilderna."""
        if _thread is None:
            return False
        try:
            _thread.stack_size(FETCH_STACK)
            _thread.start_new_thread(self.run_forever, (wifi,))
        except Exception as exc:  # noqa: BLE001
            print("ingen hämtningstråd:", repr(exc))
            return False
        return True


def age_s(at, now):
    if at is None:
        return None
    return time.ticks_diff(now, at) / 1000


# --- Decket: skärm och ratt -----------------------------------------------

class Encoder:
    """Vridratt med två faser. Avbrott på båda kanterna och en tabell över
    giltiga övergångar, så att kontaktstuds tar ut sig själv."""

    _TABLE = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)

    def __init__(self, pin_a, pin_b):
        self.a = machine.Pin(pin_a, machine.Pin.IN, machine.Pin.PULL_UP)
        self.b = machine.Pin(pin_b, machine.Pin.IN, machine.Pin.PULL_UP)
        self.state = (self.a.value() << 1) | self.b.value()
        self.quarters = 0
        edges = machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING
        self.a.irq(self._edge, edges)
        self.b.irq(self._edge, edges)

    def _edge(self, _pin):
        state = (self.a.value() << 1) | self.b.value()
        self.quarters += self._TABLE[(self.state << 2) | state]
        self.state = state

    def clicks(self):
        """Hela klick sedan förra anropet, positivt medurs."""
        n = int(self.quarters / config.ENC_STEPS)
        self.quarters -= n * config.ENC_STEPS
        return n


class Deck:
    """OLED-skärmen. Ritas om fem gånger per sekund: en hel bild tar ca
    25 ms över I2C, oftare än så får ringens animation att hacka."""

    REDRAW_MS = 200

    def __init__(self):
        self.oled = None
        self.failed = False
        self.log_lines = []
        self.drawn_at = None
        if config.OLED_SDA is None:
            return
        try:
            import oled
            i2c = machine.I2C(0, sda=machine.Pin(config.OLED_SDA),
                              scl=machine.Pin(config.OLED_SCL), freq=400000)
            found = i2c.scan()
            print("I2C hittade:", [hex(a) for a in found])
            if not found:
                print("skärm: inget svar på I2C, kolla SDA, SCL, VCC och GND")
                return
            address = oled.ADDRESS if oled.ADDRESS in found else found[0]
            self.oled = oled.OLED(i2c, config.OLED_KIND, address=address)
        except Exception as exc:  # noqa: BLE001
            print("skärm:", repr(exc))
            self.oled = None

    def draw(self, lines):
        """Rita raderna. Ett glapp i I2C-sladdarna får aldrig stoppa
        ringen: felet skrivs ut en gång, och skärmen startas om när den
        svarar igen."""
        o = self.oled
        if o is None:
            return
        o.fill(0)
        o.fill_rect(0, 0, o.width, 8, 1)
        o.text(lines[0], 0, 0, 0)
        for row in range(1, min(len(lines), 8)):
            o.text(lines[row], 0, row * 8, 1)
        try:
            if self.failed:
                o.init()
            o.show()
            if self.failed:
                print("skärm: tillbaka")
            self.failed = False
        except OSError as exc:
            if not self.failed:
                print("skärm: tappade kontakten,", repr(exc))
            self.failed = True

    def log(self, line):
        """Uppstartsloggen: rader som rullar fram som i en terminal."""
        print("deck:", line)
        if self.oled is None:
            return
        self.log_lines = (self.log_lines + [line])[-7:]
        self.draw(["SKY DECK  BOOT"] + self.log_lines)

    def update(self, lines, now):
        if self.oled is None:
            return
        if self.drawn_at is not None and time.ticks_diff(now, self.drawn_at) < self.REDRAW_MS:
            return
        self.drawn_at = now
        self.draw(lines)


def optional_button(pin):
    return Button(pin) if pin is not None else None


# --- Knapp -----------------------------------------------------------------

class Button:
    """Aktivt låg knapp. Returnerar "short" eller "long" när den släpps."""

    def __init__(self, pin):
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.down_at = None

    def poll(self):
        pressed = self.pin.value() == 0
        now = time.ticks_ms()
        if pressed and self.down_at is None:
            self.down_at = now
        elif not pressed and self.down_at is not None:
            held = time.ticks_diff(now, self.down_at)
            self.down_at = None
            if held > 30:
                return "long" if held >= LONG_PRESS_MS else "short"
        return None


# --- Huvudslingan ----------------------------------------------------------

def main():
    deck = Deck()
    deck.log("> INIT")
    ring = Ring()
    ring.boot()
    deck.log("> RING   %s" % ("OK" if ring.np is not None else "--"))
    deck.log("> GRID   %s" % ("OK" if ring.grid is not None else "--"))
    deck.log("> LINK   ...")
    wifi = Wifi()
    deck.log("> LINK   %s" % ("OK" if wifi.connect(ring) else "FAIL"))

    boot_button = optional_button(config.BUTTON_PIN)
    push = optional_button(config.ENC_PUSH_PIN)
    back = optional_button(config.BACK_PIN)
    confirm = optional_button(config.CONFIRM_PIN)
    knob = None
    if config.ENC_A is not None and config.ENC_B is not None:
        knob = Encoder(config.ENC_A, config.ENC_B)

    zoom = len(config.ZOOM_KM) - 1   # störst räckvidd först, flest plan
    feed = Feed("radar", config.ZOOM_KM[zoom])
    threaded = feed.start_thread(wifi)
    deck.log("> SCAN   ADS-B")
    n = config.N_LEDS
    target = 0          # valt plan bland dem inom räckvidd, närmast först
    target_signal = None
    print("Sky Radar igång: läge", feed.mode, feed.zoom_km, "km,",
          "hämtar i egen tråd" if threaded else "hämtar mellan bilderna")

    while True:
        presses = [b.poll() if b else None for b in (boot_button, push, back, confirm)]
        if presses[0] == "short" or presses[1]:
            zoom = (zoom + 1) % len(config.ZOOM_KM)
            feed.zoom_km = config.ZOOM_KM[zoom]
            feed.wake = True
            print("zoom", feed.zoom_km, "km")
        if presses[0] == "long" or presses[2]:
            feed.mode = "iss" if feed.mode == "radar" else "radar"
            feed.wake = True
            print("läge", feed.mode)
        if presses[3]:
            print("CONFIRM")

        # Valt plan följer anropssignalen, inte platsen i listan, eftersom
        # listan sorteras om efter avstånd vid varje hämtning.
        inside = [p for p in feed.planes if p[2] <= feed.zoom_km]
        clicks = knob.clicks() if knob else 0
        if inside:
            if clicks:
                target = (target + clicks) % len(inside)
                print("mål %d/%d %s" % (target + 1, len(inside), inside[target][0]))
            else:
                signals = [p[0] for p in inside]
                if target_signal in signals:
                    target = signals.index(target_signal)
                else:
                    target = min(target, len(inside) - 1)
            target_signal = inside[target][0]

        now = time.ticks_ms()
        t = now / 1000
        if feed.mode == "radar":
            age = age_s(feed.radar_at, now)
            sweep = (t * core.SWEEP_DEG_PER_S) % 360
            frame = core.radar_frame(feed.planes, n, feed.zoom_km, sweep, age,
                                     config.LED_NORTH, config.CLOCKWISE)
            # Det valda planet blinkar vitt på ringen
            if deck.oled is not None and inside and (now // 250) % 2 == 0:
                i = core.led_index(inside[target][1], n, config.LED_NORTH, config.CLOCKWISE)
                frame[i] = (255, 255, 255)
            if ring.grid is not None:
                ring.show_grid(core.radar_grid(feed.planes, config.GRID_W, config.GRID_H,
                                               feed.zoom_km, age, config.GRID_SERPENTINE,
                                               sweep))
        else:
            age = age_s(feed.iss_at, now)
            frame = core.iss_frame(feed.iss, config.LAT, config.LON, n, t, age,
                                   config.LED_NORTH, config.CLOCKWISE)
            if ring.grid is not None:
                ring.show_grid([core.BLACK] * (config.GRID_W * config.GRID_H))
        ring.show(frame)
        deck.update(core.deck_lines(feed.mode, feed.planes, target, feed.zoom_km, age,
                                    feed.iss, config.LAT, config.LON), now)

        if not wifi.connected():
            ring.set_status(STATUS_WIFI)
        elif age is not None and age <= core.STALE_S:
            ring.set_status(STATUS_FRESH)
        else:
            ring.set_status(STATUS_STALE)

        time.sleep_ms(FRAME_MS)


main()
