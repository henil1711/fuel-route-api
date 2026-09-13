import csv
import math
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from routes.models import FuelStation


class Command(BaseCommand):
    help = "Import verified US station coordinates: opis_id,latitude,longitude,source. Atomic; no network."

    def add_arguments(self, parser):
        parser.add_argument("path")

    @transaction.atomic
    def handle(self, *args, **options):
        updates, seen = [], set()
        stations = FuelStation.objects.in_bulk()
        try:
            with open(options["path"], newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not {"opis_id", "latitude", "longitude", "source"}.issubset(reader.fieldnames or []):
                    raise ValueError("Required columns: opis_id,latitude,longitude,source")
                for line, row in enumerate(reader, 2):
                    opis = int(row["opis_id"])
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                    if (
                        opis not in stations
                        or opis in seen
                        or not row["source"].strip()
                        or len(row["source"]) > 500
                    ):
                        raise ValueError(f"Invalid/duplicate station or source on line {line}")
                    if (
                        not math.isfinite(lat)
                        or not math.isfinite(lon)
                        or not (-90 <= lat <= 90 and -180 <= lon <= 180)
                    ):
                        raise ValueError(f"Invalid coordinates on line {line}")
                    station = stations[opis]
                    station.latitude, station.longitude = lat, lon
                    station.coordinate_source, station.updated_at = row["source"].strip(), timezone.now()
                    updates.append(station)
                    seen.add(opis)
            if not updates:
                raise ValueError("No coordinates found")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        FuelStation.objects.bulk_update(
            updates, ["latitude", "longitude", "coordinate_source", "updated_at"], batch_size=500
        )
        self.stdout.write(f"Updated {len(updates)} stations")
