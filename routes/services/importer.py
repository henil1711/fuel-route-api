import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from routes.models import FuelPrice, FuelStation

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
COLUMNS = ["OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"]


def parse_csv(path: str | Path) -> tuple[list[dict], dict]:
    observations = {}
    ids, locations, states = Counter(), Counter(), Counter()
    missing = Counter({column: 0 for column in COLUMNS})
    errors, prices = [], []
    counters = Counter(
        rows_read=0,
        rows_imported=0,
        rows_skipped=0,
        duplicate_rows=0,
        invalid_prices=0,
        non_us_rows=0,
        malformed_rows=0,
    )
    all_ids, all_locations = Counter(), Counter()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Expected columns in order: {', '.join(COLUMNS)}")
        for line, raw in enumerate(reader, 2):
            counters["rows_read"] += 1
            if None in raw or any(value is None for value in raw.values()):
                counters["malformed_rows"] += 1
                counters["rows_skipped"] += 1
                errors.append({"line": line, "reason": "wrong number of fields"})
                continue
            row = {k: " ".join(v.split()) for k, v in raw.items()}
            row["State"] = row["State"].upper()
            states[row["State"]] += 1
            all_ids[row["OPIS Truckstop ID"]] += 1
            location = tuple(row[k].casefold() for k in ("Address", "City", "State"))
            all_locations[location] += 1
            for key, value in row.items():
                if not value:
                    missing[key] += 1
            try:
                price = Decimal(row["Retail Price"])
                if not price.is_finite() or not 0 < price < 100 or price.as_tuple().exponent < -8:
                    raise InvalidOperation
                prices.append(price)
            except InvalidOperation:
                counters["invalid_prices"] += 1
                counters["rows_skipped"] += 1
                errors.append({"line": line, "reason": "invalid price"})
                continue
            if row["State"] not in US_STATES:
                counters["non_us_rows"] += 1
                counters["rows_skipped"] += 1
                continue
            try:
                opis, rack = int(row["OPIS Truckstop ID"]), int(row["Rack ID"])
                if not 0 < opis <= 2147483647 or not 0 <= rack <= 2147483647:
                    raise ValueError
                if any(not row[k] for k in COLUMNS):
                    raise ValueError
                if any(
                    len(row[k]) > limit
                    for k, limit in (("Truckstop Name", 250), ("Address", 300), ("City", 120))
                ):
                    raise ValueError
            except ValueError:
                counters["malformed_rows"] += 1
                counters["rows_skipped"] += 1
                errors.append({"line": line, "reason": "missing/invalid station metadata"})
                continue
            ids[opis] += 1
            locations[location] += 1
            fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
            if fingerprint in observations:
                observations[fingerprint]["occurrences"] += 1
                counters["duplicate_rows"] += 1
            else:
                observations[fingerprint] = {
                    "opis": opis,
                    "rack": rack,
                    "price": price,
                    "row": row,
                    "fingerprint": fingerprint,
                    "occurrences": 1,
                }
            counters["rows_imported"] += 1
    if not counters["rows_read"]:
        raise ValueError("CSV contains no data rows")
    grouped = defaultdict(set)
    for observation in observations.values():
        grouped[observation["opis"]].add(observation["price"])
    report = {
        **counters,
        "filename": Path(path).name,
        "columns": COLUMNS,
        "coordinates_present": False,
        "data_types": {
            "OPIS Truckstop ID": "integer",
            "Rack ID": "integer",
            "Retail Price": "decimal",
            "other": "text",
        },
        "unique_ids_all_countries": len(all_ids),
        "duplicate_ids_all_countries": sum(v > 1 for v in all_ids.values()),
        "duplicate_locations_all_countries": sum(v > 1 for v in all_locations.values()),
        "unique_us_stations": len(ids),
        "us_ids_with_multiple_prices": sum(len(v) > 1 for v in grouped.values()),
        "distinct_us_observations": len(observations),
        "missing_values": dict(missing),
        "state_counts": dict(sorted(states.items())),
        "price_min": str(min(prices)) if prices else None,
        "price_max": str(max(prices)) if prices else None,
        "errors": errors,
    }
    return list(observations.values()), report


@transaction.atomic
def import_prices(path: str | Path) -> dict:
    observations, report = parse_csv(path)
    if not observations:
        raise ValueError("No valid US observations; existing data was not changed")
    groups = defaultdict(list)
    for item in observations:
        groups[item["opis"]].append(item)
    existing = FuelStation.objects.in_bulk(groups)
    creates, updates = [], []
    for opis, records in groups.items():
        # Preserve every source row. Canonical metadata is deterministic, independent of input order.
        record = min(records, key=lambda r: (r["price"], r["fingerprint"]))
        row = record["row"]
        station = existing.get(opis)
        if station is None:
            station = FuelStation(opis_id=opis)
            creates.append(station)
        else:
            if (station.name, station.address, station.city, station.state) != (
                row["Truckstop Name"],
                row["Address"],
                row["City"],
                row["State"],
            ):
                station.latitude = station.longitude = None
                station.coordinate_source = ""
            updates.append(station)
        station.name, station.address, station.city, station.state = (
            row["Truckstop Name"],
            row["Address"],
            row["City"],
            row["State"],
        )
        station.retail_price = record["price"]
        station.updated_at = timezone.now()
    FuelStation.objects.bulk_create(creates, batch_size=500)
    FuelStation.objects.bulk_update(
        updates,
        [
            "name",
            "address",
            "city",
            "state",
            "retail_price",
            "latitude",
            "longitude",
            "coordinate_source",
            "updated_at",
        ],
        batch_size=500,
    )
    # Treat a successful file as a complete snapshot, avoiding stale cheap prices from previous imports.
    FuelStation.objects.exclude(opis_id__in=groups).delete()
    FuelPrice.objects.all().delete()
    FuelPrice.objects.bulk_create(
        [
            FuelPrice(
                station_id=r["opis"],
                fingerprint=r["fingerprint"],
                rack_id=r["rack"],
                price=r["price"],
                occurrences=r["occurrences"],
                source_row=r["row"],
            )
            for r in observations
        ],
        batch_size=500,
    )
    from .station_matcher import _station_index

    _station_index.cache_clear()
    return report
