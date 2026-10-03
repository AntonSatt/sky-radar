"""Skalet på kortet: WiFi, hämtning, lysdioder och knapp.

All logik bor i core.py. Den här filen är det enda som rör hårdvaran och
körs bara på mikrokontrollern (MicroPython). WiFi-uppgifterna ligger i
secrets.py bredvid, som git ignorerar:

    WIFI_SSID = "..."
    WIFI_PASSWORD = "..."

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
    def __init__(self):
        self.np = neopixel.NeoPixel(machine.Pin(config.LED_PIN), config.N_LEDS)
        self.status = None
        if config.STATUS_LED_PIN is not None:
            self.status = neopixel.NeoPixel(machine.Pin(config.STATUS_LED_PIN), 1)

    def show(self, frame):
        for i, color in enumerate(frame):
            self.np[i] = core.scale(color, config.MAX_BRIGHTNESS)
        self.np.write()

    def set_status(self, color):
        if self.status is not None:
            self.status[0] = color
            self.status.write()

    def boot(self):
        """En prick går ett varv från norr. Visar vilken lysdiod som är
        LED_NORTH och åt vilket håll numren går, inför inställningen."""
        n = config.N_LEDS
        for step in range(n + 1):
            frame = [core.BLACK] * n
            i = core.led_index(step * 360 / n, n, config.LED_NORTH, config.CLOCKWISE)
            frame[i] = (0, 255, 120)
            frame[config.LED_NORTH] = (255, 255, 255)
            self.show(frame)
            time.sleep_ms(40)
        self.show([core.BLACK] * n)


# --- Nät -------------------------------------------------------------------

class Wifi:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        if config.WIFI_TXPOWER:
            self.wlan.config(txpower=config.WIFI_TXPOWER)
        self.tried_at = None

    def connected(self):
        return self.wlan.isconnected()

    def connect(self, ring, wait_ms=20000):
        """Försök ansluta och snurra blått på ringen medan vi väntar."""
        if secrets is None:
            print("secrets.py saknas på kortet, kör utan nät")
            return False
        print("WiFi: ansluter till", secrets.WIFI_SSID)
        self.wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        self.tried_at = time.ticks_ms()
        ring.set_status(STATUS_WIFI)
        n = config.N_LEDS
        step = 0
        while not self.wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), self.tried_at) > wait_ms:
                print("WiFi: ingen anslutning, status", self.wlan.status())
                return False
            frame = [core.BLACK] * n
            frame[step % n] = (0, 60, 255)
            ring.show(frame)
            step += 1
            time.sleep_ms(60)
        print("WiFi: ansluten,", self.wlan.ifconfig()[0])
        return True

    def retry_if_needed(self):
        """Ny anslutning i bakgrunden om nätet har gått ner. Blockerar inte."""
        if self.connected() or secrets is None:
            return
        now = time.ticks_ms()
        if self.tried_at is None or time.ticks_diff(now, self.tried_at) > WIFI_RETRY_MS:
            print("WiFi: nere, försöker igen")
            self.tried_at = now
            try:
                self.wlan.disconnect()
                self.wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
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
    ring = Ring()
    ring.boot()
    wifi = Wifi()
    wifi.connect(ring)
    button = Button(config.BUTTON_PIN) if config.BUTTON_PIN is not None else None

    zoom = 1 if len(config.ZOOM_KM) > 1 else 0
    feed = Feed("radar", config.ZOOM_KM[zoom])
    threaded = feed.start_thread(wifi)
    n = config.N_LEDS
    print("Sky Radar igång: läge", feed.mode, feed.zoom_km, "km,",
          "hämtar i egen tråd" if threaded else "hämtar mellan bilderna")

    while True:
        press = button.poll() if button else None
        if press == "short":
            zoom = (zoom + 1) % len(config.ZOOM_KM)
            feed.zoom_km = config.ZOOM_KM[zoom]
            feed.wake = True
            print("zoom", feed.zoom_km, "km")
        elif press == "long":
            feed.mode = "iss" if feed.mode == "radar" else "radar"
            feed.wake = True
            print("läge", feed.mode)

        if not threaded:
            feed.step(wifi)

        now = time.ticks_ms()
        t = now / 1000
        if feed.mode == "radar":
            age = age_s(feed.radar_at, now)
            sweep = (t * core.SWEEP_DEG_PER_S) % 360
            frame = core.radar_frame(feed.planes, n, feed.zoom_km, sweep, age,
                                     config.LED_NORTH, config.CLOCKWISE)
        else:
            age = age_s(feed.iss_at, now)
            frame = core.iss_frame(feed.iss, config.LAT, config.LON, n, t, age,
                                   config.LED_NORTH, config.CLOCKWISE)
        ring.show(frame)

        if not wifi.connected():
            ring.set_status(STATUS_WIFI)
        elif age is not None and age <= core.STALE_S:
            ring.set_status(STATUS_FRESH)
        else:
            ring.set_status(STATUS_STALE)

        time.sleep_ms(FRAME_MS)


main()
