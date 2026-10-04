# Sky Radar manual

How to start the radar, read it and fix it when something goes wrong. For
building and flashing, see the [README](../README.md).

## Starting up

1. **Turn on WiFi on 2.4 GHz.** The ESP32-C3 cannot see 5 GHz networks. On
   an Android hotspot: Settings > Network & internet > Hotspot & tethering >
   Wi-Fi hotspot > Speed & compatibility > 2.4 GHz. Turning off "Turn off
   hotspot automatically" on the same page helps too.
2. **Power the unit(s).** One USB cable per board. A charger, power bank or
   laptop all work; the code lives on the board, so no laptop is needed.
3. **Watch the boot.** A green dot runs one lap round the ring, starting at
   the LED set as north. Then a blue dot spins while the board looks for
   WiFi, and the screen prints `> LINK OK` and `> SCAN ADS-B`. Aircraft show
   up after about ten seconds.
4. **Point north.** Turn the ring until the dim white dot faces north. A
   phone compass is enough.

## Reading the ring

The ring is a compass. Every aircraft within range becomes a dot in the
direction the plane actually is, seen from where the radar stands.

| You see | It means |
|---|---|
| Dim white dot, always on | North |
| Green sweep, one lap every 3 seconds | The radar is running. Aircraft light up as the sweep passes them |
| Red sweep, dots fading | No fresh data for over 20 seconds. The last known aircraft fade until the network is back |
| Coloured dot | An aircraft. Colour is altitude, brightness is distance (brighter is closer) |
| Dot blinking white | The aircraft currently shown on the screen |

Altitude colours:

| Altitude | Colour |
|---|---|
| 0 m (taking off, landing) | Red |
| 1,000 m | Orange |
| 3,000 m | Yellow |
| 6,000 m | Green |
| 9,000 m | Light blue |
| 11,500 m and up (cruising) | Blue |
| Unknown | Grey |

Colours blend smoothly between the steps. Aircraft on the ground are not
shown.

## Controls

| Control | Where | Does |
|---|---|---|
| Turn the knob | Screen module | Select an aircraft, nearest first. Its dot blinks white on the ring |
| Push the knob | Screen module | Zoom: 25, 50 or 75 km. Starts at 75 |
| BACK | Screen module | Switch between radar and ISS |
| CONFIRM | Screen module | Not used yet |
| BOOT, short press | Board | Zoom |
| BOOT, long press | Board | Switch between radar and ISS |
| RESET | Board | Restart. Fixes most things |

The board's RGB LED (on boards that have one) is green for fresh data, red
for stale data and blue for no WiFi.

## The screen

```
SKY DECK  RADAR
RNG 75km  1/5

> CCA911
ALT 739 m
DST 22.6 km
BRG 116 ESE
LINK OK
```

| Line | Means |
|---|---|
| `RNG 75km  1/5` | The range, and which aircraft of how many in range is shown |
| `> CCA911` | The callsign. Look it up on Flightradar24 to see where it is going. `UNKNOWN` if the aircraft sends none |
| `ALT 739 m` | Altitude in metres. `?` if the aircraft sends no altitude |
| `DST 22.6 km` | Distance from the radar |
| `BRG 116 ESE` | Bearing in degrees from north, and the compass point |
| `LINK OK` | Data is fresh. `LINK LOST 34s` means nothing new for 34 seconds |

`NO TARGETS` means nothing is within range. Zoom out.

## ISS mode

One LED points at the space station, brighter the closer it is. The ISS
circles the Earth in about 90 minutes, so over an afternoon the dot wanders
round the ring. White means the station is in sunlight, blue that it is in
the Earth's shadow. When it is above the horizon (within about 2,250 km) the
whole ring pulses and the screen says `** OVERHEAD **`.

## The matrix unit

The 8x8 matrix is a separate unit with its own board, running the same
code. The centre is the radar, the top edge is north and the edges are the
current range, so here you see distance as well as direction. At startup a
white pixel marks pixel 0 while a dot walks through the rest in wiring
order; turn the matrix so the white pixel is top left. If the dot zigzags,
set `GRID_SERPENTINE = True`. The matrix does not know which aircraft is
selected on the screen unit.

## When something goes wrong

**The ring keeps spinning blue.** The board cannot find a WiFi network it
knows. Check that the network is on and on 2.4 GHz (some phone hotspots
switch back to 5 GHz by themselves). The board retries every ten seconds,
no restart needed. If it never connects on a cheap board, try
`WIFI_TXPOWER = 8.5`.

**The sweep is red and the dots fade.** The network is down or the data
source is not answering, same as `LINK LOST` on the screen. The board
switches to the backup source by itself.

**The screen freezes or shows noise.** Press RESET. If it keeps happening,
reseat the SDA and SCL wires; they work loose when the module moves. Noise
on most of the screen with only one line of text means the wrong driver:
set `OLED_KIND = "sh1106"`.

**The ring stays dark.** Unplug USB and check the three wires: data to the
ring's DI (not DO), 5V and GND. Ring wire colours vary between makers, so
go by the labels on the ring, not the colours.

**Everything turns off after a while.** Many power banks switch off when the
current draw is low, and the radar draws very little. Use a phone charger
instead.

**No aircraft at all.** At 25 km it is often empty when traffic is quiet.
Zoom out to 75 km. `./scripts/kolla-api.sh` on a laptop shows what the
APIs see from your location.

**The dots point the wrong way.** The white north dot is not facing north:
turn the ring with a phone compass. If the dots move the wrong way as
aircraft fly past, the ring is upside down or numbered the other way: flip
it LEDs-up, or set `CLOCKWISE = False`.

**The knob goes backwards or skips clicks.** Swap `ENC_A` and `ENC_B` in the
board profile, or try `ENC_STEPS = 2`.

## Showing it off

- Put baking paper or a frosted lid over the LEDs so they glow instead of
  glare.
- A printed compass rose under the ring, with N/E/S/W and the nearest
  airport marked, makes people get it in five seconds.
- Let people check it against Flightradar24 on their phones.
- Put a note next to it: "Flight data: adsb.fi" (their terms ask for it).
