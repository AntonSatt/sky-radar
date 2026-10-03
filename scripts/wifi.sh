#!/usr/bin/env bash
# Lägger till ett WiFi-nät i pico/secrets.py (git ignorerar filen). Det nät
# som läggs till sist provas först; korten tar det första som syns.
# Kör sedan ./scripts/till-kortet.sh för varje kort.
set -euo pipefail

cd "$(dirname "$0")/.."

read -rp "WiFi-namn (SSID): " WIFI_SSID
read -rsp "WiFi-lösenord: " WIFI_PASSWORD
echo

WIFI_SSID=$WIFI_SSID WIFI_PASSWORD=$WIFI_PASSWORD python3 - <<'PY'
import os, pathlib
path = pathlib.Path("pico/secrets.py")
old = {}
if path.exists():
    exec(path.read_text(), old)
nets = list(old.get("WIFI_NETWORKS", []))
if "WIFI_SSID" in old:
    nets.append((old["WIFI_SSID"], old["WIFI_PASSWORD"]))
new = (os.environ["WIFI_SSID"], os.environ["WIFI_PASSWORD"])
nets = [new] + [n for n in nets if n[0] != new[0]]
lines = ["# WiFi för korten i prioritetsordning. Skapad av scripts/wifi.sh,",
         "# git ignorerar filen.", "WIFI_NETWORKS = ["]
lines += ["    (%r, %r)," % n for n in nets]
lines.append("]")
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
print("Nät i pico/secrets.py, i ordning:", ", ".join(n[0] for n in nets))
PY
unset WIFI_PASSWORD
