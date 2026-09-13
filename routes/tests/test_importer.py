import csv
from decimal import Decimal
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from routes.models import FuelStation, FuelPrice
from routes.services.importer import COLUMNS, import_prices, parse_csv


def write_csv(tmp_path, rows):
    path = tmp_path / "prices.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return path


@pytest.mark.django_db
def test_duplicate_price_observations_idempotence(tmp_path):
    row = [7, " Real Stop ", " Main Road ", " Big Cabin ", "ok", 307, "3.00733333"]
    path = write_csv(tmp_path, [row, row, [*row[:-1], "3.5"]])
    report = import_prices(path)
    assert report["duplicate_rows"] == 1
    assert FuelStation.objects.count() == 1
    station = FuelStation.objects.get()
    assert station.retail_price == Decimal("3.00733333")
    assert station.state == "OK" and station.name == "Real Stop"
    assert FuelPrice.objects.count() == 2
    assert sum(p.occurrences for p in FuelPrice.objects.all()) == 3
    import_prices(path)
    assert FuelPrice.objects.count() == 2


@pytest.mark.parametrize("price", ["", "no", "NaN", "Infinity", "-1", "0", "100", "3.123456789"])
def test_invalid_prices(tmp_path, price):
    path = write_csv(tmp_path, [[1, "Stop", "Road", "City", "TX", 2, price]])
    _, report = parse_csv(path)
    assert report["invalid_prices"] == 1 and report["rows_skipped"] == 1


def test_foreign_missing_and_malformed_rows(tmp_path):
    path = write_csv(
        tmp_path, [[1, "Stop", "Road", "City", "ON", 1, 3], [2, "Stop", "", "City", "TX", 1, 3], [3, "short"]]
    )
    _, report = parse_csv(path)
    assert report["non_us_rows"] == 1
    assert report["malformed_rows"] == 2
    assert report["rows_skipped"] == 3


def test_empty_file_and_columns(tmp_path):
    path = write_csv(tmp_path, [])
    with pytest.raises(ValueError):
        parse_csv(path)
    path.write_text("bad,columns\n")
    with pytest.raises(ValueError):
        parse_csv(path)


@pytest.mark.django_db
def test_snapshot_refresh_preserves_coordinates_unless_metadata_changes(tmp_path):
    row = [1, "Stop", "Road", "City", "TX", 2, 3]
    path = write_csv(tmp_path, [row])
    import_prices(path)
    FuelStation.objects.filter(pk=1).update(latitude=30, longitude=-100, coordinate_source="verified")
    path = write_csv(tmp_path, [[*row[:-1], 4]])
    import_prices(path)
    assert FuelStation.objects.get().latitude == 30
    assert FuelStation.objects.get().retail_price == 4
    row[2] = "Changed road"
    path = write_csv(tmp_path, [row])
    import_prices(path)
    assert FuelStation.objects.get().latitude is None


@pytest.mark.django_db
def test_database_rejects_partial_coordinate_pair(tmp_path):
    from django.db import IntegrityError, transaction

    import_prices(write_csv(tmp_path, [[1, "Stop", "Road", "City", "TX", 2, 3]]))
    with pytest.raises(IntegrityError), transaction.atomic():
        FuelStation.objects.filter(pk=1).update(latitude=30, longitude=None)


@pytest.mark.django_db
def test_coordinate_import_atomic_validation(tmp_path):
    import_prices(write_csv(tmp_path, [[1, "Stop", "Road", "City", "TX", 2, 3]]))
    path = tmp_path / "coords.csv"
    path.write_text("opis_id,latitude,longitude,source\n1,30,-100,verified\n1,NaN,0,bad\n")
    with pytest.raises(CommandError):
        call_command("import_station_coordinates", str(path))
    assert FuelStation.objects.get().latitude is None
