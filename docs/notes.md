# Engineering notes

What was measured and learned while building Sky Radar, for anyone building
something similar on a microcontroller. Measured in and around Uppsala,
Sweden, in September and October 2026.

## Data sources

All tested 2026-09-30 from the ESP32-C3's point of view: free, no API key,
TLS 1.2 (what MicroPython's TLS handles).

| Service | Response at test | Notes |
|---|---|---|
| adsb.fi open data | 5-10 KB, 0.13 s | First choice for aircraft |
| api.adsb.lol | 5-10 KB, 0.2-4 s | Same format (`ac`, `dir`, `dst`), only the URL differs. Timed out for 10 s once and came back a few minutes later |
| wheretheiss.at | 308 bytes, 1.6 s | Includes `visibility` (daylight or eclipsed), used for the sunlit/shadow colour |
| open-notify | 0.4 s | Plain HTTP |

Both ADS-B APIs take the radius in nautical miles (1 nm = 1.852 km). The
code converts from km for the request and converts everything back to km
and metres as soon as the response is parsed (`slim_aircraft` in
`pico/core.py`).

## How much traffic?

Aircraft within each radius of central Uppsala on a Wednesday afternoon (in
brackets, how many of them were below 3,000 m):

| Radius | 16:08 | 16:31 |
|---|---|---|
| 28 km (15 nm) | - | 4 (4) |
| 46 km (25 nm) | 4 (3) | 7 (7) |
| 74 km (40 nm) | 7 (3) | 15 (10) |
| 111 km (60 nm) | 10 (3) | 18 (11) |

Traffic swings a lot within half an hour. At rush hour the aircraft cluster
in the sector towards Arlanda (about 100-190 degrees from Uppsala), and 25 km
is the right zoom. When it is quiet (weekends, evenings) 75 km or more works
better. Hence the zoom button.

## Pitfalls in real ADS-B data

Seen in real responses 2026-09-30, all handled in `pico/core.py`:

- **Aircraft on the ground** have `alt_baro: "ground"` (parked aircraft at
  Bromma, for example). They are skipped.
- **`alt_baro` can be negative** for aircraft in the air. It is pressure
  altitude, which is off at high air pressure: an aircraft on approach to
  Arlanda showed -250 ft `alt_baro` but 450 ft `alt_geom` at 128 knots. Use
  `alt_geom` (GPS) first.
- **The callsign can be missing** or come as `@@@@@@@@`.
- **The backup can be down too.** Keep the timeout short (5 s) and keep
  showing the last known aircraft, fading as the data gets old, instead of
  freezing.

## MicroPython on the ESP32-C3

Applies to MicroPython 1.28-1.29 (`ESP32_GENERIC_C3`) on the Waveshare
ESP32-C3-Zero and the ESP32-C3 SuperMini.

**Flashing and running**

- esptool v5 uses hyphens: `erase-flash`, `write-flash`. Native USB, no
  BOOT button needed to flash.
- `mpremote cp ... : + run pico/main.py` copies the files and shows the
  output. `mpremote reset` makes `main.py` start on its own.
- Only one program can hold the serial port at a time (Thonny and mpremote
  clash).
- `mpremote devs` shows each board's MAC address, handy for telling several
  boards apart.
- Free after boot: about 177 KB RAM and 2 MB flash.

**ESP32-C3-Zero (Waveshare)**

- The pin labels are only on the underside. Seen from above with USB
  pointing up: left side 5V, GND, 3V3, 0, 1, 2, 3, 4, 5; right side 21, 20,
  19, 18, 10, 9, 8, 7, 6.
- Built-in WS2812 RGB LED on GPIO10. The BOOT button on GPIO9 can be read as
  a normal button while the code runs.
- A single GND pin: several ground wires need a breadboard.

**ESP32-C3 SuperMini**

- The on-board LED is a plain LED, not RGB.
- The antenna often cannot handle full transmit power. `txpower=8.5` makes
  it connect.

**Network**

- **2.4 GHz only.** WiFi status 201 means the network is not visible. Some
  phone hotspots switch to 5 GHz on their own, or switch off when no
  clients are connected.
- The WiFi driver survives a soft reboot. An interrupted run can leave it
  halfway through connecting, and then `connect()` and
  `config(txpower=...)` fail with "Wifi Internal State Error". Fix:
  `active(False)` then `active(True)` first thing.
- `requests` sends HTTP/1.0 and cannot handle chunked responses. adsb.fi and
  wheretheiss.at answer HTTP/1.0 without chunking.
- **A TLS request takes 1.5-2.5 s.** Fetch in a `_thread` so animations keep
  running. The thread needs a 16 KB stack; the default (about 4 KB) is too
  small for TLS.

**Memory**

- With the OLED and all the code, about 55-60 KB is free while running. A
  150 km response from adsb.fi (20+ aircraft, about 15 KB) takes about 50 KB
  once parsed and raised `MemoryError`. Hence the 75 km maximum.
- `json.load()` straight on a TLS socket fails ("stream operation not
  supported"). `json.loads()` accepts `bytearray` and `memoryview`, so a
  preallocated buffer can be parsed without a copy.
- Aircraft are stored as tuples, not dicts, to save memory.
- `"%d" % some_float` can misbehave in MicroPython; call `int()` first.

**OLED**

- The 1.3" module with a rotary encoder has an **SH1106**, not an SSD1306.
  Symptom with the SSD1306 driver: only the last line of text at the top and
  noise everywhere else. The SH1106 has no horizontal addressing mode and
  its image is offset by two columns; `pico/oled.py` handles both.
- Power it from 3V3, not 5V, so the I2C pull-ups do not lift the ESP32's
  pins to 5 V.
- `ENODEV` while running means a loose SDA or SCL wire. Catch `OSError` when
  drawing and re-run the init sequence once the screen answers, or the
  whole program stops.
- A full redraw takes about 25 ms over I2C. Redrawing more than about five
  times a second makes the ring animation stutter.

## Power

24 WS2812 LEDs at full white draw about 1.4 A (about 60 mA each) and USB
gives about 0.5 A. `MAX_BRIGHTNESS = 0.2` keeps it well within that and is
still bright indoors.
