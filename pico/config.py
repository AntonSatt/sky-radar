# Inställningar för lampan. Lokala avvikelser, till exempel koordinater
# hemma, läggs i config_local.py bredvid den här filen. Git ignorerar den.

# Eventlokalen. Sätt alla tre i config_local.py för en annan plats.
PLACE = "ABF, S:t Persgatan 22B, Uppsala"
LAT = 59.8621567
LON = 17.6421569

# Ringen. Arrangörerna har ringar i flera storlekar, ändra N_LEDS på plats.
N_LEDS = 24
LED_NORTH = 0          # lysdioden som pekar mot norr
CLOCKWISE = True       # går lysdiodsnumren medurs sett ovanifrån?
MAX_BRIGHTNESS = 0.2   # USB räcker inte till fullt ljus

# Matrisen (om en 8x8 används i stället för eller bredvid ringen)
GRID_W = 8
GRID_H = 8
GRID_SERPENTINE = False

# Zoomnivåer i km, knappen stegar mellan dem
ZOOM_KM = (25, 75, 150)

# Hur ofta data hämtas (adsb.fi tillåter max 1 anrop per sekund)
RADAR_EVERY_S = 4
ISS_EVERY_S = 10
TIMEOUT_S = 5

# Flyg-API:erna vill ha radien i nautiska mil ({nm}), koden räknar om från km
RADAR_URLS = (
    "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}",
    "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}",
)
ISS_URLS = (
    "https://api.wheretheiss.at/v1/satellites/25544",
    "http://api.open-notify.org/iss-now.json",
)

try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
