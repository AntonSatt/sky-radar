"""Delad logik för Sky Radar.

Ren Python utan nätverk och hårdvara, så att samma fil körs på laptopen
(CPython) och på mikrokontrollern (MicroPython, Pico 2 W eller ESP32-C3).
Allt här returnerar färger som (r, g, b) med 0-255. Skalning till
maxljusstyrka sker i hårdvaruskalet, inte här.

Ett plan representeras som en tupel (anropssignal, riktning, avstånd, höjd):
riktning i grader från lampan, avstånd i km, höjd i meter eller None. Flyg-
API:erna räknar i nautiska mil och fot, det omvandlas direkt när datan kommer
in. Tupler i stället för dict sparar minne på mikrokontrollern.
"""

import math

RAD = math.pi / 180
EARTH_KM = 6371.0
NM_KM = 1.852    # en nautisk mil
FT_M = 0.3048    # en fot

# Data äldre än så här bleknar, och svepet blir rött.
STALE_S = 20

# Svepet går ett varv på 3 sekunder.
SWEEP_DEG_PER_S = 120
SWEEP_COLOR = (0, 60, 0)
SWEEP_STALE_COLOR = (60, 0, 0)

# Höjd i meter -> färg. Lågt är rött (start och landning), högt är blått.
ALT_COLORS = (
    (0, (255, 0, 0)),
    (1000, (255, 100, 0)),
    (3000, (255, 220, 0)),
    (6000, (0, 220, 120)),
    (9000, (0, 160, 255)),
    (11500, (0, 40, 255)),
)
UNKNOWN_ALT_COLOR = (200, 200, 200)

# ISS ca 420 km upp syns över horisonten inom ca 2250 km markavstånd.
ISS_HORIZON_KM = 2250
ISS_SUNLIT_COLOR = (255, 255, 255)
ISS_SHADOW_COLOR = (40, 60, 255)

BLACK = (0, 0, 0)


# --- Data in -------------------------------------------------------------

def slim_aircraft(ac):
    """Plockar ut det lampan behöver ur ett plan från adsb.fi eller adsb.lol.

    Returnerar None för plan på marken och plan utan riktning eller avstånd.
    """
    if ac.get("alt_baro") == "ground":
        return None
    bearing = ac.get("dir")
    dist = ac.get("dst")
    if bearing is None or dist is None:
        return None
    # alt_geom (GPS) först: alt_baro är tryckhöjd och kan bli negativ vid
    # högtryck, även för plan i luften.
    alt = ac.get("alt_geom")
    if not isinstance(alt, (int, float)):
        alt = ac.get("alt_baro")
    if not isinstance(alt, (int, float)):
        alt = None
    if alt is not None:
        alt = int(alt * FT_M + 0.5)
    # Saknad anropssignal kommer ibland som "@@@@@@@@".
    signal = (ac.get("flight") or "").strip().strip("@")
    return (signal, bearing, round(dist * NM_KM, 2), alt)


def api_radius_nm(km):
    """Radien att fråga API:et om, i hela nautiska mil, avrundat uppåt."""
    return int(math.ceil(km / NM_KM))


def slim_response(data):
    """Alla plan i luften ur ett API-svar, närmast först."""
    raw = data.get("ac")
    if raw is None:
        raw = data.get("aircraft") or []
    planes = []
    for ac in raw:
        plane = slim_aircraft(ac)
        if plane is not None:
            planes.append(plane)
    planes.sort(key=lambda p: p[2])
    return planes


def parse_iss(data):
    """(lat, lon, solbelyst) ur wheretheiss.at eller open-notify.

    solbelyst är True/False, eller None när källan inte säger något.
    """
    if "iss_position" in data:
        pos = data["iss_position"]
        return (float(pos["latitude"]), float(pos["longitude"]), None)
    visibility = data.get("visibility")
    sunlit = None if visibility is None else visibility != "eclipsed"
    return (float(data["latitude"]), float(data["longitude"]), sunlit)


# --- Geometri ------------------------------------------------------------

def bearing_deg(lat1, lon1, lat2, lon2):
    """Kurs längs storcirkeln från punkt 1 mot punkt 2, 0-360 grader."""
    p1 = lat1 * RAD
    p2 = lat2 * RAD
    dl = (lon2 - lon1) * RAD
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.atan2(y, x) / RAD) % 360


def distance_km(lat1, lon1, lat2, lon2):
    """Avstånd längs jordytan (haversine)."""
    p1 = lat1 * RAD
    p2 = lat2 * RAD
    dp = p2 - p1
    dl = (lon2 - lon1) * RAD
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(min(1.0, a)))


def led_index(bearing, n, north=0, clockwise=True):
    """Vilken lysdiod på en ring med n lysdioder som pekar mot en riktning.

    north: lysdioden som pekar mot norr. clockwise: om numren går medurs
    sett ovanifrån. Båda beror på hur ringen sitter och ställs in i config.
    """
    i = int((bearing % 360) * n / 360 + 0.5) % n
    if not clockwise:
        i = -i % n
    return (north + i) % n


