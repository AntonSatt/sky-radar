#!/usr/bin/env python3
"""Adress eller plats -> koordinater, via OpenStreetMaps Nominatim.

    ./terminal/plats.py "Stockholms centralstation"
    ./terminal/plats.py                       frågar var du är

Skriver ut platsens namn och en rad som går att klistra in framför andra
kommandon, till exempel:  LAT=59.8621567 LON=17.6421569 ./scripts/kolla-api.sh

Koordinaterna har full precision från OpenStreetMap (7 decimaler, ca 1 cm).
Adressen skickas till nominatim.openstreetmap.org.
"""

import json
import sys
import urllib.parse
import urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="
# Nominatims regler kräver att programmet identifierar sig
USER_AGENT = "sky-radar/0.1 (+https://github.com/AntonSatt/sky-radar)"


def geocode(query):
    """(lat, lon, kort namn) för en adress eller plats. Kastar LookupError om
    inget hittas."""
    url = NOMINATIM + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        hits = json.load(response)
    if not hits:
        raise LookupError("Hittade ingen plats för: " + query)
    hit = hits[0]
    # Hela namnet är långt ("ABF, 22b, Sankt Persgatan, Höganäs, Främre
    # Luthagen, Centrum, Uppsala, ..."), de första delarna räcker.
    name = ", ".join(part.strip() for part in hit["display_name"].split(",")[:4])
    return float(hit["lat"]), float(hit["lon"]), name


def ask():
    try:
        return input("Var är du? (adress eller plats) ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)


def main():
    query = " ".join(sys.argv[1:]).strip() or ask()
    if not query:
        raise SystemExit("Ingen plats angiven.")
    try:
        lat, lon, name = geocode(query)
    except LookupError as exc:
        raise SystemExit(str(exc))
    print(name)
    print("LAT={} LON={}".format(lat, lon))


if __name__ == "__main__":
    main()
