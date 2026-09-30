#!/usr/bin/env python3
"""Sky Radar i terminalen.

Samma kärna (pico/core.py) och inställningar (pico/config.py) som
mikrokontrollern använder. Terminalen ersätter bara lysdioderna: ringen ritas
med tecken och en 8x8-matris visas bredvid. Används för att testa logiken
utan hårdvara, och som reservdemo om hårdvaran strular.

Tangenter: z = zoom, m = läge (radar/ISS), q = avsluta.

    ./terminal/radar.py                        live från eventlokalen
    ./terminal/radar.py --plats                frågar var du är
    ./terminal/radar.py --plats "Stockholms centralstation"
    ./terminal/radar.py --record inspelningar/test.jsonl
    ./terminal/radar.py --replay inspelningar/test.jsonl
    ./terminal/radar.py --once                 en bild, sedan avsluta
"""

import argparse
import json
import math
import select
import sys
import termios
import threading
import time
import tty
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pico"))
import config  # noqa: E402
import core  # noqa: E402
import plats  # noqa: E402

FPS = 20
ARLANDA = (59.6519, 17.9186)
USER_AGENT = "sky-radar/0.1 (hackathon)"

# Ringens storlek i tecken. Tecken är ungefär dubbelt så höga som breda.
RING_RY = 8
RING_RX = 17


# --- Data ------------------------------------------------------------------

def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.TIMEOUT_S) as response:
        return json.load(response)


def fetch_first(urls):
    """Prova källorna i ordning. Returnerar (data, källa) eller kastar sista felet."""
    error = None
    for url in urls:
        try:
            return fetch_json(url), url.split("/")[2]
        except Exception as exc:  # noqa: BLE001
            error = exc
    raise error


