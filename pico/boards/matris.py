# Matriskortet: ESP32-C3 SuperMini fastlött på en 8x8-matris, DIN på GPIO4
# (hittat med ett stifttest 2026-10-03). Ingen ring.
LED_PIN = None
GRID_PIN = 4
STATUS_LED_PIN = None   # SuperMinis lysdiod är en vanlig lysdiod, inte RGB
BUTTON_PIN = 9          # BOOT-knappen
WIFI_TXPOWER = 8.5      # SuperMinis antenn klarar ofta inte full sändareffekt
