#!/usr/bin/env bash
# Kollar att datakällorna svarar och listar planen inom räckvidd just nu.
set -u

LAT=59.858
LON=17.639
RADIE_NM=40

kolla() {
  local namn=$1 url=$2
  printf "%-15s " "$namn"
  curl -s -o /dev/null --max-time 10 \
    -w "%{http_code}  %{size_download} byte  %{time_total} s\n" "$url" \
    || echo "svarar inte"
}

kolla "adsb.fi" "https://opendata.adsb.fi/api/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM"
kolla "adsb.lol" "https://api.adsb.lol/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM"
kolla "wheretheiss.at" "https://api.wheretheiss.at/v1/satellites/25544"
kolla "open-notify" "http://api.open-notify.org/iss-now.json"

# adsb.fi tillåter max 1 anrop per sekund
sleep 1

echo
echo "Plan inom $RADIE_NM nm just nu:"
curl -s --max-time 10 "https://opendata.adsb.fi/api/v2/lat/$LAT/lon/$LON/dist/$RADIE_NM" \
  | jq -r '(.ac // .aircraft)[]
      | "\((.flight // "?") | gsub(" +$"; ""))\t\(.alt_baro // "?") ft\t\((.dir // 0) | floor) grader\t\(.dst) nm"'
