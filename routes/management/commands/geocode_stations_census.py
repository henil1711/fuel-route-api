"""Batch-geocode all unique US stations with the free Census service."""

import csv
import io
import json
from pathlib import Path

import requests
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from routes.models import FuelStation

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
US_STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()


class Command(BaseCommand):
    help = "Batch-geocode unique US stations via Census and import matched coordinates"

    def add_arguments(self, parser):
        parser.add_argument("--input", default="fuel_data/census-stations.csv")
        parser.add_argument("--output", default="fuel_data/census-results.csv")
        parser.add_argument("--submit", action="store_true")
        parser.add_argument("--benchmark", default="Public_AR_Current")
        parser.add_argument("--no-import", action="store_true")

    def handle(self, *args, **options):
        input_path, output_path = Path(options["input"]), Path(options["output"])
        stations = list(FuelStation.objects.filter(state__in=US_STATES).order_by("opis_id"))
        if not stations:
            raise CommandError("Run import_fuel_prices first.")
        if len(stations) > 10000:
            raise CommandError("Census accepts at most 10,000 rows per batch.")
        input_path.parent.mkdir(parents=True, exist_ok=True)
        with input_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "street", "city", "state", "zip"])
            writer.writerows(
                [station.opis_id, station.address, station.city, station.state, ""] for station in stations
            )
        if not options["submit"]:
            self.stdout.write(f"Wrote {len(stations)} rows to {input_path}; rerun with --submit.")
            return
        try:
            with input_path.open("rb") as handle:
                response = requests.post(
                    CENSUS_URL,
                    files={"addressFile": (input_path.name, handle, "text/csv")},
                    data={"benchmark": options["benchmark"]},
                    timeout=(10, 180),
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError("Census request failed; generated input was retained.") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(response.text, encoding="utf-8")
        matches, statuses = [], {}
        for row in csv.reader(io.StringIO(response.text)):
            if len(row) < 7:
                continue
            statuses[row[2]] = statuses.get(row[2], 0) + 1
            if row[2] != "Match":
                continue
            try:
                lon, lat = float(row[5]), float(row[6])
            except ValueError:
                continue
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                matches.append(
                    {
                        "opis_id": row[0],
                        "latitude": lat,
                        "longitude": lon,
                        "source": f"{CENSUS_URL}; Census {options['benchmark']}",
                    }
                )
        coordinates_path = output_path.with_name(output_path.stem + "-coordinates.csv")
        with coordinates_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["opis_id", "latitude", "longitude", "source"])
            writer.writeheader()
            writer.writerows(matches)
        report = {
            "input_rows": len(stations),
            "matched_rows": len(matches),
            "status_counts": statuses,
            "input": str(input_path),
            "raw_output": str(output_path),
            "coordinates": str(coordinates_path),
            "provider": CENSUS_URL,
        }
        output_path.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if matches and not options["no_import"]:
            call_command("import_station_coordinates", str(coordinates_path))
        self.stdout.write(json.dumps(report, indent=2))
