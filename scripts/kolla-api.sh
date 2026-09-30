#!/usr/bin/env bash
# Kollar att datakällorna svarar och listar planen inom räckvidd just nu.
# Standard är eventlokalen (ABF, S:t Persgatan 22B, Uppsala). Annan plats:
#   LAT=59.86 LON=17.64 RADIE_NM=15 ./kolla-api.sh
set -u

LAT=${LAT:-59.862}
LON=${LON:-17.642}
RADIE_NM=${RADIE_NM:-40}

kolla() {
  local namn=$1 url=$2 svar
  if svar=$(curl -sf -o /dev/null --max-time 10 \
      -w "%{http_code}  %{size_download} byte  %{time_total} s" "$url"); then
    printf "%-15s %s\n" "$namn" "$svar"
  else
    printf "%-15s svarar inte (%s)\n" "$namn" "$svar"
  fi
}

kolla "adsb.fi" "https://opendata.adsb.fi/api/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM"
kolla "adsb.lol" "https://api.adsb.lol/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM"
kolla "wheretheiss.at" "https://api.wheretheiss.at/v1/satellites/25544"
kolla "open-notify" "http://api.open-notify.org/iss-now.json"

# adsb.fi tillåter max 1 anrop per sekund
sleep 1

echo
echo "Plan inom $RADIE_NM nm just nu, närmast först:"
# Anropssignalen kan saknas eller vara "@@@@@@@@". Höjd: alt_geom (GPS) i
# första hand, alt_baro (tryckhöjd) kan bli negativ vid högtryck.
curl -s --max-time 10 "https://opendata.adsb.fi/api/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM" \
  | jq -r '(.ac // .aircraft) | sort_by(.dst)[]
      | ((.flight // "") | gsub("[ @]+$"; "")) as $signal
      | (if .alt_baro == "ground" then "på marken"
         else "\(.alt_geom // .alt_baro) ft" end) as $hojd
      | "\(if $signal == "" then "?" else $signal end)\t\($hojd)\t\((.dir // 0) | floor) grader\t\(.dst) nm"'
