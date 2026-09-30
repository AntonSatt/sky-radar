# Tester för pico/core.py. Körs med både CPython och MicroPython, utan
# testramverk, så att vi vet att kärnan fungerar på mikrokontrollern:
#   python3 tests/test_core.py
#   micropython tests/test_core.py
import sys

sys.path.insert(0, "pico")
sys.path.insert(0, "../pico")
import core  # noqa: E402

VENUE = (59.862, 17.642)
ARLANDA = (59.6519, 17.9186)


def close(a, b, tol):
    return abs(a - b) <= tol


def test_slim_filters_ground_and_fixes_data():
    assert core.slim_aircraft({"alt_baro": "ground", "dir": 162, "dst": 31.8}) is None
    assert core.slim_aircraft({"alt_baro": 5000}) is None
    # Negativ tryckhöjd vid högtryck: GPS-höjden ska användas. Nautiska mil
    # och fot blir km och meter.
    plane = core.slim_aircraft(
        {"flight": "BEL4BP  ", "alt_baro": -250, "alt_geom": 450, "dir": 140, "dst": 15.4})
    assert plane[0] == "BEL4BP" and plane[1] == 140 and plane[3] == 137
    assert close(plane[2], 28.52, 0.01)
    # Saknad anropssignal
    plane = core.slim_aircraft({"flight": "@@@@@@@@", "alt_baro": 900, "dir": 1, "dst": 2})
    assert plane[0] == "" and plane[3] == 274
    # Okänd höjd behåller planet
    assert core.slim_aircraft({"dir": 10, "dst": 3})[3] is None


def test_slim_response_sorts_nearest_first():
    data = {"ac": [
        {"flight": "FAR", "alt_geom": 30000, "dir": 10, "dst": 30},
        {"flight": "GND", "alt_baro": "ground", "dir": 20, "dst": 1},
        {"flight": "NEAR", "alt_geom": 2000, "dir": 30, "dst": 5},
    ]}
    assert [p[0] for p in core.slim_response(data)] == ["NEAR", "FAR"]
    assert core.slim_response({"aircraft": []}) == []


def test_api_radius_nm():
    assert core.api_radius_nm(25) == 14
    assert core.api_radius_nm(75) == 41
    assert core.api_radius_nm(150) == 81
    assert core.api_radius_nm(1.852) == 1


def test_led_index():
    assert core.led_index(0, 24) == 0
    assert core.led_index(90, 24) == 6
    assert core.led_index(359, 24) == 0
    assert core.led_index(-15, 24) == 23
    # Ring monterad med lysdiod 5 mot norr, numrerad moturs
    assert core.led_index(0, 24, north=5) == 5
    assert core.led_index(90, 24, north=0, clockwise=False) == 18
    assert core.led_index(90, 12) == 3


def test_geometry():
    bearing = core.bearing_deg(VENUE[0], VENUE[1], ARLANDA[0], ARLANDA[1])
    dist = core.distance_km(VENUE[0], VENUE[1], ARLANDA[0], ARLANDA[1])
    assert close(bearing, 146, 3), bearing
    assert close(dist, 28, 2), dist
    assert close(core.bearing_deg(0, 0, 10, 0), 0, 0.01)
    assert close(core.bearing_deg(0, 0, 0, 10), 90, 0.01)


def test_altitude_color():
    assert core.altitude_color(-500) == (255, 0, 0)
    assert core.altitude_color(0) == (255, 0, 0)
    assert core.altitude_color(40000) == (0, 40, 255)
    assert core.altitude_color(None) == core.UNKNOWN_ALT_COLOR
    assert core.altitude_color(1000) == (255, 100, 0)
    low = core.altitude_color(500)
    assert low[0] == 255 and 0 < low[1] < 100


def test_radar_frame():
    planes = [("A", 90, 5, 1000), ("B", 90, 30, 35000), ("C", 270, 50, 10000)]
    frame = core.radar_frame(planes, 24, 40, sweep=90, age_s=1)
    assert len(frame) == 24
    # Två plan på samma lysdiod: det närmaste (röda, lågt) vinner
    assert frame[6][0] > frame[6][2]
    # C ligger utanför zoomen och ska inte synas
    assert frame[18] == core.BLACK
    # Svepet syns där inget plan lyser
    frame = core.radar_frame([], 24, 40, sweep=0, age_s=1)
    assert frame[0] == core.SWEEP_COLOR
    # Gammal data: svepet blir rött
    frame = core.radar_frame([], 24, 40, sweep=0, age_s=60)
    assert frame[0] == core.SWEEP_STALE_COLOR
    frame = core.radar_frame([], 24, 40, sweep=0, age_s=None)
    assert frame[0] == core.SWEEP_STALE_COLOR


def test_radar_frame_fades_stale_data():
    planes = [("A", 0, 5, 1000)]
    fresh = core.radar_frame(planes, 24, 40, sweep=0, age_s=1)[0]
    stale = core.radar_frame(planes, 24, 40, sweep=0, age_s=70)[0]
    assert stale[0] < fresh[0]


def test_radar_grid():
    planes = [("N", 0, 40, 30000), ("C", 0, 0.1, 500)]
    grid = core.radar_grid(planes, 8, 8, 40, age_s=1)
    assert len(grid) == 64
    # Norr i kanten: översta raden
    assert any(grid[x] != core.BLACK for x in range(8))
    # Rakt söderut i kanten hamnar på nedersta raden (7, udda), kolumn 4.
    # Sicksack spegelvänder udda rader, så där blir det kolumn 3.
    south = [("S", 180, 40, 1000)]
    plain = core.radar_grid(south, 8, 8, 40, age_s=1)
    zigzag = core.radar_grid(south, 8, 8, 40, age_s=1, serpentine=True)
    assert [i for i in range(64) if plain[i] != core.BLACK] == [60]
    assert [i for i in range(64) if zigzag[i] != core.BLACK] == [59]


def test_parse_iss():
    where = {"latitude": 59.0, "longitude": 18.0, "visibility": "eclipsed"}
    assert core.parse_iss(where) == (59.0, 18.0, False)
    where["visibility"] = "daylight"
    assert core.parse_iss(where)[2] is True
    notify = {"iss_position": {"latitude": "-34.7", "longitude": "-114.8"}}
    assert core.parse_iss(notify) == (-34.7, -114.8, None)


def test_iss_frame():
    far = (-34.7, -114.8, True)
    frame = core.iss_frame(far, VENUE[0], VENUE[1], 24, t=0, age_s=1)
    lit = [i for i in range(24) if frame[i] != core.BLACK]
    assert len(lit) == 3
    bearing, dist, overhead = core.iss_info(far, VENUE[0], VENUE[1])
    assert not overhead and dist > 10000
    assert core.led_index(bearing, 24) in lit
    # Över Stockholm: över horisonten, hela ringen lyser
    near = (59.3, 18.1, False)
    frame = core.iss_frame(near, VENUE[0], VENUE[1], 24, t=0, age_s=1)
    assert all(c != core.BLACK for c in frame)
    assert core.iss_frame(None, 0, 0, 24, t=0, age_s=None) == [core.BLACK] * 24


def run():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("ok     " + name)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FEL    " + name + ": " + repr(exc))
    print("{} tester, {} fel".format(len(tests), failed))
    sys.exit(1 if failed else 0)


run()
