# Inställningar för lampan. Lokala avvikelser, till exempel koordinater
# hemma, läggs i config_local.py bredvid den här filen. Git ignorerar den.

# Eventlokalen. Sätt alla tre i config_local.py för en annan plats.
PLACE = "ABF, S:t Persgatan 22B, Uppsala"
LAT = 59.8621567
LON = 17.6421569

# Kortet. Siffrorna är GPIO-nummer, standard är ESP32-C3-Zero (Waveshare).
LED_PIN = 3            # ringens DIN (inte DOUT), None = ingen ring
STATUS_LED_PIN = 10    # kortets inbyggda RGB-lysdiod, None om den saknas
BUTTON_PIN = 9         # BOOT-knappen: kort tryck = zoom, långt tryck = läge
WIFI_TXPOWER = None    # sätt till 8.5 om WiFi inte ansluter (känt C3-problem)

# Ringen. Arrangörerna har ringar i flera storlekar, ändra N_LEDS på plats.
N_LEDS = 24
LED_NORTH = 0          # lysdioden som pekar mot norr
CLOCKWISE = True       # går lysdiodsnumren medurs sett ovanifrån?
MAX_BRIGHTNESS = 0.2   # USB räcker inte till fullt ljus

# Matrisen (om en 8x8 används i stället för eller bredvid ringen)
GRID_PIN = None        # matrisens DIN, till exempel 4. None = ingen matris
GRID_W = 8
GRID_H = 8
GRID_SERPENTINE = False

# Decket: OLED-modul med vridratt och knapparna BACK och CONFIRM. Stiften
# sätts i kortets profil, None = finns inte.
OLED_SDA = None
OLED_SCL = None
OLED_KIND = "ssd1306"  # "sh1106" om bilden har en skräprand i högerkanten
ENC_A = None           # TRA. Byt plats på A och B om ratten går baklänges
ENC_B = None           # TRB
ENC_STEPS = 4          # kvartssteg per klick, prova 2 om varannan klick missas
ENC_PUSH_PIN = None    # tryck på ratten: zoom
BACK_PIN = None        # BACK: radar eller ISS
CONFIRM_PIN = None     # CONFIRM: ledig

# Zoomnivåer i km, knappen stegar mellan dem. 150 km gav MemoryError på
# C3:an med skärmen (2026-10-03): 20+ tolkade plan tar ca 50 KB.
ZOOM_KM = (25, 50, 75)

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

# Kortets profil (stift och vilka lysdioder som finns), från pico/boards/.
# till-kortet.sh lägger den på kortet som board.py.
try:
    from board import *  # noqa: F401,F403
except ImportError:
    pass

try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
