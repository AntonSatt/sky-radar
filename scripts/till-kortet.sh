#!/usr/bin/env bash
# Lägger koden på kortet och kör den med utskrifterna i terminalen.
# Ctrl-C stoppar. main.py ligger kvar på kortet och startar själv nästa gång
# kortet får ström, även utan laptop.
#
# Första argumentet är kortets profil i pico/boards/, standard är ring:
#   ./scripts/till-kortet.sh          ringkortet
#   ./scripts/till-kortet.sh matris   matriskortet
#
# Saknas pico/secrets.py frågar skriptet efter WiFi först (lösenordet visas
# inte). Annan port än den mpremote hittar själv: PORT=/dev/ttyACM1 ./...
set -euo pipefail

cd "$(dirname "$0")/.."

PROFIL=${1:-ring}
if [[ ! -f pico/boards/$PROFIL.py ]]; then
  echo "Ingen profil pico/boards/$PROFIL.py. Finns: $(ls pico/boards | sed 's/\.py$//' | tr '\n' ' ')" >&2
  exit 1
fi

if [[ ! -f pico/secrets.py ]]; then
  read -rp "WiFi-namn (SSID): " WIFI_SSID
  read -rsp "WiFi-lösenord: " WIFI_PASSWORD
  echo
  WIFI_SSID=$WIFI_SSID WIFI_PASSWORD=$WIFI_PASSWORD python3 -c '
import os
print("WIFI_SSID = %r" % os.environ["WIFI_SSID"])
print("WIFI_PASSWORD = %r" % os.environ["WIFI_PASSWORD"])' > pico/secrets.py
  chmod 600 pico/secrets.py
  unset WIFI_PASSWORD
  echo "Sparade pico/secrets.py (git ignorerar den)"
fi

FILER=(pico/core.py pico/config.py pico/secrets.py pico/oled.py pico/main.py)
[[ -f pico/config_local.py ]] && FILER+=(pico/config_local.py)

MPREMOTE=(mpremote)
[[ -n "${PORT:-}" ]] && MPREMOTE+=(connect "$PORT")

"${MPREMOTE[@]}" cp "${FILER[@]}" : + cp "pico/boards/$PROFIL.py" :board.py + run pico/main.py