# --- Färger --------------------------------------------------------------

def scale(color, factor):
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def mix(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def altitude_color(alt):
    if alt is None:
        return UNKNOWN_ALT_COLOR
    if alt <= ALT_COLORS[0][0]:
        return ALT_COLORS[0][1]
    for i in range(1, len(ALT_COLORS)):
        hi_alt, hi_color = ALT_COLORS[i]
        if alt <= hi_alt:
            lo_alt, lo_color = ALT_COLORS[i - 1]
            return mix(lo_color, hi_color, (alt - lo_alt) / (hi_alt - lo_alt))
    return ALT_COLORS[-1][1]


def freshness(age_s):
    """1.0 för färsk data, bleknar mot 0.15 när datan blir gammal."""
    if age_s is None:
        return 0.0
    if age_s <= STALE_S:
        return 1.0
    return max(0.15, 1.0 - (age_s - STALE_S) / 60)


# --- Bilder --------------------------------------------------------------

def radar_frame(planes, n, range_km, sweep, age_s, north=0, clockwise=True):
    """En bild för ringen i radarläge.

    sweep: svepets riktning i grader. age_s: sekunder sedan senaste lyckade
    hämtning, None om ingen data finns än. Delar två plan lysdiod vinner det
    starkaste (oftast det närmaste).
    """
    frame = [BLACK] * n
    level = [0.0] * n
    fade = freshness(age_s)
    for _, bearing, dist, alt in planes:
        if dist > range_km:
            continue
        near = 1.0 - 0.7 * dist / range_km
        # Plan blossar upp när svepet passerar och klingar av till nästa varv.
        behind = (sweep - bearing) % 360
        glow = 0.35 + 0.65 * (1 - behind / 360) ** 2
        brightness = near * glow * fade
        i = led_index(bearing, n, north, clockwise)
        if brightness > level[i]:
            level[i] = brightness
            frame[i] = scale(altitude_color(alt), brightness)

    sweep_color = SWEEP_COLOR
    if age_s is None or age_s > STALE_S:
        sweep_color = SWEEP_STALE_COLOR
    for step, factor in ((0, 1.0), (1, 0.4), (2, 0.15)):
        i = led_index(sweep - step * 360 / n, n, north, clockwise)
        if level[i] == 0:
            frame[i] = scale(sweep_color, factor)
    return frame


def radar_grid(planes, w, h, range_km, age_s, serpentine=False):
    """2D-radar för en matris, till exempel 8x8. Mitten är lampan, upp är norr.

    Returnerar w*h färger rad för rad uppifrån, i den ordning lysdioderna är
    kopplade. serpentine: matrisen är kopplad i sicksack (varannan rad
    baklänges), vanligt på flexibla matriser.
    """
    grid = [BLACK] * (w * h)
    level = [0.0] * (w * h)
    fade = freshness(age_s)
    cx = (w - 1) / 2
    cy = (h - 1) / 2
    for _, bearing, dist, alt in planes:
        if dist > range_km:
            continue
        r = dist / range_km
        x = int(cx + r * cx * math.sin(bearing * RAD) + 0.5)
        y = int(cy - r * cy * math.cos(bearing * RAD) + 0.5)
        x = min(w - 1, max(0, x))
        y = min(h - 1, max(0, y))
        if serpentine and y % 2 == 1:
            x = w - 1 - x
        brightness = (1.0 - 0.5 * r) * fade
        i = y * w + x
        if brightness > level[i]:
            level[i] = brightness
            grid[i] = scale(altitude_color(alt), brightness)
    return grid


def iss_info(iss, lat, lon):
    """(riktning, avstånd i km, över horisonten) från lampan till ISS."""
    iss_lat, iss_lon, _ = iss
    dist = distance_km(lat, lon, iss_lat, iss_lon)
    return (bearing_deg(lat, lon, iss_lat, iss_lon), dist, dist < ISS_HORIZON_KM)


def iss_frame(iss, lat, lon, n, t, age_s, north=0, clockwise=True):
    """En bild för ringen i ISS-läge.

    En lysdiod pekar mot ISS, starkare ju närmare den är. Vit när ISS är i
    solljus, blå i jordens skugga. Över horisonten pulserar hela ringen.
    t: tid i sekunder, driver pulsen.
    """
    frame = [BLACK] * n
    if iss is None:
        return frame
    bearing, dist, overhead = iss_info(iss, lat, lon)
    color = ISS_SHADOW_COLOR if iss[2] is False else ISS_SUNLIT_COLOR
    fade = freshness(age_s)
    if overhead:
        pulse = 0.1 + 0.15 * (1 + math.sin(t * 4)) / 2
        for i in range(n):
            frame[i] = scale(color, pulse * fade)
    near = max(0.3, 1.0 - dist / 20000)
    i = led_index(bearing, n, north, clockwise)
    frame[i] = scale(color, near * fade)
    for side in (-1, 1):
        j = (i + side) % n
        frame[j] = scale(color, 0.25 * near * fade)
    return frame
