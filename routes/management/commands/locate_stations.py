"""Batch POI preprocessing; never individually geocode the CSV stations."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from pyproj import Geod
from routes.models import FuelStation


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def chain(value: str) -> str | None:
    name = normalized(value)
    for needle, brand in [
        ("flyingj", "flyingj"),
        ("pilot", "pilot"),
        ("loves", "loves"),
        ("kwiktrip", "kwiktrip"),
        ("kwikstar", "kwikstar"),
        ("speedway", "speedway"),
        ("caseys", "caseys"),
        ("travelcentersofamerica", "ta"),
        ("petro", "petro"),
    ]:
        if needle in name:
            return brand
    if re.match(r"^TA\b", value.upper()):
        return "ta"
    return None


class Command(BaseCommand):
    help = "Locate CSV stations by exact chain/store IDs in one US OSM fuel POI extract; ambiguous matches stay unresolved"

    def add_arguments(self, parser):
        parser.add_argument("--osm-file", default="fuel_data/osm-us.json")
        parser.add_argument(
            "--download", action="store_true", help="Explicitly fetch/cache one US fuel POI extract"
        )
        parser.add_argument("--output", default="fuel_data/station-coordinates.csv")

    def handle(self, *args, **options):
        path = Path(options["osm_file"])
        if options["download"] and not path.exists():
            query = '[out:json][timeout:120];area["ISO3166-1"="US"]["admin_level"="2"]->.us;nwr["amenity"="fuel"]["brand"~"Pilot|Love|Flying|TravelCenters|Petro|Kwik|Speedway|Casey",i](area.us);out center tags;'
            try:
                response = requests.post(
                    settings.OVERPASS_BASE_URL,
                    data={"data": query},
                    headers={"User-Agent": settings.GEOCODING_USER_AGENT},
                    timeout=(10, 220),
                )
                response.raise_for_status()
                data = response.json()
                if "elements" not in data or data.get("remark"):
                    raise ValueError("Incomplete extract; try again later")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
            except (requests.RequestException, ValueError) as exc:
                raise CommandError(
                    "OSM extract unavailable; supply a locally downloaded Overpass JSON extract"
                ) from exc
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("remark") or "elements" not in data:
                raise ValueError("Incomplete extract")
        except (OSError, ValueError) as exc:
            raise CommandError("Supply --osm-file or use --download to retrieve the extract once") from exc
        by_store = defaultdict(list)
        by_city = defaultdict(list)
        station_cities = defaultdict(set)
        stations = list(FuelStation.objects.order_by("opis_id"))
        for station in stations:
            station_cities[(chain(station.name), normalized(station.city), station.state)].add(
                station.opis_id
            )
        for element in data["elements"]:
            tags = element.get("tags", {})
            brand = chain(tags.get("brand", "") + " " + tags.get("name", "") + " " + tags.get("operator", ""))
            ref = tags.get("ref", "").strip()
            if not ref.isdigit():
                match = re.search(r"#\s*(\d+)", tags.get("name", ""))
                ref = match.group(1) if match else ""
            point = element.get("center", element)
            if (
                brand
                and "lat" in point
                and "lon" in point
                and tags.get("addr:city")
                and tags.get("addr:state")
            ):
                by_city[(brand, normalized(tags["addr:city"]), tags["addr:state"].upper())].append(
                    (element, point)
                )
            if brand and ref.isdigit() and "lat" in point and "lon" in point:
                by_store[(brand, int(ref))].append((element, point))
        geod = Geod(ellps="WGS84")
        located, unresolved = [], []
        for station in stations:
            match = re.search(r"#\s*(\d+)", station.name)
            choices = by_store.get((chain(station.name), int(match.group(1))), []) if match else []
            method = "exact chain/store ref"
            city_key = (chain(station.name), normalized(station.city), station.state)
            if not choices and len(station_cities[city_key]) == 1:
                choices = by_city.get(city_key, [])
                # Never override an explicitly conflicting store reference.
                choices = [
                    (e, p)
                    for e, p in choices
                    if not e["tags"].get("ref", "").isdigit()
                    or (match and int(e["tags"]["ref"]) == int(match.group(1)))
                ]
                method = "unique chain/city/state match; approximate identity"
            choices = [
                (e, p)
                for e, p in choices
                if e["tags"].get("addr:state", station.state).upper() == station.state
            ]
            if choices:
                first = choices[0][1]
                if any(geod.inv(first["lon"], first["lat"], p["lon"], p["lat"])[2] > 500 for _, p in choices):
                    choices = []
            if choices:
                element, point = min(choices, key=lambda item: (item[0]["type"] != "node", item[0]["id"]))
                source = f"https://www.openstreetmap.org/{element['type']}/{element['id']}; {method}"
                located.append(
                    {
                        "opis_id": station.opis_id,
                        "latitude": point["lat"],
                        "longitude": point["lon"],
                        "source": source,
                    }
                )
            else:
                unresolved.append(station.opis_id)
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["opis_id", "latitude", "longitude", "source"])
            writer.writeheader()
            writer.writerows(located)
        report = {
            "osm_elements": len(data["elements"]),
            "located": len(located),
            "unresolved": len(unresolved),
            "unresolved_opis_ids": unresolved,
            "osm_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
            "method": "Exact chain/store reference, else unique chain/city/state in both datasets; conflicting references and ambiguous distant POIs rejected. City matches require identity review for operational use.",
            "attribution": "© OpenStreetMap contributors, ODbL 1.0",
            "source": settings.OVERPASS_BASE_URL,
        }
        output.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if located:
            call_command("import_station_coordinates", str(output))
        self.stdout.write(f"Located {len(located)} CSV stations; {len(unresolved)} unresolved. See {output}")