class LiveFeed:
    """Hämtar radar- och ISS-data i en bakgrundstråd så att animationen aldrig
    fryser. På mikrokontrollern motsvaras det av andra kärnan eller korta
    anrop mellan bilderna."""

    def __init__(self, lat, lon, zoom_km, record_path=None):
        self.lat = lat
        self.lon = lon
        self.zoom_km = zoom_km
        self.record_path = record_path
        if record_path:
            Path(record_path).parent.mkdir(parents=True, exist_ok=True)
        self.planes = []
        self.radar_at = None
        self.radar_source = ""
        self.iss = None
        self.iss_at = None
        self.iss_source = ""
        self.error = ""
        self.label = "live"
        self._wake = threading.Event()
        self._last_radar_call = 0.0

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def set_zoom(self, zoom_km):
        self.zoom_km = zoom_km
        self._wake.set()

    def refresh(self):
        """Hämta allt en gång, synkront (för --once)."""
        self._fetch_radar()
        self._fetch_iss()

    def _run(self):
        next_radar = next_iss = 0.0
        while True:
            now = time.time()
            # ISS först, så att även första inspelade bilden får ISS-data
            if now >= next_iss:
                self._fetch_iss()
                next_iss = now + config.ISS_EVERY_S
            if now >= next_radar:
                self._fetch_radar()
                next_radar = now + config.RADAR_EVERY_S
            if self._wake.wait(timeout=0.5):
                self._wake.clear()
                next_radar = 0.0

    def _fetch_radar(self):
        # adsb.fi tillåter max 1 anrop per sekund
        wait = 1.1 - (time.time() - self._last_radar_call)
        if wait > 0:
            time.sleep(wait)
        self._last_radar_call = time.time()
        km = self.zoom_km
        nm = core.api_radius_nm(km)
        urls = [u.format(lat=self.lat, lon=self.lon, nm=nm) for u in config.RADAR_URLS]
        try:
            data, source = fetch_first(urls)
        except Exception as exc:  # noqa: BLE001
            self.error = "radar: " + short_error(exc)
            return
        self.planes = core.slim_response(data)
        self.radar_at = time.time()
        self.radar_source = source
        self.error = ""
        self._record(km)

    def _fetch_iss(self):
        try:
            data, source = fetch_first(config.ISS_URLS)
        except Exception as exc:  # noqa: BLE001
            self.error = "ISS: " + short_error(exc)
            return
        self.iss = core.parse_iss(data)
        self.iss_at = time.time()
        self.iss_source = source

    def _record(self, km):
        if not self.record_path:
            return
        line = {"t": round(time.time(), 1), "km": km, "ac": self.planes, "iss": self.iss}
        with open(self.record_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")


class ReplayFeed:
    """Spelar upp en inspelning i slinga, i samma takt som den spelades in.
    Samma filformat kan ligga i flash på mikrokontrollern som reserv."""

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.snapshots = [json.loads(line) for line in f if line.strip()]
        if not self.snapshots:
            raise SystemExit("Inspelningen är tom: " + path)
        self.planes = []
        self.iss = None
        self.radar_source = "inspelning"
        self.iss_source = "inspelning"
        self.error = ""
        self.label = "INSPELNING ({} bilder)".format(len(self.snapshots))
        self.zoom_km = self.snapshots[0]["km"]
        self._started = time.time()
        self._span = max(1.0, self.snapshots[-1]["t"] - self.snapshots[0]["t"] + config.RADAR_EVERY_S)
        self._update()

    def start(self):
        pass

    def refresh(self):
        self._update()

    def set_zoom(self, zoom_km):
        self.zoom_km = zoom_km

    @property
    def radar_at(self):
        self._update()
        return time.time()

    @property
    def iss_at(self):
        return time.time() if self.iss else None

    def _update(self):
        offset = (time.time() - self._started) % self._span
        t0 = self.snapshots[0]["t"]
        current = self.snapshots[0]
        for snap in self.snapshots:
            if snap["t"] - t0 <= offset:
                current = snap
        self.planes = [tuple(p) for p in current["ac"]]
        self.iss = tuple(current["iss"]) if current.get("iss") else None


def short_error(exc):
    text = str(exc) or exc.__class__.__name__
    return text[:60]


# --- Ritning ---------------------------------------------------------------

def paint(color, text):
    r, g, b = color
    return "\x1b[38;2;{};{};{}m{}\x1b[0m".format(r, g, b, text)


def led_char(color):
    if color == core.BLACK:
        return paint((70, 70, 70), "·")
    # Lysdioder syns även svagt, så lyft mörka färger lite i terminalen
    peak = max(color)
    boost = 1.0 if peak >= 120 else 120 / max(peak, 1)
    return paint(core.scale(color, min(boost, 4.0)), "●")


def ring_canvas(frame, labels, center_lines):
    """Ringen som en lista med rader. frame[i] ritas i riktningen i*360/n."""
    n = len(frame)
    h = 2 * RING_RY + 5
    w = 2 * RING_RX + 9
    cy, cx = h // 2, w // 2
    cells = [[" "] * w for _ in range(h)]

    def put(angle, radius_scale, text):
        a = angle * core.RAD
        y = int(round(cy - RING_RY * radius_scale * math.cos(a)))
        x = int(round(cx + RING_RX * radius_scale * math.sin(a)))
        start = x - (len(strip_ansi(text)) - 1) // 2
        if 0 <= y < h and 0 <= start < w:
            cells[y][start] = text
            for k in range(1, len(strip_ansi(text))):
                if start + k < w:
                    cells[y][start + k] = ""

    for i, color in enumerate(frame):
        put(i * 360 / n, 1.0, led_char(color))
    for angle, text in labels:
        put(angle, 1.22, text)
    for k, line in enumerate(center_lines):
        y = cy - len(center_lines) // 2 + k
        start = cx - len(strip_ansi(line)) // 2
        cells[y][start] = line
        for j in range(1, len(strip_ansi(line))):
            cells[y][start + j] = ""
    return ["".join(row) for row in cells]


def strip_ansi(text):
    out, skip = [], False
    for ch in text:
        if ch == "\x1b":
            skip = True
        elif skip and ch == "m":
            skip = False
        elif not skip:
            out.append(ch)
    return "".join(out)


def grid_lines(grid, w, h):
    lines = []
    for y in range(h):
        lines.append(" ".join(led_char(grid[y * w + x]) for x in range(w)))
    return lines


def radar_panel(feed, zoom_km, age):
    planes = [p for p in feed.planes if p[2] <= zoom_km]
    lines = [
        "RADAR  {} km  {} plan".format(zoom_km, len(planes)),
        "källa: {}  {}".format(feed.radar_source or "-", age_text(age)),
        "",
    ]
    for signal, bearing, dist, alt in planes[:10]:
        text = "{:<8} {:>8} {:>4}°  {:>8}".format(
            signal or "?", format_altitude(alt), int(bearing), format_km(dist))
        lines.append(paint(core.altitude_color(alt), text))
    if len(planes) > 10:
        lines.append("... och {} till".format(len(planes) - 10))
    return lines


def iss_panel(feed, lat, lon, age):
    lines = ["ISS", "källa: {}  {}".format(feed.iss_source or "-", age_text(age)), ""]
    if feed.iss is None:
        return lines + ["ingen data än"]
    bearing, dist, overhead = core.iss_info(feed.iss, lat, lon)
    iss_lat, iss_lon, sunlit = feed.iss
    light = {True: "i solljus", False: "i jordens skugga", None: "okänt ljus"}[sunlit]
    lines += [
        "position: {:.1f}, {:.1f}".format(iss_lat, iss_lon),
        "avstånd:  {:,.0f} km".format(dist).replace(",", " "),
        "riktning: {:.0f}°".format(bearing),
        light,
    ]
    if overhead:
        lines += ["", paint((255, 255, 255), "*** ÖVER HORISONTEN ***")]
    return lines


def format_altitude(alt):
    """5021 -> "5 020 m". Tiotal räcker, höjden kommer i steg om 25 fot."""
    if alt is None:
        return "?"
    return "{:,} m".format(int(round(alt, -1))).replace(",", " ")


def format_km(km):
    """20.83 -> "20,8 km", med svenskt decimalkomma."""
    return "{:.1f} km".format(km).replace(".", ",")


def age_text(age):
    if age is None:
        return "väntar på data"
    return "uppdaterad {:.0f} s sedan".format(age)


def render(feed, mode, zoom_km, lat, lon, t, place):
    now = time.time()
    n = config.N_LEDS
    labels = [
        (0, paint((200, 200, 200), "N")),
        (90, paint((200, 200, 200), "Ö")),
        (180, paint((200, 200, 200), "S")),
        (270, paint((200, 200, 200), "V")),
        (core.bearing_deg(lat, lon, ARLANDA[0], ARLANDA[1]), paint((160, 160, 160), "ARN")),
    ]
    if mode == "radar":
        age = None if feed.radar_at is None else max(0.0, now - feed.radar_at)
        sweep = (t * core.SWEEP_DEG_PER_S) % 360
        frame = core.radar_frame(feed.planes, n, zoom_km, sweep, age)
        grid = core.radar_grid(feed.planes, config.GRID_W, config.GRID_H, zoom_km, age)
        panel = radar_panel(feed, zoom_km, age)
        panel += ["", "8x8-matris:"] + grid_lines(grid, config.GRID_W, config.GRID_H)
        center = ["RADAR", "{} km".format(zoom_km)]
    else:
        age = None if feed.iss_at is None else max(0.0, now - feed.iss_at)
        frame = core.iss_frame(feed.iss, lat, lon, n, t, age)
        panel = iss_panel(feed, lat, lon, age)
        center = ["ISS"]

    ring = ring_canvas(frame, labels, center)
    rows = max(len(ring), len(panel))
    out = []
    for k in range(rows):
        left = ring[k] if k < len(ring) else " " * (2 * RING_RX + 9)
        right = panel[k] if k < len(panel) else ""
        out.append(left + "   " + right)
    footer = "z = zoom   m = läge   q = avsluta   |   " + feed.label
    if feed.error:
        footer += "   |   " + paint((255, 80, 80), feed.error)
    out += ["", footer, "Plats: {}   |   Flygdata: adsb.fi".format(place)]
    return out


# --- Huvudloop -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sky Radar i terminalen")
    parser.add_argument("--lat", type=float, default=config.LAT)
    parser.add_argument("--lon", type=float, default=config.LON)
    parser.add_argument("--plats", nargs="?", const="",
                        help="adress eller plats, slås upp via OpenStreetMap (utan värde: fråga)")
    parser.add_argument("--mode", choices=("radar", "iss"), default="radar")
    parser.add_argument("--zoom", type=int, default=1, help="index i config.ZOOM_KM")
    parser.add_argument("--record", help="spara varje radarhämtning som JSON-rader")
    parser.add_argument("--replay", help="spela upp en inspelning i stället för live")
    parser.add_argument("--once", action="store_true", help="rita en bild och avsluta")
    args = parser.parse_args()

    place = config.PLACE
    if args.plats is not None:
        try:
            args.lat, args.lon, place = plats.geocode(args.plats or plats.ask())
        except LookupError as exc:
            raise SystemExit(str(exc))
    elif (args.lat, args.lon) != (config.LAT, config.LON):
        place = "{}, {}".format(args.lat, args.lon)

    zoom = args.zoom % len(config.ZOOM_KM)
    if args.replay:
        feed = ReplayFeed(args.replay)
    else:
        feed = LiveFeed(args.lat, args.lon, config.ZOOM_KM[zoom], args.record)

    if args.once:
        feed.refresh()
        zoom_km = feed.zoom_km if args.replay else config.ZOOM_KM[zoom]
        print("\n".join(render(feed, args.mode, zoom_km, args.lat, args.lon, time.time(), place)))
        return

    if not sys.stdin.isatty():
        raise SystemExit("Kör i en riktig terminal, eller använd --once.")

    feed.start()
    mode = args.mode
    old = termios.tcgetattr(sys.stdin)
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            zoom_km = config.ZOOM_KM[zoom]
            lines = render(feed, mode, zoom_km, args.lat, args.lon, time.time(), place)
            sys.stdout.write("\x1b[H" + "\x1b[K\n".join(lines) + "\x1b[K\x1b[J")
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], 1 / FPS)
            if not ready:
                continue
            key = sys.stdin.read(1).lower()
            if key == "q":
                break
            if key == "z":
                zoom = (zoom + 1) % len(config.ZOOM_KM)
                feed.set_zoom(config.ZOOM_KM[zoom])
            if key == "m":
                mode = "iss" if mode == "radar" else "radar"
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
