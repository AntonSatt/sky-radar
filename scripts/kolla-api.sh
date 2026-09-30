#!/usr/bin/env bash
# Kollar att datakällorna svarar och listar planen inom räckvidd just nu.
# Standard är eventlokalen (ABF, S:t Persgatan 22B, Uppsala). Annan plats:
#   LAT=59.8603 LON=17.6337 RADIE_KM=25 ./kolla-api.sh
set -u

LAT=${LAT:-59.8621567}
LON=${LON:-17.6421569}
RADIE_KM=${RADIE_KM:-75}
# API:erna vill ha nautiska mil (1 nm = 1,852 km), avrundat uppåt
RADIE_NM=$(( (RADIE_KM * 1000 + 1851) / 1852 ))

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
echo "Plan inom $RADIE_KM km just nu, närmast först:"
# Anropssignalen kan saknas eller vara "@@@@@@@@". Höjd: alt_geom (GPS) i
# första hand, alt_baro (tryckhöjd) kan bli negativ vid högtryck. Fot blir
# meter och nautiska mil blir km.
curl -s --max-time 10 "https://opendata.adsb.fi/api/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM" \
  | jq -r '(.ac // .aircraft) | sort_by(.dst)[]
      | ((.flight // "") | gsub("[ @]+$"; "")) as $signal
      | (if .alt_baro == "ground" then "på marken"
         else "\((.alt_geom // .alt_baro) * 0.3048 / 10 | round * 10) m" end) as $hojd
      | "\(if $signal == "" then "?" else $signal end)\t\($hojd)\t\((.dir // 0) | floor) grader\t\(.dst * 1.852 * 10 | round / 10) km"'
